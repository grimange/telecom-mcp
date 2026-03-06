"""Agent integration readiness pipeline runner (A0-A5)."""

from __future__ import annotations

import io
import json
import logging
import re
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from telecom_mcp.chaos.injectors.faults import patched_attr
from telecom_mcp.chaos.validators.audit import parse_jsonl_lines
from telecom_mcp.chaos.validators.envelope import (
    REQUIRED_ENVELOPE_KEYS,
    validate_envelope,
)
from telecom_mcp.config import load_settings
from telecom_mcp.connectors.asterisk_ami import AsteriskAMIConnector
from telecom_mcp.connectors.asterisk_ari import AsteriskARIConnector
from telecom_mcp.connectors.freeswitch_esl import FreeSWITCHESLConnector
from telecom_mcp.server import TelecomMCPServer


@dataclass(slots=True)
class AgentReadinessRunResult:
    output_dir: Path
    score: float
    passed: bool


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
    return root / (run_id or _utc_stamp())


def _new_server(
    targets_file: str,
    *,
    mode: str = "inspect",
    write_allowlist: list[str] | None = None,
    cooldown_seconds: int = 60,
) -> TelecomMCPServer:
    settings = load_settings(
        targets_file,
        mode=mode,
        write_allowlist=write_allowlist or [],
        cooldown_seconds=cooldown_seconds,
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
            tool_name=tool_name, args=args, correlation_id=correlation_id
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

    def ami_send_action(
        self: AsteriskAMIConnector, action: dict[str, Any]
    ) -> dict[str, Any]:
        name = str(action.get("Action", ""))
        if name == "PJSIPShowEndpoint":
            endpoint = str(action.get("Endpoint", "1001"))
            return {
                "endpoint": endpoint,
                "state": "Available",
                "aor": endpoint,
                "contacts": [
                    {
                        "uri": f"sip:{endpoint}@10.0.0.10:5060",
                        "status": "Avail",
                        "rtt_ms": 12,
                    }
                ],
            }
        if name == "PJSIPShowEndpoints":
            return {
                "endpoint": "1001",
                "state": "Available",
                "contacts": 1,
            }
        if name == "CoreShowChannels":
            return {
                "name": "PJSIP/1001-00000001",
                "state": "Up",
                "caller": "1001",
                "callee": "15551234567",
                "duration_s": 42,
            }
        if name == "Command":
            return {"Response": "Success", "Message": "Command successfully executed"}
        return {"Response": "Success", "Message": "OK"}

    def ari_health(self: AsteriskARIConnector) -> dict[str, Any]:
        return {"ok": True, "latency_ms": 11, "raw": {"system": {"version": "20.7.0"}}}

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
            return [
                {
                    "id": "bridge-1",
                    "technology": "simple_bridge",
                    "channels": ["chan-1", "chan-2"],
                }
            ]
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
        if cmd_norm == "reloadxml":
            return "+OK reloadxml"
        return "+OK"

    with (
        patched_attr(AsteriskAMIConnector, "ping", ami_ping),
        patched_attr(AsteriskAMIConnector, "send_action", ami_send_action),
        patched_attr(AsteriskARIConnector, "health", ari_health),
        patched_attr(AsteriskARIConnector, "get", ari_get),
        patched_attr(FreeSWITCHESLConnector, "ping", esl_ping),
        patched_attr(FreeSWITCHESLConnector, "api", esl_api),
    ):
        yield


def _a0_preflight(out_dir: Path) -> dict[str, Any]:
    required_files = [
        "AGENTS.md",
        "docs/telecom-mcp-implementation-plan.md",
        "docs/telecom-mcp-tool-specification.md",
        "docs/prompts/stage--06--agent-integration-readiness-prompt.md",
        "scripts/agent_readiness_check.py",
    ]
    checks = {path: Path(path).exists() for path in required_files}
    checks["stage06_prompt_non_empty"] = (
        Path("docs/prompts/stage--06--agent-integration-readiness-prompt.md")
        .read_text(encoding="utf-8")
        .strip()
        != ""
    )
    payload = {
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "checks": checks,
        "pass": all(checks.values()),
    }
    _write_json(out_dir / "evidence/preflight.json", payload)
    return payload


def _a1_tool_contract_smoke(server: TelecomMCPServer, out_dir: Path) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    cases = [
        ("telecom.list_targets", {}, "c-agent-a1-1"),
        ("telecom.summary", {"pbx_id": "pbx-1"}, "c-agent-a1-2"),
        ("telecom.capture_snapshot", {"pbx_id": "pbx-1"}, "c-agent-a1-3"),
        ("asterisk.health", {"pbx_id": "pbx-1"}, "c-agent-a1-4"),
        (
            "asterisk.pjsip_show_endpoint",
            {"pbx_id": "pbx-1", "endpoint": "1001"},
            "c-agent-a1-5",
        ),
        ("asterisk.pjsip_show_endpoints", {"pbx_id": "pbx-1"}, "c-agent-a1-6"),
        ("freeswitch.health", {"pbx_id": "fs-1"}, "c-agent-a1-7"),
        ("freeswitch.sofia_status", {"pbx_id": "fs-1"}, "c-agent-a1-8"),
    ]

    with _happy_path_connectors():
        for tool_name, args, correlation_id in cases:
            env, _ = _run_with_audit(server, tool_name, args, correlation_id)
            env_issues = validate_envelope(env)
            checks.append(
                {
                    "tool": tool_name,
                    "ok": env.get("ok") is True,
                    "envelope_issues": env_issues,
                    "has_required_keys": REQUIRED_ENVELOPE_KEYS.issubset(
                        set(env.keys())
                    ),
                    "has_data_object": isinstance(env.get("data"), dict),
                }
            )

    passed = sum(
        1
        for row in checks
        if row["ok"] and not row["envelope_issues"] and row["has_data_object"]
    )
    payload = {
        "checks": checks,
        "passed": passed,
        "total": len(checks),
        "pass": passed == len(checks),
    }
    _write_json(out_dir / "evidence/tool-contract-smoke.json", payload)
    return payload


def _a2_error_contract(server: TelecomMCPServer, out_dir: Path) -> dict[str, Any]:
    cases = [
        ("unknown.tool", {}, "NOT_FOUND"),
        ("telecom.summary", {}, "VALIDATION_ERROR"),
        ("asterisk.health", {"pbx_id": "missing"}, "NOT_FOUND"),
    ]
    rows: list[dict[str, Any]] = []
    for idx, (tool_name, args, expected_code) in enumerate(cases, start=1):
        env, _ = _run_with_audit(server, tool_name, args, f"c-agent-a2-{idx}")
        row = {
            "tool": tool_name,
            "expected_error_code": expected_code,
            "actual_error_code": (env.get("error") or {}).get("code"),
            "ok_is_false": env.get("ok") is False,
            "envelope_issues": validate_envelope(env),
        }
        rows.append(row)

    passed = sum(
        1
        for row in rows
        if row["ok_is_false"]
        and row["expected_error_code"] == row["actual_error_code"]
        and not row["envelope_issues"]
    )
    payload = {
        "cases": rows,
        "passed": passed,
        "total": len(rows),
        "pass": passed == len(rows),
    }
    _write_json(out_dir / "evidence/error-contract.json", payload)
    return payload


def _a3_mode_gating(targets_file: str, out_dir: Path) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    inspect_server = _new_server(targets_file, mode="inspect")
    inspect_env = inspect_server.execute_tool(
        tool_name="asterisk.reload_pjsip",
        args={"pbx_id": "pbx-1"},
        correlation_id="c-agent-a3-inspect",
    )
    checks["inspect_blocks_write"] = (inspect_env.get("error") or {}).get(
        "code"
    ) == "NOT_ALLOWED"

    safe_no_allowlist = _new_server(targets_file, mode="execute_safe")
    no_allow_env = safe_no_allowlist.execute_tool(
        tool_name="asterisk.reload_pjsip",
        args={"pbx_id": "pbx-1"},
        correlation_id="c-agent-a3-no-allowlist",
    )
    checks["execute_safe_requires_allowlist"] = (no_allow_env.get("error") or {}).get(
        "code"
    ) == "NOT_ALLOWED"

    safe_with_allowlist = _new_server(
        targets_file,
        mode="execute_safe",
        write_allowlist=["asterisk.reload_pjsip"],
        cooldown_seconds=300,
    )
    with _happy_path_connectors():
        first_env = safe_with_allowlist.execute_tool(
            tool_name="asterisk.reload_pjsip",
            args={"pbx_id": "pbx-1"},
            correlation_id="c-agent-a3-allowlisted",
        )
        second_env = safe_with_allowlist.execute_tool(
            tool_name="asterisk.reload_pjsip",
            args={"pbx_id": "pbx-1"},
            correlation_id="c-agent-a3-cooldown",
        )

    checks["allowlisted_write_executes"] = first_env.get("ok") is True
    checks["cooldown_enforced"] = (second_env.get("error") or {}).get(
        "code"
    ) == "NOT_ALLOWED"

    payload = {
        "checks": checks,
        "details": {
            "inspect_error": inspect_env.get("error"),
            "no_allowlist_error": no_allow_env.get("error"),
            "allowlisted_ok": first_env.get("ok"),
            "cooldown_error": second_env.get("error"),
        },
        "pass": all(checks.values()),
    }
    _write_json(out_dir / "evidence/mode-gating.json", payload)
    return payload


def _a4_agent_workflow(server: TelecomMCPServer, out_dir: Path) -> dict[str, Any]:
    calls: list[tuple[str, dict[str, Any], str]] = [
        ("telecom.list_targets", {}, "c-agent-a4-1"),
        ("telecom.summary", {"pbx_id": "pbx-1"}, "c-agent-a4-2"),
        (
            "telecom.capture_snapshot",
            {"pbx_id": "pbx-1", "limits": {"max_items": 50}},
            "c-agent-a4-3",
        ),
    ]

    envelopes: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    with _happy_path_connectors():
        for tool_name, args, cid in calls:
            env, rows = _run_with_audit(server, tool_name, args, cid)
            envelopes.append(env)
            audit_rows.extend(rows)

    correlation_ok = all(
        any(row.get("correlation_id") == cid for row in audit_rows)
        for _, _, cid in calls
    ) and all(
        env.get("correlation_id") in {cid for _, _, cid in calls} for env in envelopes
    )

    json_roundtrip_ok = all(
        isinstance(json.loads(json.dumps(env)), dict) for env in envelopes
    )
    all_ok = all(env.get("ok") is True for env in envelopes)

    sample_path = out_dir / "evidence/audit-log-sample.jsonl"
    sample_path.parent.mkdir(parents=True, exist_ok=True)
    with sample_path.open("w", encoding="utf-8") as fh:
        for row in audit_rows:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")

    payload = {
        "checks": {
            "workflow_calls_succeeded": all_ok,
            "correlation_id_roundtrip": correlation_ok,
            "envelope_json_roundtrip": json_roundtrip_ok,
        },
        "calls": [
            {
                "tool": call[0],
                "correlation_id": call[2],
                "ok": env.get("ok"),
            }
            for call, env in zip(calls, envelopes)
        ],
        "pass": all_ok and correlation_ok and json_roundtrip_ok,
    }
    _write_json(out_dir / "evidence/agent-workflow.json", payload)
    return payload


def _a5_docs_examples(out_dir: Path) -> dict[str, Any]:
    required_docs = [
        "docs/examples.md",
        "docs/tools.md",
        "docs/runbook.md",
        "docs/security.md",
        "docs/prompts/stage--06--agent-integration-readiness-prompt.md",
    ]
    docs_exist = all(
        Path(path).exists() and Path(path).read_text(encoding="utf-8").strip()
        for path in required_docs
    )

    examples_text = Path("docs/examples.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```json\n(.*?)\n```", examples_text, flags=re.S)
    parsed = 0
    for block in blocks:
        obj = json.loads(block)
        if isinstance(obj, dict) and "tool" in obj and "args" in obj:
            parsed += 1

    payload = {
        "checks": {
            "required_docs_present": docs_exist,
            "examples_json_parseable": parsed == len(blocks) and parsed > 0,
        },
        "examples": {"json_blocks": len(blocks), "valid_blocks": parsed},
        "pass": docs_exist and parsed == len(blocks) and parsed > 0,
    }
    _write_json(out_dir / "evidence/docs-check.json", payload)
    return payload


def _score_and_report(
    out_dir: Path,
    a0: dict[str, Any],
    a1: dict[str, Any],
    a2: dict[str, Any],
    a3: dict[str, Any],
    a4: dict[str, Any],
    a5: dict[str, Any],
) -> tuple[float, bool]:
    s0 = 15.0 if a0["pass"] else 0.0
    s1 = round((a1["passed"] / max(a1["total"], 1)) * 35.0, 2)
    s2 = round((a2["passed"] / max(a2["total"], 1)) * 15.0, 2)
    s3_ratio = sum(1 for ok in a3["checks"].values() if ok) / max(len(a3["checks"]), 1)
    s3 = round(s3_ratio * 20.0, 2)
    s4_ratio = sum(1 for ok in a4["checks"].values() if ok) / max(len(a4["checks"]), 1)
    s4 = round(s4_ratio * 10.0, 2)
    s5_ratio = sum(1 for ok in a5["checks"].values() if ok) / max(len(a5["checks"]), 1)
    s5 = round(s5_ratio * 5.0, 2)

    score = round(s0 + s1 + s2 + s3 + s4 + s5, 2)
    passed = score >= 90.0

    findings: list[str] = []
    if not a0["pass"]:
        findings.append(
            "A0 preflight failed: required docs/scripts are missing or Stage 06 prompt is empty."
        )
    if a1["passed"] != a1["total"]:
        findings.append(
            f"A1 tool contract smoke has failures ({a1['passed']}/{a1['total']})."
        )
    if a2["passed"] != a2["total"]:
        findings.append(
            f"A2 error contract mapping has failures ({a2['passed']}/{a2['total']})."
        )
    if not a3["pass"]:
        findings.append("A3 mode gating failed for at least one safety guardrail.")
    if not a4["pass"]:
        findings.append(
            "A4 agent workflow simulation failed (success/correlation/serialization)."
        )
    if not a5["pass"]:
        findings.append("A5 docs/examples checks failed.")

    scorecard = "\n".join(
        [
            "# Agent Readiness Scorecard",
            "",
            f"- Timestamp: {datetime.now(UTC).isoformat().replace('+00:00', 'Z')}",
            f"- Total score: {score}/100",
            f"- Gate result: {'PASS' if passed else 'FAIL'}",
            "",
            "## Breakdown",
            f"- A0 Preflight: {s0}/15",
            f"- A1 Tool Contract Smoke: {s1}/35",
            f"- A2 Error Contract: {s2}/15",
            f"- A3 Mode Gating: {s3}/20",
            f"- A4 Agent Workflow: {s4}/10",
            f"- A5 Docs and Examples: {s5}/5",
            "",
            "## Gate",
            "- Pass threshold: >= 90",
        ]
    )
    _write_text(out_dir / "scorecard.md", scorecard + "\n")

    findings_md = ["# Agent Readiness Findings", ""]
    if findings:
        findings_md.append("## Issues")
        findings_md.extend([f"- {item}" for item in findings])
    else:
        findings_md.append("- No readiness findings. All phase gates passed.")
    _write_text(out_dir / "findings.md", "\n".join(findings_md) + "\n")

    if findings:
        remediation = [
            "# Agent Readiness Remediation",
            "",
            "1. Fix failing phase checks listed in findings.md.",
            "2. Re-run `python scripts/agent_readiness_check.py`.",
            "3. Do not lower safety gates to pass scoring.",
        ]
        _write_text(out_dir / "remediation.md", "\n".join(remediation) + "\n")

    return score, passed


def run_agent_readiness(
    *,
    run_id: str | None = None,
    output_root: str = "docs/audit/agent-readiness",
    targets_file: str = "targets.yaml",
) -> AgentReadinessRunResult:
    out_dir = _base_output_dir(Path(output_root), run_id)
    out_dir.mkdir(parents=True, exist_ok=False)

    server = _new_server(targets_file, mode="inspect")

    a0 = _a0_preflight(out_dir)
    a1 = _a1_tool_contract_smoke(server, out_dir)
    a2 = _a2_error_contract(server, out_dir)
    a3 = _a3_mode_gating(targets_file, out_dir)
    a4 = _a4_agent_workflow(server, out_dir)
    a5 = _a5_docs_examples(out_dir)

    score, passed = _score_and_report(out_dir, a0, a1, a2, a3, a4, a5)
    return AgentReadinessRunResult(output_dir=out_dir, score=score, passed=passed)
