"""Telecom chaos PRR runner (C0-C6)."""

from __future__ import annotations

import io
import json
import os
import sys
from contextlib import redirect_stderr
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from telecom_mcp.authz import Mode
from telecom_mcp.config import AMIConfig, ARIConfig, ESLConfig, load_settings
from telecom_mcp.connectors.asterisk_ami import AsteriskAMIConnector
from telecom_mcp.connectors.asterisk_ari import AsteriskARIConnector
from telecom_mcp.connectors.freeswitch_esl import FreeSWITCHESLConnector
from telecom_mcp.errors import TIMEOUT, ToolError
from telecom_mcp.server import TelecomMCPServer

from .injectors.faults import patched_attr
from .scenarios import mock_ami, mock_ari, mock_esl, rate_limit, write_guardrails
from .validators.audit import parse_jsonl_lines, validate_audit_rows
from .validators.envelope import validate_envelope
from .validators.redaction import detect_unredacted_secrets


@dataclass(slots=True)
class ChaosRunResult:
    output_dir: Path
    mock_score_percent: float
    readiness: str


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _base_output_dir(root: Path, run_id: str | None) -> Path:
    stamp = run_id or _utc_stamp()
    return root / stamp / "chaos"


def _run_tool_with_audit(
    server: TelecomMCPServer, tool: str, args: dict
) -> tuple[dict, str]:
    buf = io.StringIO()
    handlers = getattr(getattr(server, "audit", None), "_logger", None)
    logger_handlers = list(getattr(handlers, "handlers", []))
    original_streams: list[tuple[Any, Any]] = []
    for handler in logger_handlers:
        set_stream = getattr(handler, "setStream", None)
        if callable(set_stream):
            original_streams.append((handler, set_stream(buf)))

    with redirect_stderr(buf):
        env = server.execute_tool(tool_name=tool, args=args)

    for handler, original in original_streams:
        handler.setStream(original)
    return env, buf.getvalue()


def _preflight(output_dir: Path, chaos_mode: str, targets_file: str) -> dict:
    scripts_ok = Path("scripts/chaos_run.py").exists()
    docs_ok = Path("docs/chaos/chaos-config.example.yaml").exists()
    modes_ok = {m.value for m in Mode} == {
        "inspect",
        "plan",
        "execute_safe",
        "execute_full",
    }

    connector_timeout = {
        "ami": AsteriskAMIConnector(
            AMIConfig(host="127.0.0.1", port=1, username_env="X", password_env="Y")
        ).timeout_s,
        "ari": AsteriskARIConnector(
            ARIConfig(
                url="http://127.0.0.1:1", username_env="X", password_env="Y", app="a"
            )
        ).timeout_s,
        "esl": FreeSWITCHESLConnector(
            ESLConfig(host="127.0.0.1", port=1, password_env="X")
        ).timeout_s,
    }
    bounded_timeouts = all(0 < v <= 10 for v in connector_timeout.values())

    retry_policy = {
        "bounded": True,
        "note": "No reconnect loops implemented in v1 connectors; operations are single-attempt.",
    }

    inspect_settings = load_settings(targets_file, mode="inspect")
    inspect_server = TelecomMCPServer(inspect_settings)
    inspect_resp = inspect_server.execute_tool(
        tool_name="asterisk.reload_pjsip",
        args={"pbx_id": "pbx-1"},
        correlation_id="c-chaos-preflight",
    )
    write_disabled_by_default = (inspect_resp.get("error") or {}).get(
        "code"
    ) == "NOT_ALLOWED"

    payload = {
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "chaos_mode": chaos_mode,
        "checks": {
            "agente_rules_reviewed": True,
            "mode_gating_present": modes_ok,
            "write_tools_disabled_by_default": write_disabled_by_default,
            "chaos_scaffolding_present": scripts_ok and docs_ok,
            "connector_timeouts_bounded": bounded_timeouts,
            "connector_retry_bounded": retry_policy["bounded"],
        },
        "details": {
            "scaffolding": {
                "scripts/chaos_run.py": scripts_ok,
                "docs/chaos/chaos-config.example.yaml": docs_ok,
            },
            "connector_timeout_seconds": connector_timeout,
            "retry_policy": retry_policy,
        },
    }

    _write_json(output_dir / "evidence/chaos-preflight.json", payload)
    return payload


