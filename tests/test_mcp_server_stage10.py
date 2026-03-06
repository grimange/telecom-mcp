from __future__ import annotations

import inspect
import json
from typing import Any, Callable, get_type_hints

import pytest

from telecom_mcp.errors import VALIDATION_ERROR, ToolError
from telecom_mcp.mcp_server.runtime import load_runtime_flags
from telecom_mcp.mcp_server.server import TelecomMcpSdkServer, build_arg_parser


class _DummyMcp:
    def __init__(self, _name: str) -> None:
        self.tools: dict[str, Callable[..., Any]] = {}
        self.resources: dict[str, Callable[..., Any]] = {}
        self.prompts: dict[str, Callable[..., Any]] = {}

    def tool(self, name: str):
        def _decorator(fn):
            self.tools[name] = fn
            return fn

        return _decorator

    def resource(self, uri: str):
        def _decorator(fn):
            self.resources[uri] = fn
            return fn

        return _decorator

    def prompt(self, name: str):
        def _decorator(fn):
            self.prompts[name] = fn
            return fn

        return _decorator

    def run(self, **_kwargs):
        return None


class _DummyTool:
    def __init__(self, fn: Callable[..., Any]) -> None:
        self.fn = fn


class _DummyToolManager:
    def __init__(self) -> None:
        self._tools: dict[str, _DummyTool] = {}


class _DummyMcpWithToolManager:
    def __init__(self, _name: str) -> None:
        self._tool_manager = _DummyToolManager()
        self.resources: dict[str, Callable[..., Any]] = {}
        self.prompts: dict[str, Callable[..., Any]] = {}

    def tool(self, name: str):
        def _decorator(fn):
            self._tool_manager._tools[name] = _DummyTool(fn)
            return fn

        return _decorator

    def resource(self, uri: str):
        def _decorator(fn):
            self.resources[uri] = fn
            return fn

        return _decorator

    def prompt(self, name: str):
        def _decorator(fn):
            self.prompts[name] = fn
            return fn

        return _decorator

    def run(self, **_kwargs):
        return None


def test_runtime_flag_defaults(monkeypatch) -> None:
    monkeypatch.delenv("TELECOM_MCP_FIXTURES", raising=False)
    monkeypatch.delenv("TELECOM_MCP_ENABLE_REAL_PBX", raising=False)
    monkeypatch.delenv("TELECOM_MCP_TRANSPORT", raising=False)
    monkeypatch.delenv("TELECOM_MCP_STRICT_STARTUP", raising=False)
    monkeypatch.delenv("TELECOM_MCP_REQUIRE_TARGETS_FILE_EXPLICIT", raising=False)
    monkeypatch.delenv("TELECOM_MCP_REQUIRE_CONFIRM_TOKEN", raising=False)

    flags = load_runtime_flags()
    assert flags.fixtures is True
    assert flags.real_pbx is False
    assert flags.transport == "stdio"
    assert flags.strict_startup is False
    assert flags.require_explicit_targets_file is False
    assert flags.require_confirm_token is False


