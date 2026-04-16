from __future__ import annotations

from types import SimpleNamespace

import pytest

from telecom_mcp.errors import NOT_ALLOWED, ToolError, VALIDATION_ERROR
from telecom_mcp.tools import telecom


class _Ctx:
    def __init__(self, *, target_type: str = "asterisk", mode: str = "inspect") -> None:
        self.mode = SimpleNamespace(value=mode)
        self._target = SimpleNamespace(
            id="pbx-1" if target_type == "asterisk" else "fs-1",
            type=target_type,
            host="127.0.0.1",
        )
        self.settings = SimpleNamespace(get_target=lambda _pbx_id: self._target)

    def call_tool_internal(self, tool_name: str, args: dict[str, object]):
        if tool_name in {"asterisk.health", "freeswitch.health"}:
            return {"ok": True, "data": {"ok": True}}
        if tool_name == "telecom.endpoints":
            endpoint_filter = args.get("filter", {}) if isinstance(args.get("filter"), dict) else {}
            contains = endpoint_filter.get("contains")
            if contains == "1001":
                return {"ok": True, "data": {"items": [{"id": "1001", "status": "Reachable"}]}}
            return {"ok": True, "data": {"items": []}}
        if tool_name == "telecom.registrations":
            # no matching registration rows to force a no-contact bucket
            return {"ok": True, "data": {"items": []}}
        if tool_name == "telecom.logs":
            return {"ok": True, "data": {"items": [{"message": "sample"}]}}
        if tool_name == "telecom.channels":
            return {"ok": True, "data": {"items": [{"channel_id": "PJSIP/1001-0001", "duration_s": 45}]}}
        if tool_name == "telecom.calls":
            return {"ok": True, "data": {"items": [{"call_id": "c-1"}]}}
        if tool_name == "asterisk.bridges":
            return {"ok": True, "data": {"items": []}}
        if tool_name == "asterisk.channel_details":
            return {"ok": True, "data": {"channel_id": args.get("channel_id")}}
        if tool_name == "asterisk.version":
            return {"ok": True, "data": {"version": "20.7.0"}}
        if tool_name == "asterisk.modules":
            return {"ok": True, "data": {"items": [{"module": "res_pjsip.so"}]}}
        if tool_name == "telecom.summary":
            return {
                "ok": True,
                "data": {
                    "channels_active": 1,
                    "registrations": {
                        "endpoints_registered": 1,
                        "endpoints_unreachable": 0,
                    },
                },
            }
        if tool_name == "telecom.inventory":
            return {"ok": True, "data": {"items": [{"key": "version", "value": "20.7.0"}]}}
        if tool_name == "telecom.compare_targets":
            return {
                "ok": True,
                "data": {
                    "summary": "Compared pbx-1 vs fs-1",
                    "items": [{"field": "version", "pbx_a": "20", "pbx_b": "1.10"}],
                    "drift_categories": [{"category": "version_mismatch"}],
                },
            }
        if tool_name == "telecom.run_registration_probe":
            return {"ok": True, "data": {"probe_id": "probe-1", "initiated": True}}
        if tool_name == "telecom.verify_cleanup":
            return {"ok": True, "data": {"clean": True}}
        raise AssertionError(f"unexpected tool call: {tool_name}")


def test_run_playbook_sip_registration_triage_shape() -> None:
    _target, data = telecom.run_playbook(
        _Ctx(),
        {"name": "sip_registration_triage", "pbx_id": "pbx-1", "endpoint": "1001"},
    )
    assert data["playbook"] == "sip_registration_triage"
    assert data["bucket"] == "endpoint_present_but_no_contacts"
    assert isinstance(data["steps"], list)
    assert data["evidence"]["contacts"] == 0


def test_run_playbook_drift_comparison() -> None:
    _target, data = telecom.run_playbook(
        _Ctx(),
        {"name": "pbx_drift_comparison", "pbx_a": "pbx-1", "pbx_b": "fs-1"},
    )
    assert data["playbook"] == "pbx_drift_comparison"
    assert data["bucket"] == "risky_drift"


def test_run_smoke_suite_baseline() -> None:
    _target, data = telecom.run_smoke_suite(
        _Ctx(),
        {"name": "baseline_read_only_smoke", "pbx_id": "pbx-1"},
    )
    assert data["suite"] == "baseline_read_only_smoke"
    assert len(data["checks"]) == 7
    assert set(data["counts"]) == {"passed", "warning", "failed"}


def test_active_validation_smoke_blocked_in_inspect(monkeypatch) -> None:
    monkeypatch.setenv("TELECOM_MCP_ENABLE_ACTIVE_PROBES", "1")
    with pytest.raises(ToolError) as exc:
        telecom.run_smoke_suite(
            _Ctx(mode="inspect"),
            {"name": "active_validation_smoke", "pbx_id": "pbx-1"},
        )
    assert exc.value.code == NOT_ALLOWED


def test_unknown_playbook_rejected() -> None:
    with pytest.raises(ToolError) as exc:
        telecom.run_playbook(_Ctx(), {"name": "does_not_exist", "pbx_id": "pbx-1"})
    assert exc.value.code == VALIDATION_ERROR
