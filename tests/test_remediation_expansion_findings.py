from __future__ import annotations

import importlib
from types import SimpleNamespace


def test_scorecard_history_persists_across_reload(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TELECOM_MCP_STATE_DIR", str(tmp_path))
    from telecom_mcp.tools import telecom as telecom_mod

    importlib.reload(telecom_mod)
    telecom_mod._register_scorecard_history(
        "pbx",
        "pbx-1",
        {"entity_type": "pbx", "entity_id": "pbx-1", "score": 81, "confidence": "high"},
    )

    reloaded = importlib.reload(telecom_mod)
    entries = reloaded._SCORECARD_HISTORY.get("pbx:pbx-1", [])
    assert entries
    assert entries[-1]["score"] == 81


def test_evidence_pack_store_persists_across_reload(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TELECOM_MCP_STATE_DIR", str(tmp_path))
    from telecom_mcp.tools import telecom as telecom_mod

    importlib.reload(telecom_mod)

    class _Ctx:
        mode = SimpleNamespace(value="inspect")
        settings = SimpleNamespace(get_target=lambda _pbx_id: SimpleNamespace(id="pbx-1", type="asterisk"))

        def call_tool_internal(self, tool_name: str, _args: dict[str, object]):
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
                return {"ok": True, "data": {"suite": "baseline", "status": "passed", "counts": {"passed": 3, "warning": 0, "failed": 0}}}
            if tool_name == "telecom.run_playbook":
                return {"ok": True, "data": {"playbook": "x", "status": "warning", "bucket": "insufficient_evidence"}}
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

    _target, generated = telecom_mod.generate_evidence_pack(_Ctx(), {"pbx_id": "pbx-1", "incident_id": "inc-persist"})
    pack_id = generated["pack_id"]

    reloaded = importlib.reload(telecom_mod)
    assert pack_id in reloaded._EVIDENCE_PACKS