def test_mcp_catalog_registers_v1_telecom_tools(monkeypatch) -> None:
    from telecom_mcp.mcp_server import server as server_mod

    monkeypatch.setattr(server_mod, "_import_mcp_server_class", lambda: _DummyMcp)
    server = TelecomMcpSdkServer(targets_file="/tmp/does-not-exist-targets.yaml")

    required = {
        "telecom.healthcheck",
        "telecom.list_targets",
        "telecom.summary",
        "telecom.capture_snapshot",
        "telecom.endpoints",
        "telecom.registrations",
        "telecom.channels",
        "telecom.calls",
        "telecom.logs",
        "telecom.inventory",
        "telecom.diff_snapshots",
        "telecom.compare_targets",
        "telecom.run_smoke_test",
        "telecom.run_playbook",
        "telecom.run_smoke_suite",
        "telecom.baseline_create",
        "telecom.baseline_show",
        "telecom.audit_target",
        "telecom.drift_target_vs_baseline",
        "telecom.drift_compare_targets",
        "telecom.audit_report",
        "telecom.audit_export",
        "telecom.scorecard_target",
        "telecom.scorecard_cluster",
        "telecom.scorecard_environment",
        "telecom.scorecard_compare",
        "telecom.scorecard_trend",
        "telecom.scorecard_export",
        "telecom.scorecard_policy_inputs",
        "telecom.capture_incident_evidence",
        "telecom.generate_evidence_pack",
        "telecom.reconstruct_incident_timeline",
        "telecom.export_evidence_pack",
        "telecom.list_probes",
        "telecom.run_probe",
        "telecom.list_chaos_scenarios",
        "telecom.run_chaos_scenario",
        "telecom.list_self_healing_policies",
        "telecom.evaluate_self_healing",
        "telecom.run_self_healing_policy",
        "telecom.release_gate_decision",
        "telecom.release_promotion_decision",
        "telecom.release_gate_history",
        "telecom.assert_state",
        "telecom.run_registration_probe",
        "telecom.run_trunk_probe",
        "telecom.verify_cleanup",
        "asterisk.health",
        "asterisk.pjsip_show_endpoint",
        "asterisk.pjsip_show_endpoints",
        "asterisk.pjsip_show_contacts",
        "asterisk.core_show_channel",
        "asterisk.version",
        "asterisk.modules",
        "asterisk.logs",
        "asterisk.cli",
        "asterisk.originate_probe",
        "freeswitch.health",
        "freeswitch.sofia_status",
        "freeswitch.channel_details",
        "freeswitch.version",
        "freeswitch.modules",
        "freeswitch.logs",
        "freeswitch.api",
        "freeswitch.originate_probe",
    }
    assert required.issubset(server.app.tools.keys())
    assert "contract://inbound-call/v0.1" in server.app.resources
    assert "investigate-target-health" in server.app.prompts


def test_wrapped_tool_calls_core_server(monkeypatch) -> None:
    from telecom_mcp.mcp_server import server as server_mod

    monkeypatch.setattr(server_mod, "_import_mcp_server_class", lambda: _DummyMcp)
    server = TelecomMcpSdkServer(targets_file="/tmp/does-not-exist-targets.yaml")

    calls: list[tuple[str, dict[str, Any]]] = []

    def _fake_execute(*, tool_name: str, args: dict[str, Any], correlation_id=None):
        calls.append((tool_name, args))
        return {
            "ok": True,
            "timestamp": "2026-03-06T00:00:00Z",
            "target": {"type": "telecom", "id": "pbx-1"},
            "duration_ms": 1,
            "correlation_id": "c-test",
            "data": {"echo": args},
            "error": None,
        }

    monkeypatch.setattr(server.core_server, "execute_tool", _fake_execute)

    result = server.app.tools["telecom.summary"]("pbx-1")
    assert calls == [("telecom.summary", {"pbx_id": "pbx-1"})]
    assert result["ok"] is True
    assert result["data"]["echo"]["pbx_id"] == "pbx-1"


def test_healthcheck_reports_missing_targets_warning(monkeypatch) -> None:
    from telecom_mcp.mcp_server import server as server_mod

    monkeypatch.setattr(server_mod, "_import_mcp_server_class", lambda: _DummyMcp)
    monkeypatch.setattr(server_mod, "_resolve_targets_file", lambda _path: None)
    server = TelecomMcpSdkServer(targets_file="/tmp/does-not-exist-targets.yaml")

    health = server.app.tools["telecom.healthcheck"]()
    assert health["ok"] is True
    assert health["target"] == {"type": "telecom", "id": "server"}
    assert health["data"]["targets_count"] == 0
    assert health["data"]["effective_targets_file"] is None
    assert "runtime_build" in health["data"]
    assert isinstance(health["data"]["runtime_build"]["tool_contract_fingerprint"], str)
    assert health["data"]["fixture_mode_semantics"]["core_tools_use_live_connectors"] is True
    assert health["data"]["preflight"]["targets"] == []
    assert any(
        w.get("code") == "TARGETS_FILE_NOT_FOUND"
        for w in health["data"]["startup_warnings"]
    )


