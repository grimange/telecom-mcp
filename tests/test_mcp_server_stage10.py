from __future__ import annotations

import inspect
import json
from typing import Any, Callable

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


def test_runtime_flag_defaults(monkeypatch) -> None:
    monkeypatch.delenv("TELECOM_MCP_FIXTURES", raising=False)
    monkeypatch.delenv("TELECOM_MCP_ENABLE_REAL_PBX", raising=False)
    monkeypatch.delenv("TELECOM_MCP_TRANSPORT", raising=False)

    flags = load_runtime_flags()
    assert flags.fixtures is True
    assert flags.real_pbx is False
    assert flags.transport == "stdio"


def test_mcp_catalog_registers_v1_telecom_tools(monkeypatch) -> None:
    from telecom_mcp.mcp_server import server as server_mod

    monkeypatch.setattr(server_mod, "_import_mcp_server_class", lambda: _DummyMcp)
    server = TelecomMcpSdkServer(targets_file="/tmp/does-not-exist-targets.yaml")

    required = {
        "telecom.healthcheck",
        "telecom.list_targets",
        "telecom.summary",
        "telecom.capture_snapshot",
        "asterisk.health",
        "asterisk.pjsip_show_endpoint",
        "asterisk.pjsip_show_endpoints",
        "freeswitch.health",
        "freeswitch.sofia_status",
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
    assert any(
        w.get("code") == "TARGETS_FILE_NOT_FOUND"
        for w in health["data"]["startup_warnings"]
    )


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
        "pbx-1", '{"calls":false}', '{"max_items":75}'
    )

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
        {"pbx_id": "pbx-1", "include": {"calls": False}, "limits": {"max_items": 75}},
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
    assert health["data"]["policy"] == {
        "write_allowlist": ["asterisk.reload_pjsip"],
        "cooldown_seconds": 11,
        "max_calls_per_window": 12,
        "rate_limit_window_seconds": 13.0,
        "tool_timeout_seconds": 14.0,
    }
    warning_codes = {w["code"] for w in health["data"]["startup_warnings"]}
    assert "TARGET_PLATFORM_COVERAGE_GAP" in warning_codes
    assert "AMI_PJSIP_PERMISSIONS_UNVERIFIED" in warning_codes


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
