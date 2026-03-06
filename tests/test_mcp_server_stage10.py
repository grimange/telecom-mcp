from __future__ import annotations

import json
from typing import Any, Callable

from telecom_mcp.mcp_server.runtime import load_runtime_flags
from telecom_mcp.mcp_server.server import TelecomMcpSdkServer


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
    assert any(
        w.get("code") == "TARGETS_FILE_NOT_FOUND"
        for w in health["data"]["startup_warnings"]
    )


def test_wrappers_preserve_raw_optional_object_args(monkeypatch) -> None:
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

    _ = server.app.tools["asterisk.pjsip_show_endpoints"]("pbx-1", "bad-filter", "bad-limit")
    _ = server.app.tools["telecom.capture_snapshot"]("pbx-1", "bad-include", "bad-limits")

    assert calls[0] == (
        "asterisk.pjsip_show_endpoints",
        {"pbx_id": "pbx-1", "limit": "bad-limit", "filter": "bad-filter"},
    )
    assert calls[1] == (
        "telecom.capture_snapshot",
        {"pbx_id": "pbx-1", "include": "bad-include", "limits": "bad-limits"},
    )


def test_contract_resource_returns_json(monkeypatch) -> None:
    from telecom_mcp.mcp_server import server as server_mod

    monkeypatch.setattr(server_mod, "_import_mcp_server_class", lambda: _DummyMcp)
    server = TelecomMcpSdkServer(targets_file="/tmp/does-not-exist-targets.yaml")

    payload = server.app.resources["contract://inbound-call/v0.1"]()
    parsed = json.loads(payload)
    assert parsed["version"] == "v0.1"
