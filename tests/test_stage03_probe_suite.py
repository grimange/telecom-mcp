from __future__ import annotations

from types import SimpleNamespace

import pytest

from telecom_mcp.tools import telecom


class _Ctx:
    def __init__(
        self,
        *,
        mode: str = "inspect",
        environment: str = "lab",
        safety_tier: str = "lab_safe",
        allow_active_validation: bool = True,
    ) -> None:
        self.mode = SimpleNamespace(value=mode)
        self._target = SimpleNamespace(
            id="pbx-1",
            type="asterisk",
            environment=environment,
            safety_tier=safety_tier,
            allow_active_validation=allow_active_validation,
        )
        self.settings = SimpleNamespace(get_target=lambda _pbx_id: self._target)

    def call_tool_internal(self, tool_name: str, args: dict[str, object]):
        if tool_name == "telecom.run_smoke_suite":
            return {"ok": True, "data": {"suite": args.get("name"), "status": "passed", "counts": {"passed": 3, "warning": 0, "failed": 0}}}
        if tool_name == "telecom.capture_snapshot":
            return {"ok": True, "data": {"snapshot_id": "snap-1", "summary": {"pbx_id": "pbx-1"}}}
        if tool_name == "telecom.endpoints":
            return {"ok": True, "data": {"items": [{"id": "1001", "status": "Reachable"}]}}
        if tool_name == "telecom.registrations":
            return {"ok": True, "data": {"items": [{"endpoint": "1001"}]}}
        if tool_name == "asterisk.health":
            return {"ok": True, "data": {"ok": True}}
        if tool_name == "telecom.summary":
            return {"ok": True, "data": {"channels_active": 1}}
        if tool_name == "telecom.channels":
            return {"ok": True, "data": {"items": [{"channel_id": "PJSIP/1001-1"}]}}
        if tool_name == "telecom.logs":
            return {"ok": True, "data": {"items": [{"message": "probe line"}]}}
        if tool_name == "telecom.verify_cleanup":
            return {"ok": True, "data": {"clean": True}}
        if tool_name == "telecom.audit_target":
            return {"ok": True, "data": {"score": 80, "status": "acceptable"}}
        if tool_name == "telecom.run_registration_probe":
            return {"ok": True, "data": {"probe_id": "probe-1", "initiated": True}}
        if tool_name == "telecom.run_trunk_probe":
            return {"ok": True, "data": {"probe_id": "probe-2", "initiated": True}}
        if tool_name == "asterisk.bridges":
            return {"ok": True, "data": {"items": [{"bridge_id": "b-1"}]}}
        if tool_name == "telecom.run_playbook":
            return {"ok": True, "data": {"playbook": args.get("name"), "status": "warning"}}
        raise AssertionError(f"unexpected tool call: {tool_name}")


def test_list_probes_contains_catalog() -> None:
    _target, data = telecom.list_probes(_Ctx(), {})
    names = {item["name"] for item in data["probes"]}
    assert "registration_visibility_probe" in names
    assert "post_change_validation_probe_suite" in names


def test_passive_probe_runs_in_inspect() -> None:
    _target, data = telecom.run_probe(
        _Ctx(mode="inspect"),
        {"name": "registration_visibility_probe", "pbx_id": "pbx-1", "params": {"endpoint": "1001"}},
    )
    assert data["probe"] == "registration_visibility_probe"
    assert data["status"] in {"passed", "warning"}
    assert data["gating_failures"] == []


def test_active_probe_blocked_without_validation_mode(monkeypatch) -> None:
    monkeypatch.setenv("TELECOM_MCP_ENABLE_ACTIVE_PROBES", "1")
    _target, data = telecom.run_probe(
        _Ctx(mode="inspect"),
        {"name": "controlled_originate_probe", "pbx_id": "pbx-1", "params": {"destination": "1001"}},
    )
    assert data["status"] == "failed"
    assert any("execute_safe" in reason for reason in data["gating_failures"])


def test_active_probe_runs_when_gated_conditions_met(monkeypatch) -> None:
    monkeypatch.setenv("TELECOM_MCP_ENABLE_ACTIVE_PROBES", "1")
    _target, data = telecom.run_probe(
        _Ctx(mode="execute_safe"),
        {"name": "controlled_originate_probe", "pbx_id": "pbx-1", "params": {"destination": "1001", "timeout_s": 10}},
    )
    assert data["probe"] == "controlled_originate_probe"
    assert data["status"] in {"passed", "warning"}


def test_active_probe_blocked_when_target_not_explicitly_lab_safe(monkeypatch) -> None:
    monkeypatch.setenv("TELECOM_MCP_ENABLE_ACTIVE_PROBES", "1")
    _target, data = telecom.run_probe(
        _Ctx(
            mode="execute_safe",
            environment="lab",
            safety_tier="standard",
            allow_active_validation=False,
        ),
        {"name": "controlled_originate_probe", "pbx_id": "pbx-1", "params": {"destination": "1001"}},
    )
    assert data["status"] == "failed"
    assert any("allow_active_validation" in reason for reason in data["gating_failures"])


def test_post_change_probe_suite_runs() -> None:
    _target, data = telecom.run_probe(
        _Ctx(mode="inspect"),
        {"name": "post_change_validation_probe_suite", "pbx_id": "pbx-1", "params": {"include_active": False}},
    )
    assert data["probe"] == "post_change_validation_probe_suite"
    assert data["evidence"]["pre_smoke"] is True
