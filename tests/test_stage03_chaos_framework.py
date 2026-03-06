from __future__ import annotations

from types import SimpleNamespace

import pytest

from telecom_mcp.errors import ToolError, VALIDATION_ERROR
from telecom_mcp.tools import telecom


class _Ctx:
    def __init__(self, *, mode: str = "inspect", tags: list[str] | None = None) -> None:
        self.mode = SimpleNamespace(value=mode)
        self._target = SimpleNamespace(id="pbx-1", type="asterisk", tags=tags or [])
        self.settings = SimpleNamespace(get_target=lambda _pbx_id: self._target)

    def call_tool_internal(self, tool_name: str, args: dict[str, object]):
        if tool_name == "telecom.run_smoke_suite":
            return {"ok": True, "data": {"suite": args.get("name"), "status": "passed", "counts": {"passed": 3, "warning": 0, "failed": 0}}}
        if tool_name == "telecom.capture_snapshot":
            return {"ok": True, "data": {"snapshot_id": "snap-1", "summary": {"pbx_id": "pbx-1"}}}
        if tool_name == "telecom.run_playbook":
            return {"ok": True, "data": {"playbook": args.get("name"), "status": "warning", "bucket": "suspected"}}
        if tool_name == "telecom.audit_target":
            return {"ok": True, "data": {"score": 72, "status": "degraded"}}
        if tool_name == "telecom.verify_cleanup":
            return {"ok": True, "data": {"clean": True}}
        raise AssertionError(f"unexpected tool call: {tool_name}")


def test_list_chaos_scenarios_exposes_catalog() -> None:
    _target, data = telecom.list_chaos_scenarios(_Ctx(), {})
    names = {item["name"] for item in data["scenarios"]}
    assert "sip_registration_loss" in names
    assert "drift_injection_fixture" in names


def test_fixture_chaos_scenario_runs_in_inspect() -> None:
    _target, data = telecom.run_chaos_scenario(
        _Ctx(mode="inspect"),
        {"name": "sip_registration_loss", "pbx_id": "pbx-1", "params": {"mode": "fixture"}},
    )
    assert data["scenario"] == "sip_registration_loss"
    assert data["status"] in {"passed", "warning"}


def test_lab_chaos_blocked_without_enable_flag() -> None:
    _target, data = telecom.run_chaos_scenario(
        _Ctx(mode="execute_safe", tags=["lab"]),
        {"name": "trunk_gateway_outage", "pbx_id": "pbx-1", "params": {"mode": "lab"}},
    )
    assert data["status"] == "failed"
    assert any("TELECOM_MCP_ENABLE_CHAOS" in reason for reason in data["gating_failures"])


def test_lab_chaos_runs_when_enabled(monkeypatch) -> None:
    monkeypatch.setenv("TELECOM_MCP_ENABLE_CHAOS", "1")
    _target, data = telecom.run_chaos_scenario(
        _Ctx(mode="execute_safe", tags=["lab"]),
        {"name": "trunk_gateway_outage", "pbx_id": "pbx-1", "params": {"mode": "lab"}},
    )
    assert data["scenario"] == "trunk_gateway_outage"
    assert data["status"] in {"passed", "warning"}


def test_chaos_invalid_scenario_rejected() -> None:
    with pytest.raises(ToolError) as exc:
        telecom.run_chaos_scenario(_Ctx(), {"name": "does_not_exist", "pbx_id": "pbx-1"})
    assert exc.value.code == VALIDATION_ERROR
