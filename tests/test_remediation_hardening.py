from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from telecom_mcp.authz import Mode
from telecom_mcp.config import load_settings
from telecom_mcp.errors import (
    CONNECTION_FAILED,
    NOT_ALLOWED,
    NOT_FOUND,
    TIMEOUT,
    UPSTREAM_ERROR,
    VALIDATION_ERROR,
    ToolError,
)
from telecom_mcp.normalize.asterisk import (
    extract_pjsip_endpoint_items,
    normalize_pjsip_endpoint,
    normalize_pjsip_endpoints,
)
from telecom_mcp.server import TelecomMCPServer
from telecom_mcp.tools import asterisk, freeswitch, telecom


def _make_settings(tmp_path, *, timeout_s: float = 5.0):
    config_file = tmp_path / "targets.yaml"
    config_file.write_text(
        """
targets:
  - id: pbx-1
    type: asterisk
    host: 10.0.0.10
    ari:
      url: http://10.0.0.10:8088
      username_env: AST_ARI_USER_PBX1
      password_env: AST_ARI_PASS_PBX1
      app: telecom_mcp
    ami:
      host: 10.0.0.10
      port: 5038
      username_env: AST_AMI_USER_PBX1
      password_env: AST_AMI_PASS_PBX1
""",
        encoding="utf-8",
    )
    return load_settings(config_file, mode="inspect", tool_timeout_seconds=timeout_s)


def test_tool_timeout_returns_standard_timeout_error(tmp_path) -> None:
    settings = _make_settings(tmp_path, timeout_s=0.01)
    server = TelecomMCPServer(settings)

    def _slow_tool(_ctx, _args):
        time.sleep(0.02)
        return {"type": "telecom", "id": "pbx-1"}, {"ok": True}

    server.tool_registry["test.slow"] = (_slow_tool, Mode.INSPECT)
    resp = server.execute_tool(tool_name="test.slow", args={"pbx_id": "pbx-1"})

    assert resp["ok"] is False
    assert resp["error"]["code"] == TIMEOUT
    assert resp["error"]["details"]["timeout_seconds"] == 0.01


def test_normalize_endpoint_error_response_sets_exists_false() -> None:
    payload = normalize_pjsip_endpoint(
        "1001", {"Response": "Error", "Message": "Permission denied"}
    )
    assert payload["exists"] is False


def test_extract_pjsip_endpoint_items_parses_event_list() -> None:
    ami_response = {
        "raw": (
            "Response: Success\r\nEventList: start\r\nMessage: list will follow\r\n\r\n"
            "Event: EndpointList\r\nObjectName: 1001\r\nStatus: Available\r\nContacts: 1\r\n\r\n"
            "Event: EndpointList\r\nObjectName: 1002\r\nStatus: Unavailable\r\nContacts: 0\r\n\r\n"
            "Event: EndpointListComplete\r\nEventList: Complete\r\nListItems: 2\r\n\r\n"
        )
    }
    items = extract_pjsip_endpoint_items(ami_response)
    assert [item["ObjectName"] for item in items] == ["1001", "1002"]


def test_extract_pjsip_endpoint_items_avoids_unknown_fallback_when_events_present() -> None:
    ami_response = {
        "raw": (
            "Response: Success\r\nEventList: start\r\nMessage: list will follow\r\n\r\n"
            "Event: ContactStatusDetail\r\nURI: sip:1001@10.0.0.5:5060\r\nStatus: Reachable\r\n\r\n"
            "Event: EndpointListComplete\r\nEventList: Complete\r\nListItems: 1\r\n\r\n"
        )
    }
    items = extract_pjsip_endpoint_items(ami_response)
    assert len(items) == 1
    assert items[0]["URI"] == "sip:1001@10.0.0.5:5060"


def test_extract_pjsip_endpoint_items_drops_success_payload_without_identifier() -> None:
    items = extract_pjsip_endpoint_items({"Response": "Success", "Message": "ok"})
    assert items == []


def test_normalize_pjsip_endpoints_drops_unidentified_rows() -> None:
    payload = normalize_pjsip_endpoints(
        [{"ObjectName": "1001", "Status": "Available"}, {"Status": "Unknown"}],
        50,
    )
    assert payload["items"] == [{"endpoint": "1001", "state": "Available", "contacts": 0}]
    assert payload["data_quality"]["completeness"] == "partial"


def test_pjsip_show_endpoint_maps_permission_denied(monkeypatch) -> None:
    class _DummyAMI:
        def send_action(self, _action):
            return {"Response": "Error", "Message": "Permission denied"}

        def close(self):
            return None

    target = SimpleNamespace(type="asterisk", id="pbx-1")

    def _fake_connectors(_ctx, _pbx_id):
        return target, _DummyAMI(), SimpleNamespace(close=lambda: None)

    monkeypatch.setattr(asterisk, "_connectors", _fake_connectors)

    with pytest.raises(ToolError) as exc:
        asterisk.pjsip_show_endpoint(
            SimpleNamespace(settings=None), {"pbx_id": "pbx-1", "endpoint": "1001"}
        )

    assert exc.value.code == NOT_ALLOWED