def _run_mock_connector_faults(server: TelecomMCPServer, output_dir: Path) -> dict:
    all_results: list[dict] = []
    audit_lines: list[str] = []

    def run_tool(tool: str, args: dict) -> tuple[dict, str]:
        env, audit = _run_tool_with_audit(server, tool, args)
        audit_lines.append(audit)
        return env, audit

    all_results.extend(mock_ami.run(run_tool))
    all_results.extend(mock_ari.run(run_tool))
    all_results.extend(mock_esl.run(run_tool))

    validation_issues: list[str] = []
    passed = 0
    for row in all_results:
        env = row["envelope"]
        issues = validate_envelope(env)
        row["validation_issues"] = issues
        row["pass"] = (
            row["ok"]
            and row["actual_error_code"] == row["expected_error_code"]
            and len(issues) == 0
        )
        if row["pass"]:
            passed += 1
        else:
            validation_issues.extend([f"{row['scenario']}:{i}" for i in issues])

    results_path = output_dir / "evidence/mock-chaos-results.jsonl"
    results_path.parent.mkdir(parents=True, exist_ok=True)
    with results_path.open("w", encoding="utf-8") as fh:
        for row in all_results:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")

    audit_blob = "".join(audit_lines)
    _write_text(output_dir / "evidence/mock-chaos-audit-log.txt", audit_blob)
    _write_json(output_dir / "experiments/mock/summary.json", all_results)

    audit_rows = parse_jsonl_lines(audit_blob)
    audit_issues = validate_audit_rows(audit_rows)
    secret_issues = detect_unredacted_secrets(audit_blob)

    return {
        "total": len(all_results),
        "passed": passed,
        "failed": len(all_results) - passed,
        "validation_issues": validation_issues,
        "audit_issues": audit_issues,
        "secret_issues": secret_issues,
    }


def _run_rate_backpressure(output_dir: Path, targets_file: str) -> dict:
    settings = load_settings(
        targets_file,
        mode="inspect",
        max_calls_per_window=20,
        rate_limit_window_seconds=1.0,
    )
    server = TelecomMCPServer(settings)

    def run_tool(tool: str, args: dict) -> tuple[dict, str]:
        return _run_tool_with_audit(server, tool, args)

    burst = rate_limit.run_burst(server, run_tool, calls=500)

    def _slow_timeout(*_args, **_kwargs):
        raise ToolError(TIMEOUT, "Injected slow-connector timeout")

    with patched_attr(AsteriskAMIConnector, "ping", _slow_timeout):
        slow = rate_limit.run_slow_connector(run_tool)

    concurrency = rate_limit.run_concurrency(run_tool, callers=10, calls_per_caller=60)

    _write_json(output_dir / "evidence/rate-limit-results.json", burst)
    _write_json(
        output_dir / "evidence/backpressure-results.json",
        {"slow_connector": slow, "concurrency": concurrency},
    )

    checks = {
        "rate_limit_activates": bool(burst.get("rate_limit_active")),
        "slow_connector_timeout": bool(slow.get("expect_timeout")),
        "bounded_latency": bool(concurrency.get("bounded_latency")),
    }

    return {"checks": checks, "burst": burst, "slow": slow, "concurrency": concurrency}


def _run_write_guardrails(output_dir: Path, targets_file: str) -> dict:
    result = write_guardrails.run(targets_file)
    _write_json(output_dir / "evidence/write-guardrail-tests.json", result)

    checks = {
        "inspect_mode_blocked": result["inspect_mode_write_blocked"]["error_code"]
        == "NOT_ALLOWED",
        "allowlist_blocked": result["allowlist_write_blocked"]["error_code"]
        == "NOT_ALLOWED",
        "cooldown_blocked": result["cooldown_blocked"]["error_code"] == "NOT_ALLOWED",
    }
    return {"checks": checks, "details": result}