def test_healthcheck_runtime_build_info_supports_tool_manager_only_app(monkeypatch) -> None:
    from telecom_mcp.mcp_server import server as server_mod

    monkeypatch.setattr(
        server_mod, "_import_mcp_server_class", lambda: _DummyMcpWithToolManager
    )
    server = TelecomMcpSdkServer(targets_file="/tmp/does-not-exist-targets.yaml")

    health = server.app._tool_manager._tools["telecom.healthcheck"].fn()
    runtime_build = health["data"]["runtime_build"]
    assert runtime_build["tool_count"] >= 1
    assert isinstance(runtime_build["tool_contract_fingerprint"], str)


def test_wrappers_normalize_optional_object_and_limit_args(monkeypatch) -> None:
    from telecom_mcp.mcp_server import server as server_mod

    monkeypatch.setattr(server_mod, "_import_mcp_server_class", lambda: _DummyMcp)
    server = TelecomMcpSdkServer(targets_file="/tmp/does-not-exist-targets.yaml")

    calls: list[tuple[str, dict[str, Any]]] = []

    def _fake_execute(*, tool_name: str, args: dict[str, Any], correlation_id=None):
        calls.append((tool_name, args))
        return {
            "ok": False,
            "timestamp": "2026-03-06T00:00:00Z",
            "target": {"type": "telecom", "id": "pbx-1"},
            "duration_ms": 1,
            "correlation_id": "c-test",
            "data": {},
            "error": {"code": "VALIDATION_ERROR", "message": "bad args", "details": {}},
        }

    monkeypatch.setattr(server.core_server, "execute_tool", _fake_execute)

    _ = server.app.tools["asterisk.pjsip_show_endpoints"](
        "pbx-1", '{"starts_with":"10"}', "50"
    )
    _ = server.app.tools["asterisk.bridges"]("pbx-1", "30")
    _ = server.app.tools["freeswitch.channels"]("pbx-1", "60")
    _ = server.app.tools["freeswitch.calls"]("pbx-1", "70")
    _ = server.app.tools["freeswitch.registrations"]("pbx-1", None, "80")
    _ = server.app.tools["telecom.capture_snapshot"](
        "pbx-1", "endpoints,calls", "max_items=75"
    )
    _ = server.app.tools["telecom.endpoints"]("pbx-1", '{"starts_with":"10"}', "25")
    _ = server.app.tools["telecom.logs"]("pbx-1", "error", "15", "warning")
    _ = server.app.tools["asterisk.pjsip_show_contacts"](
        "pbx-1", '{"contains":"100"}', "40"
    )
    _ = server.app.tools["asterisk.logs"]("pbx-1", "chan_sip", "11", "notice")
    _ = server.app.tools["freeswitch.logs"]("pbx-1", "sofia", "12", "error")
    _ = server.app.tools["telecom.diff_snapshots"](
        '{"snapshot_id":"a"}',
        '{"snapshot_id":"b"}',
    )
    _ = server.app.tools["telecom.compare_targets"]("pbx-1", "fs-1")
    _ = server.app.tools["telecom.run_smoke_test"]("pbx-1")
    _ = server.app.tools["telecom.run_playbook"](
        "sip_registration_triage", "pbx-1", "1001"
    )
    _ = server.app.tools["telecom.run_smoke_suite"](
        "baseline_read_only_smoke", "pbx-1", '{"window":"5m"}'
    )
    _ = server.app.tools["telecom.baseline_create"]("pbx-1", "base-1")
    _ = server.app.tools["telecom.baseline_show"]("base-1")
    _ = server.app.tools["telecom.audit_target"]("pbx-1", "base-1")
    _ = server.app.tools["telecom.drift_target_vs_baseline"]("pbx-1", "base-1")
    _ = server.app.tools["telecom.drift_compare_targets"]("pbx-1", "fs-1")
    _ = server.app.tools["telecom.audit_report"]("pbx-1", "base-1")
    _ = server.app.tools["telecom.audit_export"]("pbx-1", "markdown", "base-1")
    _ = server.app.tools["telecom.scorecard_target"]("pbx-1")
    _ = server.app.tools["telecom.scorecard_cluster"]("cluster-a", "pbx-1,fs-1")
    _ = server.app.tools["telecom.scorecard_environment"]("prod", "pbx-1,fs-1")
    _ = server.app.tools["telecom.scorecard_compare"]("pbx-1", "fs-1")
    _ = server.app.tools["telecom.scorecard_trend"]("pbx", "pbx-1", "30d")
    _ = server.app.tools["telecom.scorecard_export"]("pbx", "pbx-1", "markdown", "pbx-1,fs-1")
    _ = server.app.tools["telecom.capture_incident_evidence"]("pbx-1")
    _ = server.app.tools["telecom.generate_evidence_pack"]("pbx-1", "trunk_outage", "inc-1")
    _ = server.app.tools["telecom.reconstruct_incident_timeline"]("pack-inc-1")
    _ = server.app.tools["telecom.export_evidence_pack"]("pack-inc-1", "markdown")
    _ = server.app.tools["telecom.list_probes"]()
    _ = server.app.tools["telecom.run_probe"]("registration_visibility_probe", "pbx-1", '{"endpoint":"1001"}')
    _ = server.app.tools["telecom.list_chaos_scenarios"]()
    _ = server.app.tools["telecom.run_chaos_scenario"]("sip_registration_loss", "pbx-1", '{"mode":"fixture"}')
    _ = server.app.tools["telecom.list_self_healing_policies"]()
    _ = server.app.tools["telecom.evaluate_self_healing"]("pbx-1", '{"change_context":"post-deploy"}')
    _ = server.app.tools["telecom.run_self_healing_policy"]("observability_refresh_retry", "pbx-1", '{"reason":"refresh"}')
    _ = server.app.tools["telecom.assert_state"]("pbx-1", "target_type", '{"value":"asterisk"}')
    _ = server.app.tools["telecom.run_registration_probe"](
        "pbx-1", "1001", "registration probe", "CHG-9001", "22"
    )
    _ = server.app.tools["telecom.run_trunk_probe"](
        "pbx-1", "18005550199", "trunk probe", "CHG-9002", "23"
    )
    _ = server.app.tools["telecom.verify_cleanup"]("pbx-1")
    _ = server.app.tools["asterisk.core_show_channel"]("pbx-1", "PJSIP/1001-00000001")
    _ = server.app.tools["asterisk.modules"]("pbx-1")
    _ = server.app.tools["asterisk.cli"]("pbx-1", "core show version")
    _ = server.app.tools["asterisk.originate_probe"](
        "pbx-1", "1001", "asterisk probe", "CHG-9003", "24"
    )
    _ = server.app.tools["freeswitch.channel_details"]("pbx-1", "uuid-1")
    _ = server.app.tools["freeswitch.modules"]("pbx-1")
    _ = server.app.tools["freeswitch.api"]("pbx-1", "status")
    _ = server.app.tools["freeswitch.originate_probe"](
        "pbx-1", "1002", "freeswitch probe", "CHG-9004", "25"
    )
    _ = server.app.tools["telecom.scorecard_policy_inputs"]("pbx", None, "pbx-1")
    _ = server.app.tools["telecom.release_gate_decision"](
        "pbx-1",
        '{"high_risk_change":true}',
        '{"score":81,"confidence":"high","freshness":"fresh","recommended_escalations":[],"policy_handoff":{"stop_conditions":[]}}',
        '{"smoke_status":"passed","post_change_status":"passed","cleanup_ok":true,"conflicting_evidence":false}',
    )
    _ = server.app.tools["telecom.release_promotion_decision"](
        "staging",
        "pbx-1,fs-1",
        '{"high_risk_change":false}',
    )
    _ = server.app.tools["telecom.release_gate_history"]("pbx", "pbx-1", "15")

    assert calls[0] == (
        "asterisk.pjsip_show_endpoints",
        {"pbx_id": "pbx-1", "limit": 50, "filter": {"starts_with": "10"}},
    )
    assert calls[1] == (
        "asterisk.bridges",
        {"pbx_id": "pbx-1", "limit": 30},
    )
    assert calls[2] == (
        "freeswitch.channels",
        {"pbx_id": "pbx-1", "limit": 60},
    )
    assert calls[3] == (
        "freeswitch.calls",
        {"pbx_id": "pbx-1", "limit": 70},
    )
    assert calls[4] == (
        "freeswitch.registrations",
        {"pbx_id": "pbx-1", "limit": 80},
    )
    assert calls[5] == (
        "telecom.capture_snapshot",
        {
            "pbx_id": "pbx-1",
            "include": {"endpoints": True, "calls": True},
            "limits": {"max_items": 75},
        },
    )
    assert calls[6] == (
        "telecom.endpoints",
        {"pbx_id": "pbx-1", "limit": 25, "filter": {"starts_with": "10"}},
    )
    assert calls[7] == (
        "telecom.logs",
        {"pbx_id": "pbx-1", "tail": 15, "grep": "error", "level": "warning"},
    )
    assert calls[8] == (
        "asterisk.pjsip_show_contacts",
        {"pbx_id": "pbx-1", "limit": 40, "filter": {"contains": "100"}},
    )
    assert calls[9] == (
        "asterisk.logs",
        {"pbx_id": "pbx-1", "tail": 11, "grep": "chan_sip", "level": "notice"},
    )
    assert calls[10] == (
        "freeswitch.logs",
        {"pbx_id": "pbx-1", "tail": 12, "grep": "sofia", "level": "error"},
    )
    assert calls[11] == (
        "telecom.diff_snapshots",
        {"snapshot_a": {"snapshot_id": "a"}, "snapshot_b": {"snapshot_id": "b"}},
    )
    assert calls[12] == (
        "telecom.compare_targets",
        {"pbx_a": "pbx-1", "pbx_b": "fs-1"},
    )
    assert calls[13] == (
        "telecom.run_smoke_test",
        {"pbx_id": "pbx-1"},
    )
    assert calls[14] == (
        "telecom.run_playbook",
        {"name": "sip_registration_triage", "pbx_id": "pbx-1", "endpoint": "1001"},
    )
    assert calls[15] == (
        "telecom.run_smoke_suite",
        {"name": "baseline_read_only_smoke", "pbx_id": "pbx-1", "params": {"window": "5m"}},
    )
    assert calls[16] == (
        "telecom.baseline_create",
        {"pbx_id": "pbx-1", "baseline_id": "base-1"},
    )
    assert calls[17] == (
        "telecom.baseline_show",
        {"baseline_id": "base-1"},
    )
    assert calls[18] == (
        "telecom.audit_target",
        {"pbx_id": "pbx-1", "baseline_id": "base-1"},
    )
    assert calls[19] == (
        "telecom.drift_target_vs_baseline",
        {"pbx_id": "pbx-1", "baseline_id": "base-1"},
    )
    assert calls[20] == (
        "telecom.drift_compare_targets",
        {"pbx_a": "pbx-1", "pbx_b": "fs-1"},
    )
    assert calls[21] == (
        "telecom.audit_report",
        {"pbx_id": "pbx-1", "baseline_id": "base-1"},
    )
    assert calls[22] == (
        "telecom.audit_export",
        {"pbx_id": "pbx-1", "format": "markdown", "baseline_id": "base-1"},
    )
    assert calls[23] == (
        "telecom.scorecard_target",
        {"pbx_id": "pbx-1"},
    )
    assert calls[24] == (
        "telecom.scorecard_cluster",
        {"cluster_id": "cluster-a", "pbx_ids": ["pbx-1", "fs-1"]},
    )
    assert calls[25] == (
        "telecom.scorecard_environment",
        {"environment_id": "prod", "pbx_ids": ["pbx-1", "fs-1"]},
    )
    assert calls[26] == (
        "telecom.scorecard_compare",
        {"entity_type": "pbx", "entity_a": "pbx-1", "entity_b": "fs-1"},
    )
    assert calls[27] == (
        "telecom.scorecard_trend",
        {"entity_type": "pbx", "entity_id": "pbx-1", "window": "30d"},
    )
    assert calls[28] == (
        "telecom.scorecard_export",
        {
            "entity_type": "pbx",
            "entity_id": "pbx-1",
            "format": "markdown",
            "pbx_ids": ["pbx-1", "fs-1"],
        },
    )
    assert calls[29] == (
        "telecom.capture_incident_evidence",
        {"pbx_id": "pbx-1"},
    )
    assert calls[30] == (
        "telecom.generate_evidence_pack",
        {"pbx_id": "pbx-1", "incident_type": "trunk_outage", "incident_id": "inc-1"},
    )
    assert calls[31] == (
        "telecom.reconstruct_incident_timeline",
        {"pack_id": "pack-inc-1"},
    )
    assert calls[32] == (
        "telecom.export_evidence_pack",
        {"pack_id": "pack-inc-1", "format": "markdown"},
    )
    assert calls[33] == (
        "telecom.list_probes",
        {},
    )
    assert calls[34] == (
        "telecom.run_probe",
        {"name": "registration_visibility_probe", "pbx_id": "pbx-1", "params": {"endpoint": "1001"}},
    )
    assert calls[35] == (
        "telecom.list_chaos_scenarios",
        {},
    )
    assert calls[36] == (
        "telecom.run_chaos_scenario",
        {"name": "sip_registration_loss", "pbx_id": "pbx-1", "params": {"mode": "fixture"}},
    )
    assert calls[37] == (
        "telecom.list_self_healing_policies",
        {},
    )
    assert calls[38] == (
        "telecom.evaluate_self_healing",
        {"pbx_id": "pbx-1", "context": {"change_context": "post-deploy"}},
    )
    assert calls[39] == (
        "telecom.run_self_healing_policy",
        {"name": "observability_refresh_retry", "pbx_id": "pbx-1", "params": {"reason": "refresh"}},
    )
    assert calls[40] == (
        "telecom.assert_state",
        {"pbx_id": "pbx-1", "assertion": "target_type", "params": {"value": "asterisk"}},
    )
    assert calls[41] == (
        "telecom.run_registration_probe",
        {
            "pbx_id": "pbx-1",
            "destination": "1001",
            "timeout_s": 22,
            "reason": "registration probe",
            "change_ticket": "CHG-9001",
        },
    )
    assert calls[42] == (
        "telecom.run_trunk_probe",
        {
            "pbx_id": "pbx-1",
            "destination": "18005550199",
            "timeout_s": 23,
            "reason": "trunk probe",
            "change_ticket": "CHG-9002",
        },
    )
    assert calls[43] == (
        "telecom.verify_cleanup",
        {"pbx_id": "pbx-1"},
    )
    assert calls[44] == (
        "asterisk.core_show_channel",
        {"pbx_id": "pbx-1", "channel_id": "PJSIP/1001-00000001"},
    )
    assert calls[45] == (
        "asterisk.modules",
        {"pbx_id": "pbx-1"},
    )
    assert calls[46] == (
        "asterisk.cli",
        {"pbx_id": "pbx-1", "command": "core show version"},
    )
    assert calls[47] == (
        "asterisk.originate_probe",
        {
            "pbx_id": "pbx-1",
            "destination": "1001",
            "timeout_s": 24,
            "reason": "asterisk probe",
            "change_ticket": "CHG-9003",
        },
    )
    assert calls[48] == (
        "freeswitch.channel_details",
        {"pbx_id": "pbx-1", "uuid": "uuid-1"},
    )
    assert calls[49] == (
        "freeswitch.modules",
        {"pbx_id": "pbx-1"},
    )
    assert calls[50] == (
        "freeswitch.api",
        {"pbx_id": "pbx-1", "command": "status"},
    )
    assert calls[51] == (
        "freeswitch.originate_probe",
        {
            "pbx_id": "pbx-1",
            "destination": "1002",
            "timeout_s": 25,
            "reason": "freeswitch probe",
            "change_ticket": "CHG-9004",
        },
    )
    assert calls[52] == (
        "telecom.scorecard_policy_inputs",
        {"entity_type": "pbx", "pbx_id": "pbx-1"},
    )
    assert calls[53] == (
        "telecom.release_gate_decision",
        {
            "pbx_id": "pbx-1",
            "context": {"high_risk_change": True},
            "policy_input": {
                "score": 81,
                "confidence": "high",
                "freshness": "fresh",
                "recommended_escalations": [],
                "policy_handoff": {"stop_conditions": []},
            },
            "validation": {
                "smoke_status": "passed",
                "post_change_status": "passed",
                "cleanup_ok": True,
                "conflicting_evidence": False,
            },
        },
    )
    assert calls[54] == (
        "telecom.release_promotion_decision",
        {
            "environment_id": "staging",
            "pbx_ids": ["pbx-1", "fs-1"],
            "context": {"high_risk_change": False},
        },
    )
    assert calls[55] == (
        "telecom.release_gate_history",
        {"entity_type": "pbx", "entity_id": "pbx-1", "limit": 15},
    )


