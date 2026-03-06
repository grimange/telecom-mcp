from __future__ import annotations

from types import SimpleNamespace

import pytest

from telecom_mcp.errors import ToolError, UPSTREAM_ERROR, VALIDATION_ERROR
from telecom_mcp.tools import telecom


@pytest.fixture(autouse=True)
def _clear_baseline_store() -> None:
    telecom._BASELINE_STORE.clear()


class _Ctx:
    def __init__(self, *, target_type: str = "asterisk") -> None:
        self.mode = SimpleNamespace(value="inspect")
        self._target = SimpleNamespace(
            id="pbx-1" if target_type == "asterisk" else "fs-1",
            type=target_type,
            host="127.0.0.1",
        )
        self.settings = SimpleNamespace(get_target=lambda _pbx_id: self._target)

    def call_tool_internal(self, tool_name: str, args: dict[str, object]):
        if tool_name == "telecom.summary":
            return {
                "ok": True,
                "data": {
                    "channels_active": 2,
                    "registrations": {
                        "endpoints_registered": 8,
                        "endpoints_unreachable": 1,
                    },
                    "confidence": {"trunks": "medium"},
                },
            }
        if tool_name == "telecom.inventory":
            return {
                "ok": True,
                "data": {
                    "items": [
                        {"key": "version", "value": "20.7.0"},
                        {"key": "transport_tls", "value": True},
                    ],
                    "posture": {
                        "module_posture": {
                            "critical_missing": [],
                            "risky_loaded": [],
                        }
                    },
                },
            }
        if tool_name == "asterisk.version":
            return {"ok": True, "data": {"version": "20.7.0"}}
        if tool_name == "asterisk.modules":
            return {
                "ok": True,
                "data": {
                    "items": [
                        {"module": "res_pjsip.so"},
                        {"module": "chan_pjsip.so"},
                    ]
                },
            }
        if tool_name == "telecom.endpoints":
            return {"ok": True, "data": {"items": [{"id": "1001"}, {"id": "1002"}]}}
        if tool_name == "telecom.registrations":
            return {"ok": True, "data": {"items": [{"endpoint": "1001"}]}}
        if tool_name == "telecom.channels":
            return {"ok": True, "data": {"items": [{"channel_id": "PJSIP/1001-0001"}]}}
        if tool_name == "telecom.logs":
            return {"ok": True, "data": {"items": [{"message": "ok"}]}}
        if tool_name == "telecom.compare_targets":
            return {
                "ok": True,
                "data": {
                    "summary": "Compared pbx-1 vs fs-1",
                    "items": [{"field": "version", "pbx_a": "20.7.0", "pbx_b": "1.10.9"}],
                    "drift_categories": [{"category": "version_mismatch"}],
                },
            }
        if tool_name == "telecom.audit_target":
            # delegate to real tool for nested calls
            _target, data = telecom.audit_target(self, args)
            return {"ok": True, "data": data}
        if tool_name == "telecom.audit_report":
            _target, data = telecom.audit_report(self, args)
            return {"ok": True, "data": data}
        raise AssertionError(f"unexpected tool call: {tool_name}")


def test_baseline_create_and_show() -> None:
    _target, created = telecom.baseline_create(
        _Ctx(), {"pbx_id": "pbx-1", "baseline_id": "base-1"}
    )
    assert created["baseline_id"] == "base-1"

    _target, shown = telecom.baseline_show(_Ctx(), {"baseline_id": "base-1"})
    assert shown["baseline_id"] == "base-1"
    assert shown["baseline"]["platform"] == "asterisk"


def test_audit_target_returns_score_and_violations() -> None:
    ctx = _Ctx()
    _ = telecom.baseline_create(ctx, {"pbx_id": "pbx-1", "baseline_id": "base-1"})
    _target, data = telecom.audit_target(
        ctx, {"pbx_id": "pbx-1", "baseline_id": "base-1"}
    )
    assert isinstance(data["score"], int)
    assert data["status"] in {"compliant", "acceptable", "degraded", "high_risk"}
    assert isinstance(data["policy_results"], list)


def test_drift_target_vs_baseline_and_compare_targets() -> None:
    ctx = _Ctx()
    _ = telecom.baseline_create(ctx, {"pbx_id": "pbx-1", "baseline_id": "base-1"})

    _target, drift = telecom.drift_target_vs_baseline(
        ctx, {"pbx_id": "pbx-1", "baseline_id": "base-1"}
    )
    assert drift["tool"] == "telecom.drift_target_vs_baseline"

    _target, compare = telecom.drift_compare_targets(
        ctx, {"pbx_a": "pbx-1", "pbx_b": "fs-1"}
    )
    assert compare["tool"] == "telecom.drift_compare_targets"
    assert compare["counts"]["drift_categories"] == 1


def test_audit_report_and_export_markdown() -> None:
    ctx = _Ctx()
    _ = telecom.baseline_create(ctx, {"pbx_id": "pbx-1", "baseline_id": "base-1"})

    _target, report = telecom.audit_report(
        ctx, {"pbx_id": "pbx-1", "baseline_id": "base-1"}
    )
    assert "PBX Audit Report" in report["report"]

    _target, exported = telecom.audit_export(
        ctx, {"pbx_id": "pbx-1", "baseline_id": "base-1", "format": "markdown"}
    )
    assert exported["format"] == "markdown"
    assert "PBX Audit Report" in exported["export"]


def test_audit_export_rejects_unknown_format() -> None:
    with pytest.raises(ToolError) as exc:
        telecom.audit_export(_Ctx(), {"pbx_id": "pbx-1", "format": "xml"})
    assert exc.value.code == VALIDATION_ERROR


def test_baseline_create_fails_closed_on_strict_state_persistence(monkeypatch) -> None:
    monkeypatch.setenv("TELECOM_MCP_STRICT_STATE_PERSISTENCE", "1")
    monkeypatch.setenv("TELECOM_MCP_STATE_DIR", "/dev/null")
    with pytest.raises(ToolError) as exc:
        telecom.baseline_create(
            _Ctx(), {"pbx_id": "pbx-1", "baseline_id": "base-strict"}
        )
    assert exc.value.code == UPSTREAM_ERROR
