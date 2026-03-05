"""Capture telecom fixtures from lab PBX targets."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Any

from ..config import AMIConfig, ARIConfig, ESLConfig, Settings, resolve_target_secrets
from ..connectors.asterisk_ami import AsteriskAMIConnector
from ..connectors.asterisk_ari import AsteriskARIConnector
from ..connectors.freeswitch_esl import FreeSWITCHESLConnector
from ..errors import NOT_ALLOWED, VALIDATION_ERROR, ToolError
from .generator import generate_fixture_tests
from .normalizer import normalize_sanitized_fixtures
from .sanitizer import FixtureSanitizer


@dataclass(slots=True)
class FixtureRunPaths:
    root: Path
    raw: Path
    sanitized: Path
    tests: Path
    report: Path


class FixtureCaptureRunner:
    def __init__(
        self,
        settings: Settings,
        *,
        output_root: Path,
        pbx_ids: list[str] | None = None,
        endpoint: str = "1001",
        timeout_s: float = 4.0,
        sanitizer: FixtureSanitizer | None = None,
    ) -> None:
        self.settings = settings
        self.output_root = output_root
        self.pbx_ids = pbx_ids or [target.id for target in settings.targets]
        self.endpoint = endpoint
        self.timeout_s = timeout_s
        self.sanitizer = sanitizer or FixtureSanitizer()

    def run(self) -> dict[str, Any]:
        started = monotonic()
        run_paths = self._prepare_run_paths()
        phases: list[dict[str, Any]] = []

        self._phase_f0_readiness(phases)
        raw_files = self._phase_f1_capture_raw(run_paths, phases)
        sanitized_files = self._phase_f2_sanitize(run_paths, raw_files, phases)
        normalized = self._phase_f3_normalize(run_paths, phases)
        generated_tests = self._phase_f4_generate_tests(run_paths, phases)
        self._phase_f5_replay_validation(normalized, phases)
        self._phase_f6_version_check(normalized, phases)

        duration_ms = int((monotonic() - started) * 1000)
        report = {
            "created_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "duration_ms": duration_ms,
            "run": str(run_paths.root),
            "raw_files": [str(p.relative_to(run_paths.root)) for p in raw_files],
            "sanitized_files": [str(p.relative_to(run_paths.root)) for p in sanitized_files],
            "normalized_files": [str(p.relative_to(run_paths.root)) for p in normalized],
            "generated_tests": [str(p.relative_to(run_paths.root)) for p in generated_tests],
            "phases": phases,
        }
        run_paths.report.write_text(_render_report(report), encoding="utf-8")
        return report

    def _prepare_run_paths(self) -> FixtureRunPaths:
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        root = self.output_root / stamp
        raw = root / "raw"
        sanitized = root / "sanitized"
        tests = root / "tests"
        for path in (root, raw, sanitized, tests):
            path.mkdir(parents=True, exist_ok=False)
        return FixtureRunPaths(root=root, raw=raw, sanitized=sanitized, tests=tests, report=root / "report.md")

    def _phase_f0_readiness(self, phases: list[dict[str, Any]]) -> None:
        if os.getenv("FIXTURE_CAPTURE", "").lower() != "true":
            raise ToolError(
                NOT_ALLOWED,
                "Fixture capture requires FIXTURE_CAPTURE=true",
            )
        if self.sanitizer.rule_count <= 0:
            raise ToolError(VALIDATION_ERROR, "No redaction rules loaded")

        for pbx_id in self.pbx_ids:
            target = self.settings.get_target(pbx_id)
            if getattr(target, "environment", "unknown") != "lab":
                raise ToolError(
                    NOT_ALLOWED,
                    "Fixture capture is allowed only for lab targets",
                    {"pbx_id": pbx_id, "environment": getattr(target, "environment", "unknown")},
                )

        phases.append({"phase": "F0", "ok": True, "checks": ["capture enabled", "lab-only targets", "redaction rules loaded"]})

    def _phase_f1_capture_raw(self, run_paths: FixtureRunPaths, phases: list[dict[str, Any]]) -> list[Path]:
        written: list[Path] = []
        for pbx_id in self.pbx_ids:
            target = self.settings.get_target(pbx_id)
            _ = resolve_target_secrets(target)

            if target.type == "asterisk":
                if target.ami:
                    ami = AsteriskAMIConnector(
                        AMIConfig(
                            host=target.ami.host,
                            port=target.ami.port,
                            username_env=target.ami.username_env,
                            password_env=target.ami.password_env,
                        ),
                        timeout_s=self.timeout_s,
                    )
                    try:
                        core = ami.send_action({"Action": "CoreStatus"})
                        endpoints = ami.send_action({"Action": "PJSIPShowEndpoints"})
                        endpoint = ami.send_action(
                            {"Action": "PJSIPShowEndpoint", "Endpoint": self.endpoint}
                        )
                    finally:
                        ami.close()
                    written.extend(
                        [
                            _write_json(run_paths.raw / "ami_core_status.json", core),
                            _write_json(run_paths.raw / "ami_pjsip_show_endpoints.json", endpoints),
                            _write_json(run_paths.raw / "ami_pjsip_show_endpoint.json", endpoint),
                        ]
                    )

                if target.ari:
                    ari = AsteriskARIConnector(
                        ARIConfig(
                            url=target.ari.url,
                            username_env=target.ari.username_env,
                            password_env=target.ari.password_env,
                            app=target.ari.app,
                        ),
                        timeout_s=self.timeout_s,
                    )
                    channels = ari.get("channels")
                    endpoints = ari.get("endpoints")
                    bridges = ari.get("bridges")
                    ari.close()
                    written.extend(
                        [
                            _write_json(run_paths.raw / "ari_channels.json", channels),
                            _write_json(run_paths.raw / "ari_endpoints.json", endpoints),
                            _write_json(run_paths.raw / "ari_bridges.json", bridges),
                        ]
                    )

            if target.type == "freeswitch" and target.esl:
                esl = FreeSWITCHESLConnector(
                    ESLConfig(
                        host=target.esl.host,
                        port=target.esl.port,
                        password_env=target.esl.password_env,
                    ),
                    timeout_s=self.timeout_s,
                )
                try:
                    status = esl.api("status")
                    sofia = esl.api("sofia status")
                    regs = esl.api("show registrations")
                finally:
                    esl.close()
                written.extend(
                    [
                        _write_text(run_paths.raw / "esl_status.txt", status),
                        _write_text(run_paths.raw / "esl_sofia_status.txt", sofia),
                        _write_text(run_paths.raw / "esl_show_registrations.txt", regs),
                    ]
                )

        phases.append({"phase": "F1", "ok": True, "raw_files": [p.name for p in written]})
        return written

    def _phase_f2_sanitize(
        self,
        run_paths: FixtureRunPaths,
        raw_files: list[Path],
        phases: list[dict[str, Any]],
    ) -> list[Path]:
        sanitized: list[Path] = []
        for path in raw_files:
            if path.suffix.lower() == ".json":
                payload = json.loads(path.read_text(encoding="utf-8"))
                cleaned = self.sanitizer.sanitize_data(payload)
            else:
                raw_text = path.read_text(encoding="utf-8")
                cleaned = {
                    "raw_text": self.sanitizer.sanitize_text(raw_text),
                }

            self.sanitizer.assert_no_sensitive_markers(cleaned)
            out = run_paths.sanitized / f"{path.stem}.json"
            out.write_text(json.dumps(cleaned, indent=2, sort_keys=True), encoding="utf-8")
            sanitized.append(out)

        phases.append({"phase": "F2", "ok": True, "sanitized_files": [p.name for p in sanitized]})
        return sanitized

    def _phase_f3_normalize(self, run_paths: FixtureRunPaths, phases: list[dict[str, Any]]) -> list[Path]:
        normalized = normalize_sanitized_fixtures(
            sanitized_dir=run_paths.sanitized,
            output_dir=run_paths.sanitized,
            version=1,
        )
        phases.append({"phase": "F3", "ok": True, "normalized_files": [p.name for p in normalized]})
        return normalized

    def _phase_f4_generate_tests(self, run_paths: FixtureRunPaths, phases: list[dict[str, Any]]) -> list[Path]:
        tests = generate_fixture_tests(normalized_dir=run_paths.sanitized, tests_dir=run_paths.tests)
        phases.append({"phase": "F4", "ok": True, "tests": [p.name for p in tests]})
        return tests

    def _phase_f5_replay_validation(self, normalized: list[Path], phases: list[dict[str, Any]]) -> None:
        missing_data = []
        for file in normalized:
            if file.suffix != ".json":
                continue
            payload = json.loads(file.read_text(encoding="utf-8"))
            if "data" not in payload:
                missing_data.append(file.name)
        if missing_data:
            raise ToolError(
                VALIDATION_ERROR,
                "Fixture replay validation failed",
                {"missing_data": missing_data},
            )
        phases.append({"phase": "F5", "ok": True})

    def _phase_f6_version_check(self, normalized: list[Path], phases: list[dict[str, Any]]) -> None:
        missing_version = []
        for file in normalized:
            if file.suffix != ".json":
                continue
            payload = json.loads(file.read_text(encoding="utf-8"))
            if not isinstance(payload.get("version"), int):
                missing_version.append(file.name)
        if missing_version:
            raise ToolError(
                VALIDATION_ERROR,
                "Fixture versioning check failed",
                {"missing_version": missing_version},
            )
        phases.append({"phase": "F6", "ok": True})


def _write_json(path: Path, payload: Any) -> Path:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _write_text(path: Path, payload: str) -> Path:
    path.write_text(payload, encoding="utf-8")
    return path


def _render_report(report: dict[str, Any]) -> str:
    lines = [
        "# Fixture Capture Report",
        "",
        f"- Created: {report['created_at']}",
        f"- Duration (ms): {report['duration_ms']}",
        f"- Run path: `{report['run']}`",
        "",
        "## Phase Results",
    ]
    for phase in report["phases"]:
        lines.append(f"- {phase['phase']}: {'PASS' if phase['ok'] else 'FAIL'}")

    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            "### Raw",
        ]
    )
    lines.extend(f"- `{name}`" for name in report["raw_files"])
    lines.extend(["", "### Sanitized"])
    lines.extend(f"- `{name}`" for name in report["sanitized_files"])
    lines.extend(["", "### Normalized"])
    lines.extend(f"- `{name}`" for name in report["normalized_files"])
    lines.extend(["", "### Tests"])
    lines.extend(f"- `{name}`" for name in report["generated_tests"])
    lines.append("")
    return "\n".join(lines)
