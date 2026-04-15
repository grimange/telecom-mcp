from __future__ import annotations

from types import SimpleNamespace

import pytest

from telecom_mcp.errors import NOT_ALLOWED, ToolError
from telecom_mcp.tools import asterisk, freeswitch, telecom


def test_asterisk_cli_rejects_non_allowlisted_command() -> None:
    with pytest.raises(ToolError) as exc:
        asterisk.cli(
            SimpleNamespace(settings=None),
            {"pbx_id": "pbx-1", "command": "core stop now"},
        )
    assert exc.value.code == NOT_ALLOWED


def test_asterisk_cli_allows_dialplan_show_telecom_mcp_test(monkeypatch) -> None:
    class _DummyAmi:
        def send_action(self, action):
            assert action["Action"] == "Command"
            assert action["Command"] == "dialplan show telecom-mcp-test"
            return {
                "Response": "Success",
                "Output": "[ Context 'telecom-mcp-test' created by 'pbx_config' ]",
            }

        def close(self):
            return None

    monkeypatch.setattr(
        asterisk,
        "_connectors",
        lambda _ctx, _pbx_id: (SimpleNamespace(type="asterisk", id="pbx-1"), _DummyAmi(), None),
    )
    target, data = asterisk.cli(
        SimpleNamespace(settings=None),
        {"pbx_id": "pbx-1", "command": "dialplan show telecom-mcp-test"},
    )
    assert target == {"type": "asterisk", "id": "pbx-1"}
    assert data["counts"]["total"] == 1
    assert data["items"][0]["message"] == "[ Context 'telecom-mcp-test' created by 'pbx_config' ]"


def test_freeswitch_api_rejects_non_allowlisted_command() -> None:
    with pytest.raises(ToolError) as exc:
        freeswitch.api(
            SimpleNamespace(settings=None),
            {"pbx_id": "fs-1", "command": "reloadxml"},
        )
    assert exc.value.code == NOT_ALLOWED


def test_asterisk_core_show_channel_uses_ami(monkeypatch) -> None:
    class _DummyAmi:
        def send_action(self, action):
            assert action["Action"] == "CoreShowChannels"
            return {
                "Response": "Success",
                "Channel": "PJSIP/1001-00000001",
                "ChannelStateDesc": "Up",
                "CallerIDNum": "1001",
                "ConnectedLineNum": "1002",
            }

        def close(self):
            return None

    monkeypatch.setattr(
        asterisk,
        "_connectors",
        lambda _ctx, _pbx_id: (SimpleNamespace(type="asterisk", id="pbx-1"), _DummyAmi(), None),
    )
    target, data = asterisk.core_show_channel(
        SimpleNamespace(settings=None),
        {"pbx_id": "pbx-1", "channel_id": "PJSIP/1001-00000001"},
    )
    assert target == {"type": "asterisk", "id": "pbx-1"}
    assert data["channel_id"] == "PJSIP/1001-00000001"
    assert data["state"] == "Up"


def test_freeswitch_channel_details_parses_uuid_dump(monkeypatch) -> None:
    class _DummyEsl:
        def api(self, command):
            assert command == "uuid_dump abc-123"
            return (
                "+OK\n"
                "Channel-Name: sofia/internal/1001@pbx\n"
                "Channel-State: CS_EXECUTE\n"
                "Caller-Caller-ID-Number: 1001\n"
                "Caller-Destination-Number: 1002\n"
            )

        def close(self):
            return None

    monkeypatch.setattr(
        freeswitch,
        "_connector",
        lambda _ctx, _pbx_id: (SimpleNamespace(type="freeswitch", id="fs-1"), _DummyEsl()),
    )
    target, data = freeswitch.channel_details(
        SimpleNamespace(settings=None),
        {"pbx_id": "fs-1", "uuid": "abc-123"},
    )
    assert target == {"type": "freeswitch", "id": "fs-1"}
    assert data["uuid"] == "abc-123"
    assert data["state"] == "CS_EXECUTE"
    assert data["caller"] == "1001"


def test_asterisk_modules_parses_module_rows(monkeypatch) -> None:
    class _DummyAmi:
        def send_action(self, _action):
            return {
                "Response": "Success",
                "Output": (
                    "Module                         Description                        Use Count  Status\n"
                    "res_pjsip.so                   Basic SIP resource                 5          Running\n"
                    "app_dial.so                    Dialing Application                3          Running\n"
                ),
            }

        def close(self):
            return None

    monkeypatch.setattr(
        asterisk,
        "_connectors",
        lambda _ctx, _pbx_id: (SimpleNamespace(type="asterisk", id="pbx-1"), _DummyAmi(), None),
    )
    _target, data = asterisk.modules(SimpleNamespace(settings=None), {"pbx_id": "pbx-1"})
    assert data["counts"]["total"] == 2
    assert data["items"][0]["module"] == "res_pjsip.so"


def test_freeswitch_modules_parses_module_rows(monkeypatch) -> None:
    class _DummyEsl:
        def api(self, _cmd):
            return "+OK\nmod_sofia\nmod_conference\n"

        def close(self):
            return None

    monkeypatch.setattr(
        freeswitch,
        "_connector",
        lambda _ctx, _pbx_id: (SimpleNamespace(type="freeswitch", id="fs-1"), _DummyEsl()),
    )
    _target, data = freeswitch.modules(SimpleNamespace(settings=None), {"pbx_id": "fs-1"})
    assert data["counts"]["total"] == 2
    assert data["items"][0]["module"] == "mod_sofia"


def test_telecom_diff_snapshots_reports_changes() -> None:
    _target, data = telecom.diff_snapshots(
        SimpleNamespace(),
        {
            "snapshot_a": {
                "snapshot_id": "snap-a",
                "summary": {"channels_active": 1},
                "endpoints": [{"endpoint": "1001", "status": "available"}],
                "calls": [{"call_id": "call-1", "state": "UP"}],
                "trunks": [],
            },
            "snapshot_b": {
                "snapshot_id": "snap-b",
                "summary": {"channels_active": 2},
                "endpoints": [{"endpoint": "1001", "status": "unavailable"}],
                "calls": [{"call_id": "call-2", "state": "UP"}],
                "trunks": [],
            },
        },
    )
    assert data["tool"] == "telecom.diff_snapshots"
    assert data["sections"]["endpoints"]["counts"]["changed"] == 1
    assert data["sections"]["calls"]["counts"]["added"] == 1
    assert data["sections"]["calls"]["counts"]["removed"] == 1
    assert data["summary_delta"]["channels_active"]["delta"] == 1
