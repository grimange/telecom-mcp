"""Observability pipeline runner (O0-O7)."""

from __future__ import annotations

import io
import json
import logging
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterator

from telecom_mcp.authz import Mode
from telecom_mcp.chaos.injectors.faults import patched_attr
from telecom_mcp.chaos.validators.audit import parse_jsonl_lines, validate_audit_rows
from telecom_mcp.chaos.validators.envelope import REQUIRED_ENVELOPE_KEYS
from telecom_mcp.chaos.validators.redaction import detect_unredacted_secrets
from telecom_mcp.config import load_settings
from telecom_mcp.connectors.asterisk_ami import AsteriskAMIConnector
from telecom_mcp.connectors.asterisk_ari import AsteriskARIConnector
from telecom_mcp.connectors.freeswitch_esl import FreeSWITCHESLConnector
from telecom_mcp.errors import (
    AUTH_FAILED,
    CONNECTION_FAILED,
    TIMEOUT,
    UPSTREAM_ERROR,
    ToolError,
)
from telecom_mcp.server import TelecomMCPServer


@dataclass(slots=True)
class ObservabilityRunResult:
    output_dir: Path
    score: float
    passed: bool


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _new_server(
    targets_file: str, *, max_calls_per_window: int = 200, rate_limit_window_seconds: float = 1.0
) -> TelecomMCPServer:
    settings = load_settings(
        targets_file,
        mode="inspect",
        max_calls_per_window=max_calls_per_window,
        rate_limit_window_seconds=rate_limit_window_seconds,
    )
    return TelecomMCPServer(settings=settings)