def test_summary_includes_data_quality_metadata() -> None:
    class _Ctx:
        settings = SimpleNamespace(get_target=lambda _pbx_id: SimpleNamespace(type="asterisk", id="pbx-1"))

        def call_tool_internal(self, tool_name: str, _args: dict[str, object]):
            if tool_name == "asterisk.health":
                return {"data": {"asterisk_version": "22.5.2"}}
            if tool_name == "asterisk.active_channels":
                return {"data": {"channels": [{"channel_id": "1"}, {"channel_id": "2"}]}}
            if tool_name == "asterisk.pjsip_show_endpoints":
                return {
                    "data": {
                        "items": [
                            {"endpoint": "1001", "contacts": 1},
                            {"endpoint": "1002", "contacts": 0},
                        ]
                    }
                }
            raise AssertionError(f"unexpected tool call: {tool_name}")

    target, data = telecom.summary(_Ctx(), {"pbx_id": "pbx-1"})
    assert target == {"type": "asterisk", "id": "pbx-1"}
    assert data["channels_active"] == 2
    assert data["registrations"]["endpoints_registered"] == 1
    assert data["data_quality"]["completeness"] == "partial"
    assert isinstance(data["warnings"], list)


def test_pjsip_show_registration_maps_permission_denied(monkeypatch) -> None:
    class _DummyAMI:
        def send_action(self, _action):
            return {"Response": "Error", "Message": "Permission denied"}

        def close(self):
            return None

    target = SimpleNamespace(type="asterisk", id="pbx-1")

    def _fake_connectors(_ctx, _pbx_id):
        return target, _DummyAMI(), SimpleNamespace(close=lambda: None)

    monkeypatch.setattr(asterisk, "_connectors", _fake_connectors)

    with pytest.raises(ToolError) as exc:
        asterisk.pjsip_show_registration(
            SimpleNamespace(settings=None),
            {"pbx_id": "pbx-1", "registration": "carrier-a"},
        )

    assert exc.value.code == NOT_ALLOWED


def test_channel_details_fallback_maps_permission_denied(monkeypatch) -> None:
    class _DummyAMI:
        def send_action(self, _action):
            return {"Response": "Error", "Message": "Permission denied"}

        def close(self):
            return None

    class _DummyARI:
        def get(self, _path):
            raise ToolError(NOT_FOUND, "missing channel")

        def close(self):
            return None

    target = SimpleNamespace(type="asterisk", id="pbx-1")

    def _fake_connectors(_ctx, _pbx_id):
        return target, _DummyAMI(), _DummyARI()

    monkeypatch.setattr(asterisk, "_connectors", _fake_connectors)

    with pytest.raises(ToolError) as exc:
        asterisk.channel_details(
            SimpleNamespace(settings=None),
            {"pbx_id": "pbx-1", "channel_id": "PJSIP/1001-000001"},
        )

    assert exc.value.code == NOT_ALLOWED


def test_capture_snapshot_avoids_duplicate_summary_calls() -> None:
    class _Ctx:
        settings = SimpleNamespace(
            get_target=lambda _pbx_id: SimpleNamespace(type="asterisk", id="pbx-1")
        )

        def __init__(self):
            self.calls: dict[str, int] = {}

        def call_tool_internal(self, tool_name: str, _args: dict[str, object]):
            self.calls[tool_name] = self.calls.get(tool_name, 0) + 1
            if tool_name == "asterisk.health":
                return {"data": {"asterisk_version": "22.5.2"}}
            if tool_name == "asterisk.active_channels":
                return {"data": {"channels": [{"channel_id": "1"}]}}
            if tool_name == "asterisk.pjsip_show_endpoints":
                return {"data": {"items": [{"endpoint": "1001", "contacts": 1}]}}
            raise AssertionError(f"unexpected tool call: {tool_name}")

    ctx = _Ctx()
    _target, data = telecom.capture_snapshot(ctx, {"pbx_id": "pbx-1"})

    assert data["summary"]["channels_active"] == 1
    assert ctx.calls.get("telecom.summary", 0) == 0
    assert ctx.calls["asterisk.health"] == 1
    assert ctx.calls["asterisk.active_channels"] == 1
    assert ctx.calls["asterisk.pjsip_show_endpoints"] == 1
    assert data["raw"]["asterisk"]["ami"]["pjsip_show_endpoints"]["items"][0]["endpoint"] == "1001"
    assert data["raw"]["asterisk"]["ari"]["active_channels"]["channels"][0]["channel_id"] == "1"