def test_contract_resource_returns_json(monkeypatch) -> None:
    from telecom_mcp.mcp_server import server as server_mod

    monkeypatch.setattr(server_mod, "_import_mcp_server_class", lambda: _DummyMcp)
    server = TelecomMcpSdkServer(targets_file="/tmp/does-not-exist-targets.yaml")

    payload = server.app.resources["contract://inbound-call/v0.1"]()
    parsed = json.loads(payload)
    assert parsed["version"] == "v0.1"


def test_write_wrappers_require_intent_metadata(monkeypatch) -> None:
    from telecom_mcp.mcp_server import server as server_mod

    monkeypatch.setattr(server_mod, "_import_mcp_server_class", lambda: _DummyMcp)
    server = TelecomMcpSdkServer(targets_file="/tmp/does-not-exist-targets.yaml")

    sig = inspect.signature(server.app.tools["asterisk.reload_pjsip"])
    assert sig.parameters["reason"].default is inspect._empty
    assert sig.parameters["change_ticket"].default is inspect._empty


def test_healthcheck_surfaces_policy_and_platform_coverage_warning(monkeypatch, tmp_path) -> None:
    from telecom_mcp.mcp_server import server as server_mod

    monkeypatch.setattr(server_mod, "_import_mcp_server_class", lambda: _DummyMcp)
    targets_file = tmp_path / "targets.yaml"
    targets_file.write_text(
        """
targets:
  - id: pbx-1
    type: asterisk
    host: 10.0.0.10
    ami:
      host: 10.0.0.10
      port: 5038
      username_env: AST_AMI_USER_PBX1
      password_env: AST_AMI_PASS_PBX1
    ari:
      url: http://10.0.0.10:8088
      username_env: AST_ARI_USER_PBX1
      password_env: AST_ARI_PASS_PBX1
      app: telecom_mcp
""",
        encoding="utf-8",
    )
    server = TelecomMcpSdkServer(
        targets_file=str(targets_file),
        write_allowlist=["asterisk.reload_pjsip"],
        cooldown_seconds=11,
        max_calls_per_window=12,
        rate_limit_window_seconds=13.0,
        tool_timeout_seconds=14.0,
    )

    health = server.app.tools["telecom.healthcheck"]()
    assert health["data"]["runtime_build"]["tool_count"] >= 1
    assert health["data"]["policy"] == {
        "write_allowlist": ["asterisk.reload_pjsip"],
        "cooldown_seconds": 11,
        "max_calls_per_window": 12,
        "rate_limit_window_seconds": 13.0,
        "tool_timeout_seconds": 14.0,
        "write_mode_active": False,
        "writes_effectively_disabled": True,
        "require_explicit_targets_file": False,
        "require_confirm_token": False,
        "runtime_flag_require_confirm_token": False,
        "fail_on_degraded_default": False,
    }
    warning_codes = {w["code"] for w in health["data"]["startup_warnings"]}
    assert "TARGET_PLATFORM_COVERAGE_GAP" in warning_codes
    assert "AMI_PJSIP_PERMISSIONS_UNVERIFIED" in warning_codes
    assert "TARGETS_FILE_NON_CANONICAL" in warning_codes
    assert health["data"]["preflight"]["platform_coverage"]["missing"] == ["freeswitch"]
    assert health["data"]["preflight"]["targets"][0]["pbx_id"] == "pbx-1"
    assert health["data"]["live_connector_mode_effective"] is True


