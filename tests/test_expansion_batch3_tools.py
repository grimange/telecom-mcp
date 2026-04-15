from __future__ import annotations

from types import SimpleNamespace

from telecom_mcp.tools import telecom


class _Ctx:
    def __init__(self) -> None:
        def _get_target(pbx_id: str):
            if pbx_id == "pbx-1":
                return SimpleNamespace(
                    id="pbx-1",
                    type="asterisk",
                    host="10.0.0.10",
                    ami=object(),
                    ari=object(),
                    esl=None,
                    logs=object(),
                )
            return SimpleNamespace(
                id="fs-1",
                type="freeswitch",
                host="10.0.0.20",
                ami=None,
                ari=None,
                esl=object(),
                logs=None,
            )

        self.settings = SimpleNamespace(get_target=_get_target)

    def call_tool_internal(self, tool_name: str, args: dict[str, object]):
        pbx_id = str(args.get("pbx_id", ""))
        if tool_name == "telecom.inventory":
            _target, data = telecom.inventory(self, {"pbx_id": pbx_id})
            return {"ok": True, "data": data}
        if tool_name == "telecom.summary":
            if pbx_id == "pbx-1":
                return {
                    "ok": True,
                    "data": {
                        "channels_active": 5,
                        "registrations": {
                            "endpoints_registered": 10,
                            "endpoints_unreachable": 2,
                        },
                    },
                }
            return {
                "ok": True,
                "data": {
                    "channels_active": 3,
                    "registrations": {
                        "endpoints_registered": 7,
                        "endpoints_unreachable": 4,
                    },
                },
            }
        if tool_name in {"asterisk.version", "freeswitch.version"}:
            return {
                "ok": True,
                "data": {"version": "22.5.1" if pbx_id == "pbx-1" else "1.10.11"},
            }
        if tool_name in {"asterisk.modules", "freeswitch.modules"}:
            if pbx_id == "pbx-1":
                module_items = [{"module": "res_pjsip.so"}, {"module": "chan_pjsip.so"}]
            else:
                module_items = [{"module": "mod_sofia"}, {"module": "mod_commands"}]
            return {
                "ok": True,
                "data": {"items": module_items, "counts": {"total": len(module_items)}},
            }
        if tool_name == "asterisk.pjsip_show_endpoints":
            return {"ok": True, "data": {"items": [{"endpoint": "1001"}]}}
        if tool_name == "freeswitch.registrations":
            return {"ok": True, "data": {"items": [{"user": "1001"}]}}
        raise AssertionError(f"unexpected tool call: {tool_name}")


def test_inventory_includes_baseline_and_posture() -> None:
    _target, data = telecom.inventory(_Ctx(), {"pbx_id": "pbx-1"})
    assert data["baseline"]["platform"] == "asterisk"
    assert data["baseline"]["connectors"]["ami"] is True
    assert data["posture"]["version_posture"]["status"] == "known"
    assert data["posture"]["module_posture"]["status"] == "known"
    assert data["posture"]["module_posture"]["critical_missing"] == []


def test_compare_targets_reports_drift_items() -> None:
    _target, data = telecom.compare_targets(
        _Ctx(),
        {"pbx_a": "pbx-1", "pbx_b": "fs-1"},
    )
    assert data["tool"] == "telecom.compare_targets"
    assert data["counts"]["differences"] >= 1
    assert data["counts"]["drift_categories"] >= 1
    fields = {item["field"] for item in data["items"]}
    assert "platform" in fields