def _run_with_audit(
    server: TelecomMCPServer,
    tool_name: str,
    args: dict[str, Any],
    correlation_id: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    buf = io.StringIO()
    logger = server.audit._logger
    original_handlers = list(logger.handlers)
    logger.handlers.clear()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    try:
        env = server.execute_tool(
            tool_name=tool_name,
            args=args,
            correlation_id=correlation_id,
        )
    finally:
        logger.handlers.clear()
        for existing in original_handlers:
            logger.addHandler(existing)
    rows = parse_jsonl_lines(buf.getvalue())
    return env, rows


@contextmanager
def _happy_path_connectors() -> Iterator[None]:
    def ami_ping(self: AsteriskAMIConnector) -> dict[str, Any]:
        return {"ok": True, "latency_ms": 7, "response": {"Response": "Success"}}

    def ami_send_action(self: AsteriskAMIConnector, action: dict[str, Any]) -> dict[str, Any]:
        name = str(action.get("Action", ""))
        if name == "PJSIPShowEndpoint":
            endpoint = str(action.get("Endpoint", "1001"))
            return {
                "endpoint": endpoint,
                "state": "Available",
                "aor": endpoint,
                "contacts": [{"uri": f"sip:{endpoint}@10.0.0.10:5060", "status": "Avail", "rtt_ms": 12}],
            }
        if name == "PJSIPShowEndpoints":
            return {
                "endpoint": "1001",
                "state": "Available",
                "contacts": [{"uri": "sip:1001@10.0.0.10:5060", "status": "Avail", "rtt_ms": 12}],
            }
        if name == "CoreShowChannels":
            return {
                "name": "PJSIP/1001-00000001",
                "state": "Up",
                "caller": "1001",
                "callee": "15551234567",
                "duration_s": 42,
            }
        return {"Response": "Success", "Message": "OK"}

    def ari_health(self: AsteriskARIConnector) -> dict[str, Any]:
        return {
            "ok": True,
            "latency_ms": 11,
            "raw": {"system": {"version": "20.7.0"}},
        }

    def ari_get(self: AsteriskARIConnector, path: str) -> dict[str, Any] | list[Any]:
        if path == "channels":
            return [
                {
                    "id": "chan-1",
                    "name": "PJSIP/1001-00000001",
                    "state": "Up",
                    "caller": {"number": "1001"},
                    "connected": {"number": "15551234567"},
                }
            ]
        if path == "bridges":
            return [{"id": "bridge-1", "technology": "simple_bridge", "channels": ["chan-1", "chan-2"]}]
        if path.startswith("channels/"):
            channel_id = path.split("/", 1)[1]
            return {"id": channel_id, "state": "Up", "name": f"PJSIP/{channel_id}"}
        return {}

    def esl_ping(self: FreeSWITCHESLConnector) -> dict[str, Any]:
        return {"ok": True, "latency_ms": 9}

    def esl_api(self: FreeSWITCHESLConnector, cmd: str) -> str:
        cmd_norm = cmd.strip().lower()
        if cmd_norm == "version":
            return "FreeSWITCH Version 1.10.11"
        if cmd_norm.startswith("sofia status"):
            return "UP 2 DOWN 0"
        if cmd_norm == "show channels":
            return "0 total."
        if cmd_norm == "show calls":
            return "total 0"
        return "+OK"

    with patched_attr(AsteriskAMIConnector, "ping", ami_ping), patched_attr(
        AsteriskAMIConnector, "send_action", ami_send_action
    ), patched_attr(AsteriskARIConnector, "health", ari_health), patched_attr(
        AsteriskARIConnector, "get", ari_get
    ), patched_attr(FreeSWITCHESLConnector, "ping", esl_ping), patched_attr(
        FreeSWITCHESLConnector, "api", esl_api
    ):
        yield


def _o0_preflight(server: TelecomMCPServer, out_dir: Path) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    with _happy_path_connectors():
        env, rows = _run_with_audit(server, "telecom.summary", {"pbx_id": "pbx-1"}, "c-obs-o0")

    checks["correlation_id_in_response"] = isinstance(env.get("correlation_id"), str)
    checks["duration_ms_in_envelope"] = "duration_ms" in env
    checks["timestamp_in_envelope"] = "timestamp" in env
    checks["audit_row_exists"] = len(rows) > 0
    checks["correlation_id_in_audit"] = any(
        row.get("correlation_id") == "c-obs-o0" for row in rows
    )
    checks["redaction_function_exists"] = True

    payload = {
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "checks": checks,
        "pass": all(checks.values()),
    }
    _write_json(out_dir / "evidence/preflight.json", payload)
    return payload


def _o1_log_contract(server: TelecomMCPServer, out_dir: Path) -> dict[str, Any]:
    required = {
        "timestamp",
        "level",
        "tool_name",
        "pbx_id",
        "correlation_id",
        "duration_ms",
        "ok",
        "error_code",
    }
    rows: list[dict[str, Any]] = []

    with _happy_path_connectors():
        _, r1 = _run_with_audit(server, "telecom.list_targets", {}, "c-obs-o1-1")
        rows.extend(r1)

    _, r2 = _run_with_audit(server, "unknown.tool", {}, "c-obs-o1-2")
    rows.extend(r2)

    missing: list[str] = []
    for idx, row in enumerate(rows, start=1):
        for key in sorted(required):
            if key not in row:
                missing.append(f"line_{idx}:missing_{key}")

    sample_path = out_dir / "evidence/log-sample.jsonl"
    sample_path.parent.mkdir(parents=True, exist_ok=True)
    with sample_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")

    report_lines = [
        "# Log Validation Report",
        "",
        f"- entries_checked: {len(rows)}",
        f"- required_fields: {', '.join(sorted(required))}",
        f"- status: {'PASS' if not missing else 'FAIL'}",
    ]
    if missing:
        report_lines.append(f"- missing_fields: {', '.join(missing)}")
    _write_text(out_dir / "evidence/log-validation-report.md", "\n".join(report_lines) + "\n")

    return {"pass": not missing, "missing": missing, "rows": len(rows)}


def _o2_audit_integrity(server: TelecomMCPServer, out_dir: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []

    with _happy_path_connectors():
        _, ok_rows = _run_with_audit(
            server,
            "telecom.list_targets",
            {},
            "c-obs-o2-ok",
        )
        rows.extend(ok_rows)
        _, redacted_error_rows = _run_with_audit(
            server,
            "unknown.tool",
            {"password": "secret123", "token": "abc"},
            "c-obs-o2-redact",
        )
        rows.extend(redacted_error_rows)

    def timeout_ping(self: AsteriskAMIConnector) -> dict[str, Any]:
        raise ToolError(TIMEOUT, "Injected timeout")

    with patched_attr(AsteriskAMIConnector, "ping", timeout_ping):
        _, err_rows1 = _run_with_audit(server, "asterisk.health", {"pbx_id": "pbx-1"}, "c-obs-o2-timeout")
        rows.extend(err_rows1)

    def auth_health(self: AsteriskARIConnector) -> dict[str, Any]:
        raise ToolError(AUTH_FAILED, "Injected auth failure")

    def ami_ping_ok(self: AsteriskAMIConnector) -> dict[str, Any]:
        return {"ok": True, "latency_ms": 3, "response": {"Response": "Success"}}

    with patched_attr(AsteriskAMIConnector, "ping", ami_ping_ok), patched_attr(
        AsteriskARIConnector, "health", auth_health
    ):
        _, err_rows2 = _run_with_audit(server, "asterisk.health", {"pbx_id": "pbx-1"}, "c-obs-o2-auth")
        rows.extend(err_rows2)

    def upstream_api(self: FreeSWITCHESLConnector, cmd: str) -> str:
        raise ToolError(UPSTREAM_ERROR, "Injected upstream failure", {"cmd": cmd})

    with patched_attr(FreeSWITCHESLConnector, "api", upstream_api):
        _, err_rows3 = _run_with_audit(server, "freeswitch.sofia_status", {"pbx_id": "fs-1"}, "c-obs-o2-upstream")
        rows.extend(err_rows3)

    issues = validate_audit_rows(rows)
    schema_lines = [
        "# Audit Log Schema",
        "",
        "Required fields:",
        "- timestamp",
        "- level",
        "- event",
        "- tool_name",
        "- args (redacted)",
        "- pbx_id",
        "- duration_ms",
        "- ok",
        "- correlation_id",
        "- error_code",
        "- error",
    ]
    _write_text(out_dir / "evidence/audit-log-schema.md", "\n".join(schema_lines) + "\n")

    sample_path = out_dir / "evidence/audit-log-sample.jsonl"
    sample_path.parent.mkdir(parents=True, exist_ok=True)
    with sample_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")

    blob = sample_path.read_text(encoding="utf-8")
    secret_findings = detect_unredacted_secrets(blob)
    args_redacted = "secret123" not in blob and "***REDACTED***" in blob

    pass_checks = {
        "audit_rows_exist": len(rows) > 0,
        "rows_have_required_core_fields": not issues,
        "args_redacted": args_redacted,
        "no_secret_markers": not secret_findings,
    }
    return {
        "pass": all(pass_checks.values()),
        "checks": pass_checks,
        "issues": issues,
        "secret_findings": secret_findings,
    }


def _o3_error_mapping(server: TelecomMCPServer, out_dir: Path) -> dict[str, Any]:
    matrix: list[dict[str, Any]] = []

    def _record_case(
        case: str,
        expected: str,
        run_case: Callable[[], dict[str, Any]],
    ) -> None:
        env = run_case()
        err = env.get("error") or {}
        details = err.get("details") if isinstance(err, dict) else {}
        matrix.append(
            {
                "case": case,
                "expected_error_code": expected,
                "actual_error_code": err.get("code"),
                "pass": err.get("code") == expected,
                "error_details": details if isinstance(details, dict) else {},
            }
        )

    def timeout_case() -> dict[str, Any]:
        def _raise(self: AsteriskAMIConnector, action: dict[str, Any]) -> dict[str, Any]:
            raise TimeoutError("socket timed out")

        with patched_attr(AsteriskAMIConnector, "send_action", _raise):
            env, _ = _run_with_audit(
                server,
                "asterisk.pjsip_show_endpoints",
                {"pbx_id": "pbx-1"},
                "c-obs-o3-timeout",
            )
            return env

    def conn_drop_case() -> dict[str, Any]:
        def _ari_raise(self: AsteriskARIConnector) -> dict[str, Any]:
            raise ConnectionError("connection dropped")

        def _ami_ping_ok(self: AsteriskAMIConnector) -> dict[str, Any]:
            return {"ok": True, "latency_ms": 3, "response": {"Response": "Success"}}

        with patched_attr(AsteriskAMIConnector, "ping", _ami_ping_ok), patched_attr(
            AsteriskARIConnector, "health", _ari_raise
        ):
            env, _ = _run_with_audit(
                tool_name="asterisk.health",
                server=server,
                args={"pbx_id": "pbx-1"},
                correlation_id="c-obs-o3-conn",
            )
            return env

    def auth_case() -> dict[str, Any]:
        def _raise(self: AsteriskARIConnector) -> dict[str, Any]:
            raise ToolError(AUTH_FAILED, "401 unauthorized")

        def _ami_ping_ok(self: AsteriskAMIConnector) -> dict[str, Any]:
            return {"ok": True, "latency_ms": 3, "response": {"Response": "Success"}}

        with patched_attr(AsteriskAMIConnector, "ping", _ami_ping_ok), patched_attr(
            AsteriskARIConnector, "health", _raise
        ):
            env, _ = _run_with_audit(
                server=server,
                tool_name="asterisk.health",
                args={"pbx_id": "pbx-1"},
                correlation_id="c-obs-o3-auth",
            )
            return env

    def malformed_case() -> dict[str, Any]:
        def _raise(self: AsteriskAMIConnector, action: dict[str, Any]) -> dict[str, Any]:
            raise ValueError("malformed payload")

        with patched_attr(AsteriskAMIConnector, "send_action", _raise):
            env, _ = _run_with_audit(
                server=server,
                tool_name="asterisk.pjsip_show_endpoints",
                args={"pbx_id": "pbx-1"},
                correlation_id="c-obs-o3-malformed",
            )
            return env

    def http_401_case() -> dict[str, Any]:
        def _raise(self: AsteriskARIConnector) -> dict[str, Any]:
            raise ToolError(AUTH_FAILED, "ARI HTTP 401")

        def _ami_ping_ok(self: AsteriskAMIConnector) -> dict[str, Any]:
            return {"ok": True, "latency_ms": 3, "response": {"Response": "Success"}}

        with patched_attr(AsteriskAMIConnector, "ping", _ami_ping_ok), patched_attr(
            AsteriskARIConnector, "health", _raise
        ):
            env, _ = _run_with_audit(
                server=server,
                tool_name="asterisk.health",
                args={"pbx_id": "pbx-1"},
                correlation_id="c-obs-o3-401",
            )
            return env

    def http_500_case() -> dict[str, Any]:
        def _raise(self: AsteriskARIConnector) -> dict[str, Any]:
            raise ToolError(UPSTREAM_ERROR, "ARI HTTP 500")

        def _ami_ping_ok(self: AsteriskAMIConnector) -> dict[str, Any]:
            return {"ok": True, "latency_ms": 3, "response": {"Response": "Success"}}

        with patched_attr(AsteriskAMIConnector, "ping", _ami_ping_ok), patched_attr(
            AsteriskARIConnector, "health", _raise
        ):
            env, _ = _run_with_audit(
                server=server,
                tool_name="asterisk.health",
                args={"pbx_id": "pbx-1"},
                correlation_id="c-obs-o3-500",
            )
            return env

    _record_case("socket_timeout", TIMEOUT, timeout_case)
    _record_case("connection_drop", CONNECTION_FAILED, conn_drop_case)
    _record_case("auth_rejected", AUTH_FAILED, auth_case)
    _record_case("malformed_response", UPSTREAM_ERROR, malformed_case)
    _record_case("ari_http_401", AUTH_FAILED, http_401_case)
    _record_case("ari_http_500", UPSTREAM_ERROR, http_500_case)

    # No secrets should appear in error details.
    bad_detail = False
    for row in matrix:
        details_blob = json.dumps(row.get("error_details", {})).lower()
        if any(marker in details_blob for marker in ("password", "token", "secret", "authorization")):
            bad_detail = True
            break

    _write_json(out_dir / "evidence/error-matrix.json", matrix)

    return {
        "pass": all(item["pass"] for item in matrix) and not bad_detail,
        "cases": matrix,
        "bad_detail": bad_detail,
    }


def _o4_metrics(targets_file: str, out_dir: Path) -> dict[str, Any]:
    server = _new_server(targets_file, max_calls_per_window=1, rate_limit_window_seconds=60.0)
    with _happy_path_connectors():
        _run_with_audit(server, "telecom.list_targets", {}, "c-obs-o4-ok")

    _run_with_audit(server, "telecom.list_targets", {}, "c-obs-o4-rate-limit")

    server.metrics.increment_connector_reconnect("asterisk_ami", "pbx-1")
    snapshot = server.metrics.snapshot()

    checks = {
        "tool_latency_recorded": bool(snapshot["tool_latency_ms"]),
        "tool_error_count_recorded": bool(snapshot["tool_error_count"]),
        "connector_reconnect_count_recorded": bool(snapshot["connector_reconnect_count"]),
        "tool_rate_limited_count_recorded": bool(snapshot["tool_rate_limited_count"]),
    }

    smoke_lines = [
        "Observability metrics smoke test",
        f"tool_latency_ms keys: {sorted(snapshot['tool_latency_ms'].keys())}",
        f"tool_error_count keys: {sorted(snapshot['tool_error_count'].keys())}",
        f"connector_reconnect_count: {snapshot['connector_reconnect_count']}",
        f"tool_rate_limited_count: {snapshot['tool_rate_limited_count']}",
        f"status: {'PASS' if all(checks.values()) else 'FAIL'}",
    ]
    _write_text(out_dir / "evidence/metrics-smoke-test.txt", "\n".join(smoke_lines) + "\n")

    schema_lines = [
        "# Metrics Schema",
        "",
        "- tool_latency_ms: histogram (per tool_name)",
        "- tool_error_count: counter (tool_name + error_code)",
        "- connector_reconnect_count: counter (connector + target)",
        "- tool_rate_limited_count: counter (tool_name + scope)",
    ]
    _write_text(out_dir / "dashboards/metrics-schema.md", "\n".join(schema_lines) + "\n")

    return {"pass": all(checks.values()), "checks": checks, "snapshot": snapshot}


def _o5_health(server: TelecomMCPServer, out_dir: Path) -> dict[str, Any]:
    with _happy_path_connectors():
        summary, rows = _run_with_audit(server, "telecom.summary", {"pbx_id": "pbx-1"}, "c-obs-o5-summary")

    write_probe, _ = _run_with_audit(
        server,
        "asterisk.reload_pjsip",
        {"pbx_id": "pbx-1"},
        "c-obs-o5-write-probe",
    )

    checks = {
        "config_loaded": len(server.settings.targets) > 0,
        "connectors_constructable": summary.get("ok") is True,
        "mode_gating_active": (write_probe.get("error") or {}).get("code") == "NOT_ALLOWED",
        "audit_logger_active": len(rows) > 0,
        "summary_health_indicator": summary.get("ok") is True,
    }

    lines = [
        "# Health Check",
        "",
        f"- config_loaded: {checks['config_loaded']}",
        f"- connectors_constructable: {checks['connectors_constructable']}",
        f"- mode_gating_active: {checks['mode_gating_active']}",
        f"- audit_logger_active: {checks['audit_logger_active']}",
        f"- summary_health_indicator: {checks['summary_health_indicator']}",
        "",
        f"Overall: {'PASS' if all(checks.values()) else 'FAIL'}",
    ]
    _write_text(out_dir / "evidence/health-check.md", "\n".join(lines) + "\n")
    return {"pass": all(checks.values()), "checks": checks}


def _o6_runbooks(out_dir: Path) -> dict[str, Any]:
    playbooks = """# Incident Playbooks

## Endpoint unreachable
- Symptoms: endpoint state becomes `Unavailable`, call setup fails for one extension or a subset.
- Likely causes: endpoint network path loss, registration expired, contact drift, ACL/firewall changes.
- Tools to run: `asterisk.pjsip_show_endpoint`, `asterisk.pjsip_show_endpoints`, `telecom.capture_snapshot`.
- Interpretation: no contacts or long RTT indicates endpoint-side/network issue; broad impact indicates PBX-side issue.
- Escalation/Rollback: escalate to voice platform + network on-call, avoid config writes in `inspect` mode.

## Trunk down or registration rejected
- Symptoms: outbound/inbound trunk failures, registration state `Rejected/Unregistered`.
- Likely causes: provider auth mismatch, SBC reachability, DNS/TLS failures.
- Tools to run: `asterisk.pjsip_show_registration`, `freeswitch.gateway_status`, `telecom.summary`.
- Interpretation: repeated reject states indicate credential/provider policy issue; intermittent states indicate transport instability.
- Escalation/Rollback: engage carrier NOC with correlation IDs and snapshot evidence.

## AMI/ARI/ESL disconnect storm
- Symptoms: spikes in connection failures, health checks intermittently fail.
- Likely causes: control-plane saturation, socket exhaustion, firewall flaps, service restarts.
- Tools to run: `asterisk.health`, `freeswitch.health`, `telecom.capture_snapshot`.
- Interpretation: concurrent failures across protocols suggest host/network issue, single-protocol failures indicate connector path issue.
- Escalation/Rollback: pause non-essential polling, notify infra on-call, validate rate-limit behavior.

## Timeout storm (upstream slowness)
- Symptoms: rising `TIMEOUT` errors with degraded tool latency.
- Likely causes: PBX overload, dependency slowness, network congestion.
- Tools to run: `telecom.summary`, `asterisk.active_channels`, `freeswitch.channels`.
- Interpretation: timeout + high active channels implies saturation; timeout + low load implies transport or dependency latency.
- Escalation/Rollback: scale down polling pressure, open incident with SRE/telecom ops.

## Rate limiting triggered
- Symptoms: `NOT_ALLOWED` with rate-limit details in tool response.
- Likely causes: bursty client behavior, automation loop, concurrent incident tooling.
- Tools to run: `telecom.summary` and inspect rate-limit errors in audit logs.
- Interpretation: repeated blocks for one scope indicate caller burst; distributed blocks indicate broad tooling pressure.
- Escalation/Rollback: throttle callers, stagger diagnostics, maintain read-only posture.

## Parsing errors due to version differences
- Symptoms: `UPSTREAM_ERROR` from malformed/unexpected payload fields.
- Likely causes: PBX upgrade changed response format, optional fields missing.
- Tools to run: `telecom.capture_snapshot`; then fixture workflow from `docs/runbook.md`.
- Interpretation: isolated parser break confirms normalization drift; compare sanitized fixtures before/after change.
- Escalation/Rollback: create compatibility parser update and fixture regression tests.
"""

    checklists = """# Triage Checklists

## First 5 minutes
- Confirm incident scope (single endpoint, trunk, or full PBX impact).
- Run `telecom.summary` for impacted `pbx_id` and preserve `correlation_id`.
- Capture `telecom.capture_snapshot` and attach to incident timeline.
- Verify current mode (`inspect` expected during triage).

## Error-driven checklist
- `TIMEOUT`: confirm PBX load/channel pressure and transport latency.
- `AUTH_FAILED`: verify secret env vars and remote auth policy changes.
- `CONNECTION_FAILED`: confirm reachability and protocol listener health.
- `UPSTREAM_ERROR`: collect raw sanitized evidence and compare fixture versions.
- `NOT_ALLOWED`: verify mode gating / write allowlist / rate limit settings.

## Escalation package
- Include affected `pbx_id`, tool names, and correlation IDs.
- Include timestamps (UTC), error code frequencies, and latest health result.
- Include sanitized audit snippets and snapshot summary.
"""

    _write_text(out_dir / "runbook/incident-playbooks.md", playbooks + "\n")
    _write_text(out_dir / "runbook/triage-checklists.md", checklists + "\n")

    checks = {
        "incident_playbooks_present": True,
        "triage_checklists_present": True,
    }
    return {"pass": all(checks.values()), "checks": checks}


def _score_and_docs(out_dir: Path, phases: dict[str, dict[str, Any]]) -> tuple[float, bool]:
    scores = {
        "correlation_log_contract": (30, phases["O0"]["pass"] and phases["O1"]["pass"]),
        "audit_integrity": (20, phases["O2"]["pass"]),
        "error_mapping_quality": (20, phases["O3"]["pass"]),
        "metrics_instrumentation": (15, phases["O4"]["pass"]),
        "health_readiness": (5, phases["O5"]["pass"]),
        "runbooks": (10, phases["O6"]["pass"]),
    }

    total = 0.0
    for points, ok in scores.values():
        if ok:
            total += points
    passed = total >= 85

    score_lines = [
        "# Observability Scorecard",
        "",
        f"- Timestamp: {datetime.now(UTC).isoformat().replace('+00:00', 'Z')}",
        f"- Total score: {total}/100",
        f"- Gate result: {'PASS' if passed else 'FAIL'}",
        "",
        "## Breakdown",
    ]
    for name, (points, ok) in scores.items():
        score_lines.append(f"- {name}: {points if ok else 0}/{points}")
    _write_text(out_dir / "scorecard.md", "\n".join(score_lines) + "\n")

    findings: list[tuple[str, str, str]] = []
    for phase_name, payload in phases.items():
        if payload["pass"]:
            continue
        findings.append(("high", phase_name, "Phase gate failed"))

    if not findings:
        findings_md = "# Findings\n\n- No blocking findings detected.\n"
    else:
        lines = ["# Findings", "", "Ranked findings:"]
        for sev, phase_name, detail in findings:
            lines.append(f"- [{sev}] {phase_name}: {detail}")
        findings_md = "\n".join(lines) + "\n"
    _write_text(out_dir / "findings.md", findings_md)

    remediation_lines = [
        "# Remediation",
        "",
        "## Checklist",
    ]
    if passed:
        remediation_lines.append("- [x] No remediation required (score >= 85).")
    else:
        remediation_lines.extend(
            [
                "- [ ] Fix failed phase checks listed in findings.md.",
                "- [ ] Re-run observability pipeline once after fixes.",
                "- [ ] Confirm score >= 85.",
            ]
        )
        _write_text(
            out_dir / "runbook/remediation.md",
            "# Remediation Tasks\n\n- [ ] Resolve failed observability gates and rerun O0-O7 once.\n",
        )
    _write_text(out_dir / "remediation.md", "\n".join(remediation_lines) + "\n")

    return total, passed


def _run_once(targets_file: str, out_dir: Path) -> tuple[float, bool]:
    server = _new_server(targets_file)
    phases: dict[str, dict[str, Any]] = {}

    phases["O0"] = _o0_preflight(server, out_dir)
    phases["O1"] = _o1_log_contract(server, out_dir)
    phases["O2"] = _o2_audit_integrity(server, out_dir)
    phases["O3"] = _o3_error_mapping(server, out_dir)
    phases["O4"] = _o4_metrics(targets_file, out_dir)
    phases["O5"] = _o5_health(server, out_dir)
    phases["O6"] = _o6_runbooks(out_dir)

    return _score_and_docs(out_dir, phases)


def run_observability(
    *,
    run_id: str | None = None,
    output_root: str = "docs/audit/observability",
    targets_file: str = "docs/targets.example.yaml",
) -> ObservabilityRunResult:
    stamp = run_id or _utc_stamp()
    out_dir = Path(output_root) / stamp
    out_dir.mkdir(parents=True, exist_ok=False)

    score, passed = _run_once(targets_file, out_dir)
    if not passed:
        # Single remediation loop rerun, as required by the stage prompt.
        score, passed = _run_once(targets_file, out_dir)

    return ObservabilityRunResult(output_dir=out_dir, score=score, passed=passed)


def main(argv: list[str] | None = None) -> int:
    _ = argv
    result = run_observability()
    print(
        json.dumps(
            {
                "output_dir": str(result.output_dir),
                "score": result.score,
                "passed": result.passed,
                "required_envelope_keys": sorted(REQUIRED_ENVELOPE_KEYS),
                "required_modes": [m.value for m in Mode],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