def test_mcp_cli_exposes_policy_tuning_flags() -> None:
    parser = build_arg_parser()
    args = parser.parse_args(
        [
            "--cooldown-seconds",
            "9",
            "--max-calls-per-window",
            "99",
            "--rate-limit-window-seconds",
            "2.5",
            "--tool-timeout-seconds",
            "3.5",
        ]
    )
    assert args.cooldown_seconds == 9
    assert args.max_calls_per_window == 99
    assert args.rate_limit_window_seconds == 2.5
    assert args.tool_timeout_seconds == 3.5
    assert args.strict_startup is False


def test_wrapper_signatures_use_typed_filter_include_limit(monkeypatch) -> None:
    from telecom_mcp.mcp_server import server as server_mod

    monkeypatch.setattr(server_mod, "_import_mcp_server_class", lambda: _DummyMcp)
    server = TelecomMcpSdkServer(targets_file="/tmp/does-not-exist-targets.yaml")

    capture_sig = inspect.signature(server.app.tools["telecom.capture_snapshot"])
    endpoints_sig = inspect.signature(server.app.tools["asterisk.pjsip_show_endpoints"])
    channels_sig = inspect.signature(server.app.tools["asterisk.active_channels"])
    endpoint_hints = get_type_hints(server.app.tools["asterisk.pjsip_show_endpoints"])
    channel_hints = get_type_hints(server.app.tools["asterisk.active_channels"])

    assert capture_sig.parameters["include"].annotation != Any
    assert capture_sig.parameters["limits"].annotation != Any
    assert endpoints_sig.parameters["filter"].annotation != Any
    assert endpoint_hints["limit"] != Any
    assert channels_sig.parameters["filter"].annotation != Any
    assert channel_hints["limit"] != Any


def test_strict_startup_blocks_on_hygiene_warnings(monkeypatch) -> None:
    from telecom_mcp.mcp_server import server as server_mod

    monkeypatch.setattr(server_mod, "_import_mcp_server_class", lambda: _DummyMcp)

    def _inject_duplicate_warning(self):
        self.startup_warnings.append(
            {"code": "TARGETS_FILE_DUPLICATE", "message": "duplicate", "details": {}}
        )

    monkeypatch.setattr(
        server_mod.TelecomMcpSdkServer,
        "_append_targets_file_hygiene_warnings",
        _inject_duplicate_warning,
    )

    with pytest.raises(ToolError) as exc:
        server_mod.TelecomMcpSdkServer(
            targets_file="/tmp/does-not-exist-targets.yaml",
            strict_startup=True,
        )
    assert exc.value.code == VALIDATION_ERROR
