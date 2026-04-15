from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from telecom_mcp.errors import NOT_FOUND, ToolError
from telecom_mcp.tools import asterisk, freeswitch, telecom


class _Ctx:
    def __init__(self, target_type: str = "asterisk") -> None:
        self._target = SimpleNamespace(
            id="pbx-1" if target_type == "asterisk" else "fs-1",
            type=target_type,
            host="127.0.0.1",
            logs=None,
        )
        self.settings = SimpleNamespace(get_target=lambda _pbx_id: self._target)

    def call_tool_internal(self, tool_name: str, _args: dict[str, object]):
        if tool_name == "asterisk.pjsip_show_endpoints":
            return {
                "ok": True,
                "data": {
                    "items": [
                        {"endpoint": "1001", "state": "Reachable", "contacts": 1},
                        {"endpoint": "1002", "state": "Unavailable", "contacts": 0},
                    ]
                },
            }
        if tool_name == "freeswitch.registrations":
            return {
                "ok": True,
                "data": {
                    "items": [
                        {"user": "1001", "status": "REGED", "contact": "sofia/internal/1001"},
                        {"user": "1002", "status": "FAILED", "contact": "sofia/internal/1002"},
                    ]
                },
            }
        if tool_name == "freeswitch.channels":
            return {"ok": True, "data": {"channels": [{"uuid": "u1", "state": "CS_EXECUTE"}]}}
        if tool_name == "freeswitch.calls":
            return {"ok": True, "data": {"calls": [{"call_id": "c1", "state": "ACTIVE", "legs": 2}]}}
        if tool_name == "telecom.summary":
            return {
                "ok": True,
                "data": {
                    "channels_active": 2,
                    "registrations": {"endpoints_registered": 1, "endpoints_unreachable": 1},
                },
            }
        if tool_name in {"asterisk.version", "freeswitch.version"}:
            return {"ok": True, "data": {"version": "1.2.3"}}
        if tool_name in {"asterisk.modules", "freeswitch.modules"}:
            return {"ok": True, "data": {"items": [{"module": "mod_1"}], "counts": {"total": 1}}}
        raise AssertionError(f"unexpected tool call: {tool_name}")


def test_telecom_endpoints_normalized_for_asterisk() -> None:
    target, data = telecom.endpoints(_Ctx("asterisk"), {"pbx_id": "pbx-1"})
    assert target == {"type": "asterisk", "id": "pbx-1"}
    assert data["counts"]["total"] == 2
    assert data["counts"]["unavailable"] == 1
    assert data["items"][0]["status"] in {"available", "unavailable"}


def test_telecom_registrations_normalized_for_freeswitch() -> None:
    target, data = telecom.registrations(_Ctx("freeswitch"), {"pbx_id": "fs-1"})
    assert target == {"type": "freeswitch", "id": "fs-1"}
    assert data["counts"]["total"] == 2
    assert data["counts"]["registered"] == 1


def test_telecom_inventory_collects_batch1_sources() -> None:
    target, data = telecom.inventory(_Ctx("asterisk"), {"pbx_id": "pbx-1"})
    assert target == {"type": "asterisk", "id": "pbx-1"}
    assert data["tool"] == "telecom.inventory"
    assert data["sources"] == [
        "telecom.summary",
        "asterisk.version",
        "asterisk.modules",
        "asterisk.pjsip_show_endpoints",
    ]


def test_asterisk_logs_reads_configured_file(tmp_path: Path) -> None:
    log_file = tmp_path / "asterisk.log"
    log_file.write_text("INFO boot\nWARNING channel\nERROR drop\n", encoding="utf-8")

    ctx = _Ctx("asterisk")
    ctx._target.logs = SimpleNamespace(path=str(log_file), source_command="tail -n 200 asterisk.log")

    _target, data = asterisk.logs(
        ctx,
        {"pbx_id": "pbx-1", "tail": 2, "grep": "R", "level": "error"},
    )

    assert data["tool"] == "asterisk.logs"
    assert data["counts"]["total"] == 1
    assert data["items"][0]["message"] == "ERROR drop"


def test_asterisk_logs_can_be_temporarily_disabled_via_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log_file = tmp_path / "asterisk.log"
    log_file.write_text("ERROR should_not_be_read\n", encoding="utf-8")

    ctx = _Ctx("asterisk")
    ctx._target.logs = SimpleNamespace(path=str(log_file), source_command="tail -n 200 asterisk.log")
    monkeypatch.setenv("TELECOM_MCP_DISABLE_LOCAL_ASTERISK_LOGS", "1")

    _target, data = asterisk.logs(ctx, {"pbx_id": "pbx-1", "tail": 10})

    assert data["tool"] == "asterisk.logs"
    assert data["counts"]["total"] == 0
    assert data["items"] == []
    assert any("TELECOM_MCP_DISABLE_LOCAL_ASTERISK_LOGS" in msg for msg in data["warnings"])


def test_freeswitch_logs_requires_configured_source() -> None:
    with pytest.raises(ToolError) as exc:
        freeswitch.logs(_Ctx("freeswitch"), {"pbx_id": "fs-1"})
    assert exc.value.code == NOT_FOUND


def test_asterisk_pjsip_show_contacts_parses_rows(monkeypatch) -> None:
    class _DummyAmi:
        def send_action(self, _action):
            return {
                "Response": "Success",
                "raw": (
                    "Response: Success\r\nEventList: start\r\n\r\n"
                    "Event: ContactList\r\nObjectName: sip:1001@10.0.0.1:5060\r\nEndpoint: 1001\r\nStatus: Reachable\r\n\r\n"
                    "Event: ContactListComplete\r\nEventList: Complete\r\n\r\n"
                ),
            }

        def close(self):
            return None

    target = SimpleNamespace(type="asterisk", id="pbx-1")

    def _fake_connectors(_ctx, _pbx_id):
        return target, _DummyAmi(), None

    monkeypatch.setattr(asterisk, "_connectors", _fake_connectors)
    _target, data = asterisk.pjsip_show_contacts(
        SimpleNamespace(settings=None),
        {"pbx_id": "pbx-1", "limit": 10},
    )
    assert len(data["items"]) == 1
    assert data["items"][0]["endpoint"] == "1001"


def test_version_tools_parse_backend_output(monkeypatch) -> None:
    class _DummyAmi:
        def send_action(self, _action):
            return {"Response": "Success", "Output": "Asterisk 22.5.1 built by mock"}

        def close(self):
            return None

    class _DummyEsl:
        def api(self, _cmd):
            return "+OK FreeSWITCH Version 1.10.11-release"

        def close(self):
            return None

    asterisk_target = SimpleNamespace(type="asterisk", id="pbx-1")
    freeswitch_target = SimpleNamespace(type="freeswitch", id="fs-1")

    monkeypatch.setattr(
        asterisk,
        "_connectors",
        lambda _ctx, _pbx_id: (asterisk_target, _DummyAmi(), None),
    )
    monkeypatch.setattr(
        freeswitch,
        "_connector",
        lambda _ctx, _pbx_id: (freeswitch_target, _DummyEsl()),
    )

    _atarget, av = asterisk.version(SimpleNamespace(settings=None), {"pbx_id": "pbx-1"})
    _ftarget, fv = freeswitch.version(SimpleNamespace(settings=None), {"pbx_id": "fs-1"})
    assert av["version"] == "22.5.1"
    assert fv["version"] == "1.10.11-release"