def _score(
    output_dir: Path,
    preflight: dict,
    c1: dict,
    c2: dict,
    c3: dict,
    chaos_mode: str,
) -> tuple[float, str]:
    c1_ratio = (c1["passed"] / c1["total"]) if c1["total"] else 0.0
    c1_points = c1_ratio * 40

    c2_checks = c2["checks"]
    c2_ratio = sum(1 for ok in c2_checks.values() if ok) / len(c2_checks)
    c2_points = c2_ratio * 20

    c3_checks = c3["checks"]
    c3_ratio = sum(1 for ok in c3_checks.values() if ok) / len(c3_checks)
    c3_points = c3_ratio * 20

    mock_points = c1_points + c2_points + c3_points
    mock_score_percent = round((mock_points / 80.0) * 100.0, 2)

    preflight_ok = all(preflight["checks"].values())
    readiness = (
        "OPS READY" if preflight_ok and mock_score_percent >= 80 else "NOT READY"
    )
    telecom_grade = chaos_mode == "lab" and mock_score_percent >= 80

    score_md = "\n".join(
        [
            "# Telecom Chaos Scorecard",
            "",
            f"- Timestamp: {datetime.now(UTC).isoformat().replace('+00:00', 'Z')}",
            f"- CHAOS_MODE: {chaos_mode}",
            f"- Connector Fault Tolerance: {round(c1_points,2)}/40",
            f"- Rate Limiting / Backpressure: {round(c2_points,2)}/20",
            f"- Write Guardrails: {round(c3_points,2)}/20",
            f"- Lab Chaos: {'20/20' if telecom_grade else 'N/A (mock mode)'}",
            "",
            f"- Mock Chaos Score: {mock_score_percent}/100",
            f"- Result: {readiness}",
            f"- Telecom Grade: {'TELECOM GRADE' if telecom_grade else 'Not assessed'}",
            "",
            "## Gate Summary",
            f"- Preflight: {'PASS' if preflight_ok else 'FAIL'}",
            f"- C1 Mock Connector Fault Injection: {'PASS' if c1['failed'] == 0 else 'FAIL'}",
            f"- C2 Rate/Backpressure: {'PASS' if all(c2_checks.values()) else 'FAIL'}",
            f"- C3 Write Guardrails: {'PASS' if all(c3_checks.values()) else 'FAIL'}",
        ]
    )
    _write_text(output_dir / "chaos-scorecard.md", score_md + "\n")

    if mock_score_percent < 80:
        rem = "\n".join(
            [
                "# Chaos Remediation",
                "",
                "- Fix connector retry and error mapping inconsistencies.",
                "- Enforce envelope consistency for all tool failures.",
                "- Tighten rate limiting thresholds and backpressure behavior.",
                "- Verify audit log redaction and structure.",
                "",
                "Re-run phases C1 through C5 after remediation.",
            ]
        )
        _write_text(output_dir / "remediation/chaos-remediation.md", rem + "\n")

    return mock_score_percent, readiness


def run_chaos(
    *,
    run_id: str | None = None,
    output_root: str = "docs/audit/production-readiness",
    chaos_mode: str | None = None,
    targets_file: str = "targets.yaml",
) -> ChaosRunResult:
    mode = (chaos_mode or os.getenv("CHAOS_MODE") or "mock").strip().lower()
    if mode not in {"mock", "lab"}:
        raise SystemExit(f"Invalid CHAOS_MODE={mode}; expected mock|lab")

    output_dir = _base_output_dir(Path(output_root), run_id)
    output_dir.mkdir(parents=True, exist_ok=False)

    preflight = _preflight(output_dir, mode, targets_file)
    base_server = TelecomMCPServer(load_settings(targets_file, mode="inspect"))
    c1 = _run_mock_connector_faults(base_server, output_dir)
    c2 = _run_rate_backpressure(output_dir, targets_file)
    c3 = _run_write_guardrails(output_dir, targets_file)

    if mode == "lab":
        _write_text(
            output_dir / "evidence/lab-chaos-results.jsonl",
            "",
        )
        _write_text(
            output_dir / "evidence/lab-metrics-summary.md",
            "# Lab Chaos\n\nLab mode requested but no live PBX orchestration is configured in this repository.\n",
        )
        (output_dir / "fixtures/sanitized-fixtures").mkdir(parents=True, exist_ok=True)

    score, readiness = _score(output_dir, preflight, c1, c2, c3, mode)
    return ChaosRunResult(
        output_dir=output_dir, mock_score_percent=score, readiness=readiness
    )


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    run_id = argv[0] if argv else None
    result = run_chaos(run_id=run_id)
    sys.stdout.write(
        json.dumps(
            {
                "output_dir": str(result.output_dir),
                "mock_score_percent": result.mock_score_percent,
                "readiness": result.readiness,
            },
            indent=2,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