def test_summary_fail_on_degraded_raises_tool_error() -> None:
    class _Ctx:
        settings = SimpleNamespace(
            get_target=lambda _pbx_id: SimpleNamespace(type="asterisk", id="pbx-1")
        )

        def call_tool_internal(self, tool_name: str, _args: dict[str, object]):
            if tool_name == "asterisk.health":
                return {"ok": True, "correlation_id": "c-ok", "data": {"asterisk_version": "22.5.2"}}
            if tool_name == "asterisk.active_channels":
                return {
                    "ok": False,
                    "correlation_id": "c-fail",
                    "error": {"code": "CONNECTION_FAILED", "message": "unreachable"},
                }
            if tool_name == "asterisk.pjsip_show_endpoints":
                return {"ok": True, "correlation_id": "c-end", "data": {"items": []}}
            raise AssertionError(f"unexpected tool call: {tool_name}")

    with pytest.raises(ToolError) as exc:
        telecom.summary(_Ctx(), {"pbx_id": "pbx-1", "fail_on_degraded": True})
    assert exc.value.code == "UPSTREAM_ERROR"


def test_summary_degraded_registration_counters_are_nullable() -> None:
    class _Ctx:
        settings = SimpleNamespace(
            get_target=lambda _pbx_id: SimpleNamespace(type="asterisk", id="pbx-1")
        )

        def call_tool_internal(self, tool_name: str, _args: dict[str, object]):
            if tool_name == "asterisk.health":
                return {"ok": True, "correlation_id": "c-ok", "data": {"asterisk_version": "22.5.2"}}
            if tool_name == "asterisk.active_channels":
                return {"ok": True, "correlation_id": "c-ch", "data": {"channels": []}}
            if tool_name == "asterisk.pjsip_show_endpoints":
                return {
                    "ok": False,
                    "correlation_id": "c-end-fail",
                    "error": {"code": "NOT_ALLOWED", "message": "permission denied"},
                }
            raise AssertionError(f"unexpected tool call: {tool_name}")

    _target, data = telecom.summary(_Ctx(), {"pbx_id": "pbx-1"})
    assert data["degraded"] is True
    assert data["registrations"]["endpoints_registered"] is None
    assert data["registrations"]["endpoints_unreachable"] is None
    assert data["confidence"]["registrations"] == "low"
    assert data["channels_active"] == 0
    assert data["confidence"]["channels"] == "high"


def test_capture_snapshot_fail_on_degraded_raises_tool_error() -> None:
    class _Ctx:
        settings = SimpleNamespace(
            get_target=lambda _pbx_id: SimpleNamespace(type="asterisk", id="pbx-1")
        )

        def call_tool_internal(self, tool_name: str, _args: dict[str, object]):
            if tool_name == "asterisk.health":
                return {"ok": True, "correlation_id": "c-ok", "data": {"asterisk_version": "22.5.2"}}
            if tool_name == "asterisk.active_channels":
                return {
                    "ok": False,
                    "correlation_id": "c-fail",
                    "error": {"code": "CONNECTION_FAILED", "message": "unreachable"},
                }
            if tool_name == "asterisk.pjsip_show_endpoints":
                return {"ok": True, "correlation_id": "c-end", "data": {"items": []}}
            raise AssertionError(f"unexpected tool call: {tool_name}")

    with pytest.raises(ToolError) as exc:
        telecom.capture_snapshot(_Ctx(), {"pbx_id": "pbx-1", "fail_on_degraded": True})
    assert exc.value.code == "UPSTREAM_ERROR"


def test_capture_snapshot_rejects_non_boolean_include_flags() -> None:
    class _Ctx:
        settings = SimpleNamespace(
            get_target=lambda _pbx_id: SimpleNamespace(type="asterisk", id="pbx-1")
        )

    with pytest.raises(ToolError) as exc:
        telecom.capture_snapshot(_Ctx(), {"pbx_id": "pbx-1", "include": {"calls": "false"}})
    assert exc.value.code == VALIDATION_ERROR


def test_unknown_ami_error_maps_to_upstream_error() -> None:
    with pytest.raises(ToolError) as exc:
        asterisk._raise_for_ami_error({"Response": "Error", "Message": "Unexpected backend fault"})
    assert exc.value.code == UPSTREAM_ERROR


def test_reload_pjsip_validates_ami_command_outcome(monkeypatch) -> None:
    class _DummyAMI:
        def send_action(self, _action):
            return {"Response": "Success", "Output": "No such command 'pjsip reload'"}

        def close(self):
            return None

    target = SimpleNamespace(type="asterisk", id="pbx-1")

    def _fake_connectors(_ctx, _pbx_id):
        return target, _DummyAMI(), SimpleNamespace(close=lambda: None)

    monkeypatch.setattr(asterisk, "_connectors", _fake_connectors)

    with pytest.raises(ToolError) as exc:
        asterisk.reload_pjsip(SimpleNamespace(settings=None), {"pbx_id": "pbx-1"})
    assert exc.value.code == UPSTREAM_ERROR


