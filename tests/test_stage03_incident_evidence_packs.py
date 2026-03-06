from __future__ import annotations

from types import SimpleNamespace

import pytest

from telecom_mcp.errors import ToolError, VALIDATION_ERROR
from telecom_mcp.tools import telecom


@pytest.fixture(autouse=True)
def _reset_pack_store() -> None:
    telecom._EVIDENCE_PACKS.clear()


class _Ctx:
    def __init__(self, *, target_type: str = "asterisk") -> None:
        self.mode = SimpleNamespace(value="inspect")
        self._target = SimpleNamespace(
            id="pbx-1" if target_type == "asterisk" else "fs-1",
            type=target_type,
        )
        self.settings = SimpleNamespace(get_target=lambda _pbx_id: self._target)

    def call_tool_internal(self, tool_name: str, args: dict[str, object]):
        if tool_name == "telecom.summary":
            return {"ok": True, "data": {"channels_active": 1}}
        if tool_name == "telecom.capture_snapshot":
            return {"ok": True, "data": {"snapshot_id": "snap-1", "summary": {"pbx_id": "pbx-1"}}}
        if tool_name in {"telecom.endpoints", "telecom.registrations", "telecom.channels", "telecom.calls", "telecom.logs"}:
            return {"ok": True, "data": {"items": [{"id": "x-1"}]}}
        if tool_name in {"asterisk.version", "freeswitch.version"}:
            return {"ok": True, "data": {"version": "1.0.0"}}
        if tool_name in {"asterisk.modules", "freeswitch.modules"}:
            return {"ok": True, "data": {"items": [{"module": "res_pjsip.so"}]}}
        if tool_name in {"asterisk.pjsip_show_endpoints", "asterisk.pjsip_show_contacts", "freeswitch.channels", "freeswitch.calls", "freeswitch.sofia_status"}:
            return {"ok": True, "data": {"items": [{"id": "v-1"}]}}
        if tool_name == "telecom.run_smoke_suite":
            return {"ok": True, "data": {"suite": args.get("name"), "status": "passed", "counts": {"passed": 3, "warning": 0, "failed": 0}}}
        if tool_name == "telecom.run_playbook":
            return {"ok": True, "data": {"playbook": args.get("name"), "status": "warning", "bucket": "insufficient_evidence"}}
        if tool_name == "telecom.audit_target":
            return {"ok": True, "data": {"score": 82, "status": "acceptable", "violations": []}}
        if tool_name == "telecom.drift_target_vs_baseline":
            return {"ok": True, "data": {"items": [], "summary": "no drift"}}
        if tool_name == "telecom.verify_cleanup":
            return {"ok": True, "data": {"clean": True}}
        if tool_name == "telecom.release_gate_decision":
            return {
                "ok": True,
                "data": {
                    "decision": {"decision": "allow", "reasons": []},
                    "validation_summary": {"smoke_status": "passed"},
                },
            }
        raise AssertionError(f"unexpected tool call: {tool_name}")


def test_capture_incident_evidence_collects_items() -> None:
    _target, data = telecom.capture_incident_evidence(_Ctx(), {"pbx_id": "pbx-1"})
    assert data["tool"] == "telecom.capture_incident_evidence"
    assert data["counts"]["evidence_items"] > 0


def test_generate_pack_and_reconstruct_timeline() -> None:
    ctx = _Ctx()
    _target, generated = telecom.generate_evidence_pack(
        ctx, {"pbx_id": "pbx-1", "incident_type": "outbound_failure", "incident_id": "inc-1"}
    )
    pack_id = generated["pack_id"]
    assert generated["pack"]["integrity_hash"]

    _target, rebuilt = telecom.reconstruct_incident_timeline(ctx, {"pack_id": pack_id})
    assert rebuilt["tool"] == "telecom.reconstruct_incident_timeline"
    assert isinstance(rebuilt["timeline"], list)


def test_export_evidence_pack_formats() -> None:
    ctx = _Ctx()
    _target, generated = telecom.generate_evidence_pack(ctx, {"pbx_id": "pbx-1"})
    pack_id = generated["pack_id"]

    _target, md = telecom.export_evidence_pack(ctx, {"pack_id": pack_id, "format": "markdown"})
    assert "Telecom Incident Evidence Pack" in md["export"]

    _target, zipped = telecom.export_evidence_pack(ctx, {"pack_id": pack_id, "format": "zip"})
    assert zipped["format"] == "zip"
    assert zipped["export"]["manifest"]["metadata.json"] is True
    assert "sensitivity_labels" in zipped["export"]["pack"]


def test_export_evidence_pack_redacts_sensitive_fields_and_bounded_items(monkeypatch) -> None:
    monkeypatch.setenv("TELECOM_MCP_EXPORT_MAX_EVIDENCE_ITEMS", "1")
    ctx = _Ctx()
    _target, generated = telecom.generate_evidence_pack(ctx, {"pbx_id": "pbx-1"})
    pack_id = generated["pack_id"]
    pack = telecom._EVIDENCE_PACKS[pack_id]
    items = pack["evidence_items"]
    if items:
        items[0]["payload"] = {"token": "secret-token", "Authorization": "Bearer abc"}
    else:
        pack["evidence_items"] = [{"payload": {"token": "secret-token"}}]

    _target, exported = telecom.export_evidence_pack(ctx, {"pack_id": pack_id, "format": "json"})
    blob = str(exported["export"])
    assert "secret-token" not in blob
    assert "Bearer abc" not in blob
    assert "***REDACTED***" in blob
    assert len(exported["export"]["evidence_items"]) == 1


def test_export_evidence_pack_rejects_bad_format() -> None:
    with pytest.raises(ToolError) as exc:
        telecom.export_evidence_pack(_Ctx(), {"pack_id": "missing", "format": "xml"})
    assert exc.value.code == VALIDATION_ERROR
