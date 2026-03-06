from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from telecom_mcp.tools import telecom


@pytest.fixture(autouse=True)
def _reset_self_heal_state(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TELECOM_MCP_STATE_DIR", str(tmp_path / "state"))
    telecom._SELF_HEAL_LAST_ACTION_TS.clear()
    telecom._SELF_HEAL_RETRY_COUNT.clear()


class _Ctx:
    def __init__(
        self,
        *,
        mode: str = "inspect",
        target_type: str = "asterisk",
        environment: str = "lab",
        safety_tier: str = "lab_safe",
        allow_active_validation: bool = True,
    ) -> None:
        self.mode = SimpleNamespace(value=mode)
        self._target = SimpleNamespace(
            id="pbx-1",
            type=target_type,
            environment=environment,
            safety_tier=safety_tier,
            allow_active_validation=allow_active_validation,
        )
        self.settings = SimpleNamespace(get_target=lambda _pbx_id: self._target)

    def call_tool_internal(self, tool_name: str, args: dict[str, object]):
        if tool_name == "telecom.run_smoke_suite":
            return {"ok": True, "data": {"suite": args.get("name"), "status": "passed", "counts": {"passed": 3, "warning": 0, "failed": 0}}}
        if tool_name == "telecom.run_playbook":
            return {"ok": True, "data": {"playbook": args.get("name"), "status": "warning", "bucket": "stale"}}
        if tool_name == "telecom.audit_target":
            return {"ok": True, "data": {"score": 78, "status": "acceptable"}}
        if tool_name == "telecom.capture_snapshot":
            return {"ok": True, "data": {"snapshot_id": "snap-1"}}
        if tool_name == "telecom.logs":
            return {"ok": True, "data": {"items": [{"message": "ok"}]}}
        if tool_name == "telecom.channels":
            return {"ok": True, "data": {"items": [{"channel_id": "C-1"}]}}
        if tool_name == "telecom.registrations":
            return {"ok": True, "data": {"items": [{"endpoint": "1001"}]}}
        if tool_name == "telecom.verify_cleanup":
            return {"ok": True, "data": {"clean": True}}
        if tool_name == "telecom.run_probe":
            return {"ok": True, "data": {"probe": args.get("name"), "status": "passed"}}
        if tool_name == "telecom.drift_compare_targets":
            return {"ok": True, "data": {"summary": "ok", "items": []}}
        if tool_name == "telecom.generate_evidence_pack":
            return {"ok": True, "data": {"pack_id": "pack-1"}}
        if tool_name == "telecom.scorecard_target":
            _target, data = telecom.scorecard_target(self, args)
            return {"ok": True, "data": data}
        if tool_name in {"asterisk.reload_pjsip", "freeswitch.reloadxml", "freeswitch.sofia_profile_rescan"}:
            return {"ok": True, "data": {"action": "ok"}}
        raise AssertionError(f"unexpected tool call: {tool_name}")


def test_list_self_healing_policies() -> None:
    _target, data = telecom.list_self_healing_policies(_Ctx(), {})
    names = {item["name"] for item in data["policies"]}
    assert "observability_refresh_retry" in names
    assert "escalate_only_high_risk" in names


def test_evaluate_self_healing_returns_eligibility() -> None:
    _target, data = telecom.evaluate_self_healing(
        _Ctx(mode="inspect"), {"pbx_id": "pbx-1", "context": {"change_context": "post-deploy"}}
    )
    assert data["tool"] == "telecom.evaluate_self_healing"
    assert isinstance(data["evaluations"], list)


def test_run_observability_refresh_policy_in_inspect() -> None:
    _target, data = telecom.run_self_healing_policy(
        _Ctx(mode="inspect"),
        {"name": "observability_refresh_retry", "pbx_id": "pbx-1", "params": {"reason": "refresh"}},
    )
    assert data["policy"] == "observability_refresh_retry"
    assert data["status"] in {"passed", "warning"}


def test_run_safe_reload_policy_blocked_without_enable() -> None:
    _target, data = telecom.run_self_healing_policy(
        _Ctx(mode="execute_safe"),
        {"name": "safe_sip_reload_refresh", "pbx_id": "pbx-1", "params": {"reason": "refresh", "change_ticket": "CHG-1"}},
    )
    assert data["status"] == "failed"
    assert any("TELECOM_MCP_ENABLE_SELF_HEALING" in reason for reason in data["gating_failures"])


def test_run_safe_reload_policy_when_enabled(monkeypatch) -> None:
    monkeypatch.setenv("TELECOM_MCP_ENABLE_SELF_HEALING", "1")
    _target, data = telecom.run_self_healing_policy(
        _Ctx(mode="execute_safe"),
        {"name": "safe_sip_reload_refresh", "pbx_id": "pbx-1", "params": {"reason": "refresh", "change_ticket": "CHG-1"}},
    )
    assert data["policy"] == "safe_sip_reload_refresh"
    assert data["status"] in {"passed", "warning"}


def test_run_safe_reload_policy_blocked_on_non_lab_safe_target(monkeypatch) -> None:
    monkeypatch.setenv("TELECOM_MCP_ENABLE_SELF_HEALING", "1")
    _target, data = telecom.run_self_healing_policy(
        _Ctx(
            mode="execute_safe",
            environment="production",
            safety_tier="restricted",
            allow_active_validation=False,
        ),
        {"name": "safe_sip_reload_refresh", "pbx_id": "pbx-1", "params": {"reason": "refresh", "change_ticket": "CHG-1"}},
    )
    assert data["status"] == "failed"
    assert any("allow_active_validation" in reason for reason in data["gating_failures"])


def test_self_heal_persists_coordination_state(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TELECOM_MCP_ENABLE_SELF_HEALING", "1")
    monkeypatch.setenv("TELECOM_MCP_STATE_DIR", str(tmp_path / "state"))
    _target, data = telecom.run_self_healing_policy(
        _Ctx(mode="execute_safe"),
        {
            "name": "safe_sip_reload_refresh",
            "pbx_id": "pbx-1",
            "params": {"reason": "refresh", "change_ticket": "CHG-1"},
        },
    )
    assert data["status"] in {"passed", "warning"}
    state_file = tmp_path / "state" / "self_heal_coordination.json"
    payload = json.loads(state_file.read_text(encoding="utf-8"))
    assert "last_action_ts" in payload
    assert "retry_count" in payload