def test_reloadxml_validates_esl_command_outcome(monkeypatch) -> None:
    class _DummyESL:
        def api(self, _cmd):
            return "-ERR command not allowed"

        def close(self):
            return None

    target = SimpleNamespace(type="freeswitch", id="fs-1")

    def _fake_connector(_ctx, _pbx_id):
        return target, _DummyESL()

    monkeypatch.setattr(freeswitch, "_connector", _fake_connector)

    with pytest.raises(ToolError) as exc:
        freeswitch.reloadxml(SimpleNamespace(settings=None), {"pbx_id": "fs-1"})
    assert exc.value.code == NOT_ALLOWED


def test_asterisk_health_reports_degraded_when_ami_capability_denied(monkeypatch) -> None:
    class _DummyAMI:
        def ping(self):
            return {"ok": True, "latency_ms": 7}

        def send_action(self, action):
            if action.get("Action") == "PJSIPShowEndpoints":
                return {"Response": "Error", "Message": "Permission denied"}
            return {"Response": "Success", "Message": "ok"}

        def close(self):
            return None

    class _DummyARI:
        def health(self):
            return {"ok": True, "latency_ms": 5, "raw": {"system": {"version": "22.5.2"}}}

        def close(self):
            return None

    target = SimpleNamespace(type="asterisk", id="pbx-1")

    def _fake_connectors(_ctx, _pbx_id):
        return target, _DummyAMI(), _DummyARI()

    monkeypatch.setattr(asterisk, "_connectors", _fake_connectors)

    _target, data = asterisk.health(SimpleNamespace(settings=None), {"pbx_id": "pbx-1"})
    assert data["ami"]["connectivity_ok"] is True
    assert data["ami"]["capability_ok"] is False
    assert data["ami"]["ok"] is False
    assert data["degraded"] is True
    assert data["data_quality"]["degraded"] is True


def test_targets_parser_rejects_bad_indentation(tmp_path) -> None:
    config_file = tmp_path / "targets.yaml"
    config_file.write_text(
        """
targets:
  - id: pbx-1
      type: asterisk
    host: 10.0.0.10
""",
        encoding="utf-8",
    )

    with pytest.raises(ToolError) as exc:
        load_settings(config_file)

    assert exc.value.code == VALIDATION_ERROR


def test_active_channels_fallback_records_data_quality(monkeypatch) -> None:
    class _DummyAMI:
        def send_action(self, _action):
            return {
                "Response": "Success",
                "raw": (
                    "Response: Success\r\nMessage: list follows\r\n\r\n"
                    "Event: CoreShowChannel\r\nUniqueid: 1\r\nChannel: PJSIP/1001-0001\r\n"
                    "ChannelStateDesc: Up\r\nCallerIDNum: 1001\r\nConnectedLineNum: 1002\r\n"
                    "Duration: 3\r\n\r\n"
                    "Event: CoreShowChannelsComplete\r\nEventList: Complete\r\n\r\n"
                ),
            }

        def close(self):
            return None

    class _DummyARI:
        def get(self, _path):
            raise ToolError(CONNECTION_FAILED, "ari unavailable")

        def close(self):
            return None

    target = SimpleNamespace(type="asterisk", id="pbx-1")

    def _fake_connectors(_ctx, _pbx_id):
        return target, _DummyAMI(), _DummyARI()

    monkeypatch.setattr(asterisk, "_connectors", _fake_connectors)

    _target, data = asterisk.active_channels(
        SimpleNamespace(settings=None), {"pbx_id": "pbx-1"}
    )

    assert any(row["channel_id"] == "1" for row in data["channels"])
    assert data["data_quality"]["fallback_used"] is True
    assert data["data_quality"]["fallback_reason"]["code"] == CONNECTION_FAILED


def test_active_channels_does_not_swallow_non_tool_errors(monkeypatch) -> None:
    class _DummyAMI:
        def close(self):
            return None

    class _DummyARI:
        def get(self, _path):
            raise RuntimeError("unexpected parser bug")

        def close(self):
            return None

    target = SimpleNamespace(type="asterisk", id="pbx-1")

    def _fake_connectors(_ctx, _pbx_id):
        return target, _DummyAMI(), _DummyARI()

    monkeypatch.setattr(asterisk, "_connectors", _fake_connectors)

    with pytest.raises(RuntimeError):
        asterisk.active_channels(SimpleNamespace(settings=None), {"pbx_id": "pbx-1"})
