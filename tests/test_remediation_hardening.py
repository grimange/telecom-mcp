from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from telecom_mcp.authz import Mode
from telecom_mcp.config import load_settings
from telecom_mcp.errors import (
    AUTH_FAILED,
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


def test_normalize_pjsip_endpoints_aggregates_contact_details() -> None:
    payload = normalize_pjsip_endpoints(
        [
            {"Event": "EndpointList", "ObjectName": "1001", "Status": "Available"},
            {
                "Event": "ContactStatusDetail",
                "URI": "sip:1001@10.0.0.5:5060",
                "Status": "Reachable",
            },
        ],
        50,
    )
    assert payload["items"] == [{"endpoint": "1001", "state": "Available", "contacts": 1}]


def test_asterisk_modules_parses_rows_from_raw_command_output(monkeypatch) -> None:
    class _DummyAMI:
        def send_action(self, _action):
            return {
                "Response": "Error",
                "Message": "Command output follows",
                "raw": (
                    "Response: Error\r\nMessage: Command output follows\r\n\r\n"
                    "Output: Module                         Description                        Use Count  Status\r\n"
                    "Output: res_pjsip.so                   Basic SIP resource                 5          Running\r\n"
                    "Output: app_dial.so                    Dialing Application                3          Running\r\n"
                    "--END COMMAND--\r\n"
                ),
            }

        def close(self):
            return None

    target = SimpleNamespace(type="asterisk", id="pbx-1")

    def _fake_connectors(_ctx, _pbx_id):
        return target, _DummyAMI(), SimpleNamespace(close=lambda: None)

    monkeypatch.setattr(asterisk, "_connectors", _fake_connectors)
    _target, data = asterisk.modules(SimpleNamespace(settings=None), {"pbx_id": "pbx-1"})
    assert data["counts"]["total"] == 2
    assert data["items"][0]["module"] == "res_pjsip.so"
    assert data["items"][1]["module"] == "app_dial.so"


def test_asterisk_modules_falls_back_when_primary_like_output_is_empty(monkeypatch) -> None:
    class _DummyAMI:
        def send_action(self, action):
            command = action.get("Command")
            if command == "module show like":
                return {"Response": "Success", "Message": "No such module loaded"}
            if command == "module show":
                return {
                    "Response": "Success",
                    "Output": (
                        "Module                         Description                        Use Count  Status\n"
                        "res_pjsip.so                   Basic SIP resource                 5          Running\n"
                        "app_dial.so                    Dialing Application                3          Running\n"
                    ),
                }
            if command == "module show like res_":
                return {
                    "Response": "Success",
                    "Output": (
                        "Module                         Description                        Use Count  Status\n"
                        "res_pjsip.so                   Basic SIP resource                 5          Running\n"
                    ),
                }
            raise AssertionError(f"unexpected command: {command}")

        def close(self):
            return None

    target = SimpleNamespace(type="asterisk", id="pbx-1")

    def _fake_connectors(_ctx, _pbx_id):
        return target, _DummyAMI(), SimpleNamespace(close=lambda: None)

    monkeypatch.setattr(asterisk, "_connectors", _fake_connectors)
    _target, data = asterisk.modules(SimpleNamespace(settings=None), {"pbx_id": "pbx-1"})

    assert data["counts"]["total"] == 2
    assert data["source_command"] == "fallback:module show,module show like res_"
    assert any("Primary command returned no module rows." in warning for warning in data["warnings"])
    assert sorted(item["module"] for item in data["items"]) == ["app_dial.so", "res_pjsip.so"]


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


def test_pjsip_show_endpoint_maps_unable_to_retrieve_to_not_found(monkeypatch) -> None:
    class _DummyAMI:
        def send_action(self, _action):
            return {
                "Response": "Error",
                "Message": "Unable to retrieve endpoint definitely_missing",
            }

        def close(self):
            return None

    target = SimpleNamespace(type="asterisk", id="pbx-1")

    def _fake_connectors(_ctx, _pbx_id):
        return target, _DummyAMI(), SimpleNamespace(close=lambda: None)

    monkeypatch.setattr(asterisk, "_connectors", _fake_connectors)

    with pytest.raises(ToolError) as exc:
        asterisk.pjsip_show_endpoint(
            SimpleNamespace(settings=None),
            {"pbx_id": "pbx-1", "endpoint": "definitely_missing"},
        )

    assert exc.value.code == NOT_FOUND


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
                        ],
                        "data_quality": {"completeness": "full"},
                    }
                }
            raise AssertionError(f"unexpected tool call: {tool_name}")

    target, data = telecom.summary(_Ctx(), {"pbx_id": "pbx-1"})
    assert target == {"type": "asterisk", "id": "pbx-1"}
    assert data["channels_active"] == 2
    assert data["registrations"]["endpoints_registered"] == 1
    assert data["data_quality"]["completeness"] == "partial"
    assert "Trunk inventory is unavailable; summary completeness is partial." in data["data_quality"]["issues"]
    assert isinstance(data["warnings"], list)
    assert "Trunk counters unavailable without trunk parsers." in data["notes"]


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


def test_pjsip_show_registration_uses_documented_plural_action(monkeypatch) -> None:
    class _DummyAMI:
        def send_action(self, action):
            assert action["Action"] == "PJSIPShowRegistrationsOutbound"
            return {
                "Response": "Success",
                "raw": (
                    "Response: Success\r\nEventList: start\r\nMessage: list follows\r\n\r\n"
                    "Event: OutboundRegistrationDetail\r\nObjectName: carrier-a\r\nStatus: Registered\r\n\r\n"
                    "Event: OutboundRegistrationDetailComplete\r\nEventList: Complete\r\n\r\n"
                ),
            }

        def close(self):
            return None

    target = SimpleNamespace(type="asterisk", id="pbx-1")

    def _fake_connectors(_ctx, _pbx_id):
        return target, _DummyAMI(), SimpleNamespace(close=lambda: None)

    monkeypatch.setattr(asterisk, "_connectors", _fake_connectors)

    _target, data = asterisk.pjsip_show_registration(
        SimpleNamespace(settings=None),
        {"pbx_id": "pbx-1", "registration": "carrier-a"},
    )
    assert data["registration"] == "carrier-a"
    assert data["state"] == "Registered"


def test_pjsip_show_contacts_normalizes_no_contacts(monkeypatch) -> None:
    class _DummyAMI:
        def send_action(self, _action):
            return {"Response": "Error", "Message": "No Contacts found"}

        def close(self):
            return None

    target = SimpleNamespace(type="asterisk", id="pbx-1")

    def _fake_connectors(_ctx, _pbx_id):
        return target, _DummyAMI(), SimpleNamespace(close=lambda: None)

    monkeypatch.setattr(asterisk, "_connectors", _fake_connectors)

    _target, data = asterisk.pjsip_show_contacts(
        SimpleNamespace(settings=None),
        {"pbx_id": "pbx-1"},
    )
    assert data["items"] == []
    assert data["warnings"] == ["No contacts reported by AMI for this target."]


def test_pjsip_show_endpoints_rejects_unknown_filter_keys() -> None:
    class _Ctx:
        settings = SimpleNamespace(
            get_target=lambda _pbx_id: SimpleNamespace(type="asterisk", id="pbx-1")
        )

    with pytest.raises(ToolError) as exc:
        asterisk.pjsip_show_endpoints(
            _Ctx(),
            {"pbx_id": "pbx-1", "filter": {"unknown_key": "x"}},
        )
    assert exc.value.code == VALIDATION_ERROR


def test_active_channels_rejects_unknown_filter_keys() -> None:
    class _Ctx:
        settings = SimpleNamespace(
            get_target=lambda _pbx_id: SimpleNamespace(type="asterisk", id="pbx-1")
        )

    with pytest.raises(ToolError) as exc:
        asterisk.active_channels(
            _Ctx(),
            {"pbx_id": "pbx-1", "filter": {"bogus": "x"}},
        )
    assert exc.value.code == VALIDATION_ERROR


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


def test_channel_details_fallback_maps_unknown_command_to_not_allowed(monkeypatch) -> None:
    class _DummyAMI:
        def send_action(self, _action):
            return {
                "Response": "Error",
                "Message": "Invalid/unknown command: CoreShowChannels",
            }

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


def test_summary_fail_on_degraded_raises_on_partial_without_failed_sources() -> None:
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
                    "ok": True,
                    "correlation_id": "c-end",
                    "data": {
                        "items": [],
                        "data_quality": {"completeness": "partial"},
                    },
                }
            raise AssertionError(f"unexpected tool call: {tool_name}")

    with pytest.raises(ToolError) as exc:
        telecom.summary(_Ctx(), {"pbx_id": "pbx-1", "fail_on_degraded": True})
    assert exc.value.code == "UPSTREAM_ERROR"


def test_summary_respects_fail_on_degraded_policy_env(monkeypatch) -> None:
    monkeypatch.setenv("TELECOM_MCP_FAIL_ON_DEGRADED_DEFAULT", "1")

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
        telecom.summary(_Ctx(), {"pbx_id": "pbx-1"})
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


def test_capture_snapshot_rejects_unknown_include_and_limits_keys() -> None:
    class _Ctx:
        settings = SimpleNamespace(
            get_target=lambda _pbx_id: SimpleNamespace(type="asterisk", id="pbx-1")
        )

    with pytest.raises(ToolError) as include_exc:
        telecom.capture_snapshot(_Ctx(), {"pbx_id": "pbx-1", "include": {"bogus": True}})
    assert include_exc.value.code == VALIDATION_ERROR

    with pytest.raises(ToolError) as limits_exc:
        telecom.capture_snapshot(_Ctx(), {"pbx_id": "pbx-1", "limits": {"unknown": 1}})
    assert limits_exc.value.code == VALIDATION_ERROR


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


def test_asterisk_connectors_allow_ami_only_for_ami_tools(monkeypatch) -> None:
    target = SimpleNamespace(type="asterisk", id="pbx-1", ami=SimpleNamespace(), ari=None)
    ctx = SimpleNamespace(
        settings=SimpleNamespace(get_target=lambda _pbx_id: target),
        remaining_timeout_s=lambda: 1.0,
    )

    class _DummyAMI:
        def __init__(self, _config, timeout_s=1.0):
            self.timeout_s = timeout_s

    monkeypatch.setattr(asterisk, "AsteriskAMIConnector", _DummyAMI)

    _target, ami, ari = asterisk._connectors(ctx, "pbx-1")
    assert ami is not None
    assert ari is None


def test_active_channels_falls_back_when_ari_missing(monkeypatch) -> None:
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

    target = SimpleNamespace(type="asterisk", id="pbx-1")

    def _fake_connectors(_ctx, _pbx_id, **_kwargs):
        return target, _DummyAMI(), None

    monkeypatch.setattr(asterisk, "_connectors", _fake_connectors)

    _target, data = asterisk.active_channels(
        SimpleNamespace(settings=None), {"pbx_id": "pbx-1"}
    )
    assert any(row["channel_id"] == "1" for row in data["channels"])
    assert data["data_quality"]["fallback_used"] is True


def test_freeswitch_health_rejects_err_status_read(monkeypatch) -> None:
    class _DummyESL:
        def ping(self):
            return {"ok": True, "latency_ms": 5, "raw": "-ERR not allowed"}

        def api(self, _cmd):
            return "+OK FreeSWITCH Version 1.10.0"

        def close(self):
            return None

    target = SimpleNamespace(type="freeswitch", id="fs-1")

    def _fake_connector(_ctx, _pbx_id):
        return target, _DummyESL()

    monkeypatch.setattr(freeswitch, "_connector", _fake_connector)

    with pytest.raises(ToolError) as exc:
        freeswitch.health(SimpleNamespace(settings=None), {"pbx_id": "fs-1"})
    assert exc.value.code == NOT_ALLOWED


def test_freeswitch_channels_rejects_err_read(monkeypatch) -> None:
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
        freeswitch.channels(SimpleNamespace(settings=None), {"pbx_id": "fs-1"})
    assert exc.value.code == NOT_ALLOWED


def test_freeswitch_health_success_includes_profiles_and_version(monkeypatch) -> None:
    class _DummyESL:
        def ping(self):
            return {"ok": True, "latency_ms": 7, "raw": "+OK status"}

        def api(self, cmd: str):
            if cmd == "version":
                return "FreeSWITCH Version 1.10.11-release"
            if cmd == "sofia status":
                return (
                    "+OK Sofia status\n"
                    "Profile: internal RUNNING\n"
                    "Registrations: 2\n"
                    "Gateways: 1\n"
                    "Gateway: gw-primary UP\n"
                )
            raise AssertionError(f"unexpected command: {cmd}")

        def close(self):
            return None

    target = SimpleNamespace(type="freeswitch", id="fs-1")

    def _fake_connector(_ctx, _pbx_id):
        return target, _DummyESL()

    monkeypatch.setattr(freeswitch, "_connector", _fake_connector)

    _target, data = freeswitch.health(SimpleNamespace(settings=None), {"pbx_id": "fs-1"})
    assert data["freeswitch_version"] == "1.10.11-release"
    assert data["profiles"]
    assert data["profiles"][0]["name"] == "internal"
    assert data["transport"]["ok"] is True
    assert data["auth"]["ok"] is True
    assert data["command"]["status"] == "ok"
    assert "raw" not in data


def test_freeswitch_channels_include_raw_returns_stable_envelope(monkeypatch) -> None:
    class _DummyESL:
        def api(self, _cmd):
            return (
                "+OK uuid,direction,created,created_epoch,name,state,cid_name,cid_num,ip_addr,dest,"
                "presence_id,callstate,callee_name,callee_num,callee_direction\n"
                "1111,inbound,2026-03-06 10:00:00,0,sofia/internal/1001@pbx,CS_EXECUTE,Alice,1001,"
                "10.0.0.11,1002,,ACTIVE,Bob,1002,outbound\n"
                "1 total.\n"
            )

        def close(self):
            return None

    target = SimpleNamespace(type="freeswitch", id="fs-1")

    def _fake_connector(_ctx, _pbx_id):
        return target, _DummyESL()

    monkeypatch.setattr(freeswitch, "_connector", _fake_connector)

    _target, data = freeswitch.channels(
        SimpleNamespace(settings=None), {"pbx_id": "fs-1", "include_raw": True}
    )
    assert data["ok"] is True
    assert data["target"] == {"type": "freeswitch", "id": "fs-1"}
    assert data["transport"]["status"] == "reachable"
    assert data["auth"]["status"] == "authenticated"
    assert data["command"]["status"] == "ok"
    assert data["channels"][0]["channel_id"] == "1111"
    assert "uuid,direction" in data["raw"]["esl"]


def test_freeswitch_channels_empty_valid_distinct_from_parse_failure(monkeypatch) -> None:
    class _DummyESL:
        def api(self, _cmd):
            return "+OK uuid,name,state\n0 total.\n"

        def close(self):
            return None

    target = SimpleNamespace(type="freeswitch", id="fs-1")

    def _fake_connector(_ctx, _pbx_id):
        return target, _DummyESL()

    monkeypatch.setattr(freeswitch, "_connector", _fake_connector)

    _target, data = freeswitch.channels(SimpleNamespace(settings=None), {"pbx_id": "fs-1"})
    assert data["ok"] is True
    assert data["command"]["status"] == "empty_valid"
    assert data["channels"] == []
    assert data["data_quality"]["result_kind"] == "empty_valid"


def test_freeswitch_health_degrades_when_sofia_discovery_unavailable(monkeypatch) -> None:
    class _DummyESL:
        def ping(self):
            return {"ok": True, "latency_ms": 7, "raw": "+OK status"}

        def api(self, cmd: str):
            if cmd == "version":
                return "FreeSWITCH Version 1.10.11-release"
            if cmd == "sofia status":
                return "-ERR command not found"
            raise AssertionError(f"unexpected command: {cmd}")

        def close(self):
            return None

    target = SimpleNamespace(type="freeswitch", id="fs-1")

    def _fake_connector(_ctx, _pbx_id):
        return target, _DummyESL()

    monkeypatch.setattr(freeswitch, "_connector", _fake_connector)

    _target, data = freeswitch.health(SimpleNamespace(settings=None), {"pbx_id": "fs-1"})
    assert data["ok"] is True
    assert data["degraded"] is True
    assert data["freeswitch_version"] == "1.10.11-release"
    assert data["profiles"] == []
    assert any("command_unavailable" in warning for warning in data["warnings"])


def test_freeswitch_capabilities_reports_auth_failure(monkeypatch) -> None:
    class _DummyESL:
        def connect(self):
            return None

        def api(self, _cmd):
            raise ToolError(AUTH_FAILED, "ESL authentication failed")

        def close(self):
            return None

    target = SimpleNamespace(type="freeswitch", id="fs-1", host="10.0.0.10", esl=object())

    def _fake_connector(_ctx, _pbx_id):
        return target, _DummyESL()

    monkeypatch.setattr(freeswitch, "_connector", _fake_connector)
    monkeypatch.setattr(
        freeswitch,
        "_event_monitor",
        lambda _ctx, _pbx_id: SimpleNamespace(
            ensure_started=lambda: None,
            status_snapshot=lambda: {
                "supported": True,
                "state": "unavailable",
                "available": False,
                "degraded": False,
                "healthy": False,
                "buffer_capacity": 128,
                "buffered_events": 0,
                "dropped_events": 0,
                "monitor_started_at": None,
                "last_event_at": None,
                "last_healthy_at": None,
                "last_error": {"code": AUTH_FAILED, "message": "monitor unavailable", "details": {}},
                "session_id": None,
                "subscription_reply": None,
                "freshness": {
                    "monitor_started_at": None,
                    "last_event_at": None,
                    "last_healthy_at": None,
                    "idle_duration_ms": None,
                    "monitor_age_ms": None,
                    "is_stale": True,
                    "staleness_reason": "monitor_unavailable",
                    "stale_after_ms": 60000,
                    "monitor_state": "unavailable",
                },
            },
        ),
    )

    ctx = SimpleNamespace(settings=None, mode=Mode.INSPECT)
    _target, data = freeswitch.capabilities(ctx, {"pbx_id": "fs-1"})
    assert data["ok"] is False
    assert data["capabilities"]["target_reachability"]["available"] is True
    assert data["capabilities"]["auth_usability"]["available"] is False
    assert data["capabilities"]["passive_event_readback"]["supported"] is True
    assert data["capabilities"]["write_actions"]["available"] is False
    assert data["error"]["code"] == AUTH_FAILED


def test_freeswitch_recent_events_empty_buffer_is_valid(monkeypatch) -> None:
    class _DummyMonitor:
        def ensure_started(self):
            return None

        def snapshot(self, **_kwargs):
            return {
                "state": "available",
                "healthy": True,
                "events": [],
                "buffer_capacity": 128,
                "buffered_events": 0,
                "dropped_events": 0,
                "overflowed": False,
                "monitor_started_at": "2026-04-14T00:00:00Z",
                "last_event_at": None,
                "last_healthy_at": "2026-04-14T00:00:00Z",
                "last_error": None,
                "session_id": "sess-1",
                "freshness": {
                    "monitor_started_at": "2026-04-14T00:00:00Z",
                    "last_event_at": None,
                    "last_healthy_at": "2026-04-14T00:00:00Z",
                    "idle_duration_ms": 1000,
                    "monitor_age_ms": 1000,
                    "is_stale": False,
                    "staleness_reason": None,
                    "stale_after_ms": 60000,
                    "monitor_state": "available",
                },
            }

    monkeypatch.setattr(freeswitch, "_event_monitor", lambda _ctx, _pbx_id: _DummyMonitor())
    ctx = SimpleNamespace(
        settings=SimpleNamespace(get_target=lambda _pbx_id: SimpleNamespace(type="freeswitch", id="fs-1")),
        server=SimpleNamespace(),
    )
    _target, data = freeswitch.recent_events(ctx, {"pbx_id": "fs-1"})
    assert data["ok"] is True
    assert data["command"]["status"] == "empty_valid"
    assert data["events"] == []
    assert data["event_buffer"]["is_stale"] is False
    assert data["freshness"]["monitor_state"] == "available"


def test_freeswitch_recent_events_filters_and_overflow(monkeypatch) -> None:
    class _DummyMonitor:
        def ensure_started(self):
            return None

        def snapshot(self, **_kwargs):
            return {
                "state": "degraded",
                "healthy": False,
                "events": [
                    {
                        "observed_at": "2026-04-14T00:00:00Z",
                        "event_name": "CHANNEL_CREATE",
                        "event_family": "channel",
                        "identifiers": {"unique_id": "uuid-1"},
                        "content_type": "text/event-plain",
                        "session_id": "sess-1",
                        "target_id": "fs-1",
                        "raw": {"headers": {"event-name": "CHANNEL_CREATE"}, "body": "x", "body_truncated": False},
                    }
                ],
                "buffer_capacity": 128,
                "buffered_events": 10,
                "dropped_events": 3,
                "overflowed": True,
                "monitor_started_at": "2026-04-14T00:00:00Z",
                "last_event_at": "2026-04-14T00:00:00Z",
                "last_healthy_at": "2026-04-14T00:00:00Z",
                "last_error": {"code": CONNECTION_FAILED, "message": "monitor degraded", "details": {}},
                "session_id": "sess-1",
                "freshness": {
                    "monitor_started_at": "2026-04-14T00:00:00Z",
                    "last_event_at": "2026-04-14T00:00:00Z",
                    "last_healthy_at": "2026-04-14T00:00:00Z",
                    "idle_duration_ms": 61000,
                    "monitor_age_ms": 62000,
                    "is_stale": True,
                    "staleness_reason": "monitor_degraded",
                    "stale_after_ms": 60000,
                    "monitor_state": "degraded",
                },
            }

    monkeypatch.setattr(freeswitch, "_event_monitor", lambda _ctx, _pbx_id: _DummyMonitor())
    ctx = SimpleNamespace(
        settings=SimpleNamespace(get_target=lambda _pbx_id: SimpleNamespace(type="freeswitch", id="fs-1")),
        server=SimpleNamespace(),
    )
    _target, data = freeswitch.recent_events(
        ctx,
        {
            "pbx_id": "fs-1",
            "event_names": ["CHANNEL_CREATE"],
            "event_family": "channel",
            "include_raw": True,
        },
    )
    assert data["ok"] is True
    assert data["degraded"] is True
    assert data["event_buffer"]["dropped_events"] == 3
    assert data["filters"]["event_names"] == ["CHANNEL_CREATE"]
    assert any("overflowed" in warning.lower() for warning in data["warnings"])
    assert data["event_buffer"]["is_stale"] is True
    assert "raw" in data["events"][0]


def test_freeswitch_recent_events_heartbeat_filter_matches_buffer_truth(monkeypatch) -> None:
    class _DummyMonitor:
        def ensure_started(self):
            return None

        def snapshot(self, **_kwargs):
            return {
                "state": "available",
                "healthy": True,
                "events": [
                    {
                        "observed_at": "2026-04-14T00:00:00Z",
                        "event_name": "HEARTBEAT",
                        "event_family": "system",
                        "identifiers": {"core_uuid": "core-1"},
                        "content_type": "text/event-plain",
                        "session_id": "sess-1",
                        "target_id": "fs-1",
                    }
                ],
                "buffer_capacity": 128,
                "buffered_events": 1,
                "dropped_events": 0,
                "overflowed": False,
                "monitor_started_at": "2026-04-14T00:00:00Z",
                "last_event_at": "2026-04-14T00:00:00Z",
                "last_healthy_at": "2026-04-14T00:00:00Z",
                "last_error": None,
                "session_id": "sess-1",
                "freshness": {
                    "monitor_started_at": "2026-04-14T00:00:00Z",
                    "last_event_at": "2026-04-14T00:00:00Z",
                    "last_healthy_at": "2026-04-14T00:00:00Z",
                    "idle_duration_ms": 1,
                    "monitor_age_ms": 1,
                    "is_stale": False,
                    "staleness_reason": None,
                    "stale_after_ms": 60000,
                    "monitor_state": "available",
                },
            }

    monkeypatch.setattr(freeswitch, "_event_monitor", lambda _ctx, _pbx_id: _DummyMonitor())
    ctx = SimpleNamespace(
        settings=SimpleNamespace(get_target=lambda _pbx_id: SimpleNamespace(type="freeswitch", id="fs-1")),
        server=SimpleNamespace(),
    )
    _target, data = freeswitch.recent_events(
        ctx,
        {"pbx_id": "fs-1", "event_names": ["HEARTBEAT"]},
    )
    assert data["events"][0]["event_name"] == "HEARTBEAT"
    assert data["filters"]["event_names"] == ["HEARTBEAT"]


def test_freeswitch_capabilities_reports_event_readback_available(monkeypatch) -> None:
    class _DummyESL:
        def connect(self):
            return None

        def api(self, _cmd):
            return "FreeSWITCH Version 1.10.11-release"

        def close(self):
            return None

    class _DummyMonitor:
        def ensure_started(self):
            return None

        def status_snapshot(self):
            return {
                "supported": True,
                "state": "available",
                "available": True,
                "degraded": False,
                "healthy": True,
                "buffer_capacity": 128,
                "buffered_events": 2,
                "dropped_events": 0,
                "monitor_started_at": "2026-04-14T00:00:00Z",
                "last_event_at": "2026-04-14T00:00:00Z",
                "last_healthy_at": "2026-04-14T00:00:00Z",
                "last_error": None,
                "session_id": "sess-1",
                "subscription_reply": "+OK event listener enabled plain",
                "freshness": {
                    "monitor_started_at": "2026-04-14T00:00:00Z",
                    "last_event_at": "2026-04-14T00:00:00Z",
                    "last_healthy_at": "2026-04-14T00:00:00Z",
                    "idle_duration_ms": 10,
                    "monitor_age_ms": 10,
                    "is_stale": False,
                    "staleness_reason": None,
                    "stale_after_ms": 60000,
                    "monitor_state": "available",
                },
            }

    target = SimpleNamespace(type="freeswitch", id="fs-1", host="10.0.0.10", esl=object())

    monkeypatch.setattr(freeswitch, "_connector", lambda _ctx, _pbx_id: (target, _DummyESL()))
    monkeypatch.setattr(freeswitch, "_event_monitor", lambda _ctx, _pbx_id: _DummyMonitor())

    ctx = SimpleNamespace(settings=None, mode=Mode.INSPECT)
    _target, data = freeswitch.capabilities(ctx, {"pbx_id": "fs-1"})
    assert data["ok"] is True
    assert data["capabilities"]["passive_event_readback"]["available"] is True
    assert data["capabilities"]["inbound_esl_session_discovery"]["supported"] is True
    assert data["capabilities"]["inbound_esl_session_drop"]["supported"] is False
    assert data["inbound_esl_session_drop_policy"]["support_state"] == "unsupported_current_posture"
    assert data["event_readback"]["buffered_events"] == 2
    assert data["event_readback"]["is_stale"] is False


def test_freeswitch_route_check_static_match_is_route_found(monkeypatch) -> None:
    class _DummyESL:
        def api(self, cmd: str):
            if cmd == "xml_locate dialplan default":
                return (
                    '<document><section name="dialplan"><context name="default">'
                    '<extension name="local-1001">'
                    '<condition field="destination_number" expression="^1001$"/>'
                    "</extension></context></section></document>"
                )
            if cmd == "sofia status":
                return "Profile: internal RUNNING\n"
            raise AssertionError(f"unexpected command: {cmd}")

        def close(self):
            return None

    target = SimpleNamespace(type="freeswitch", id="fs-1")
    monkeypatch.setattr(freeswitch, "_connector", lambda _ctx, _pbx_id: (target, _DummyESL()))

    _target, data = freeswitch.route_check(
        SimpleNamespace(settings=None),
        {"pbx_id": "fs-1", "destination": "1001", "context": "default"},
    )
    assert data["route_status"] == "route_found"
    assert data["confidence"] == "high"
    assert data["matched_context"] == "default"
    assert data["matched_extension"] == "local-1001"
    assert data["blocking_findings"] == []


def test_freeswitch_route_check_no_matching_extension_is_no_route(monkeypatch) -> None:
    class _DummyESL:
        def api(self, cmd: str):
            if cmd == "xml_locate dialplan default":
                return (
                    '<document><section name="dialplan"><context name="default">'
                    '<extension name="local-1002">'
                    '<condition field="destination_number" expression="^1002$"/>'
                    "</extension></context></section></document>"
                )
            if cmd == "sofia status":
                return "Profile: internal RUNNING\n"
            raise AssertionError(f"unexpected command: {cmd}")

        def close(self):
            return None

    target = SimpleNamespace(type="freeswitch", id="fs-1")
    monkeypatch.setattr(freeswitch, "_connector", lambda _ctx, _pbx_id: (target, _DummyESL()))

    _target, data = freeswitch.route_check(
        SimpleNamespace(settings=None),
        {"pbx_id": "fs-1", "destination": "1001", "context": "default"},
    )
    assert data["route_status"] == "no_route"
    assert data["confidence"] == "high"
    assert data["blocking_findings"][0]["code"] == "NO_MATCHING_EXTENSION"


def test_freeswitch_route_check_degrades_when_dialplan_readback_fails(monkeypatch) -> None:
    class _DummyESL:
        def api(self, cmd: str):
            if cmd == "xml_locate dialplan default":
                return "-ERR command not found"
            if cmd == "sofia status":
                return "Profile: internal RUNNING\n"
            raise AssertionError(f"unexpected command: {cmd}")

        def close(self):
            return None

    target = SimpleNamespace(type="freeswitch", id="fs-1")
    monkeypatch.setattr(freeswitch, "_connector", lambda _ctx, _pbx_id: (target, _DummyESL()))

    _target, data = freeswitch.route_check(
        SimpleNamespace(settings=None),
        {"pbx_id": "fs-1", "destination": "1001", "context": "default"},
    )
    assert data["route_status"] == "degraded"
    assert data["confidence"] == "low"
    assert any(item["code"] == "ROUTE_EVIDENCE_INCOMPLETE" for item in data["blocking_findings"])


def test_freeswitch_route_check_gateway_blocker_is_degraded(monkeypatch) -> None:
    class _DummyESL:
        def api(self, cmd: str):
            if cmd == "xml_locate dialplan public":
                return (
                    '<document><section name="dialplan"><context name="public">'
                    '<extension name="outbound">'
                    '<condition field="destination_number" expression="^18005550199$"/>'
                    "</extension></context></section></document>"
                )
            if cmd == "sofia status":
                return "Profile: external RUNNING\nGateway: carrier DOWN\n"
            if cmd == "sofia status gateway carrier":
                return "Gateway: carrier DOWN\n"
            raise AssertionError(f"unexpected command: {cmd}")

        def close(self):
            return None

    target = SimpleNamespace(type="freeswitch", id="fs-1")
    monkeypatch.setattr(freeswitch, "_connector", lambda _ctx, _pbx_id: (target, _DummyESL()))

    _target, data = freeswitch.route_check(
        SimpleNamespace(settings=None),
        {
            "pbx_id": "fs-1",
            "destination": "18005550199",
            "context": "public",
            "gateway": "carrier",
        },
    )
    assert data["route_status"] == "degraded"
    assert any(item["code"] == "GATEWAY_UNAVAILABLE" for item in data["blocking_findings"])


def test_freeswitch_route_check_include_evidence_is_bounded(monkeypatch) -> None:
    large_padding = "x" * 6000

    class _DummyESL:
        def api(self, cmd: str):
            if cmd == "xml_locate dialplan default":
                return (
                    '<document><section name="dialplan"><context name="default">'
                    '<extension name="local-1001">'
                    '<condition field="destination_number" expression="^1001$"/>'
                    f"</extension>{large_padding}</context></section></document>"
                )
            if cmd == "sofia status":
                return "Profile: internal RUNNING\n"
            raise AssertionError(f"unexpected command: {cmd}")

        def close(self):
            return None

    target = SimpleNamespace(type="freeswitch", id="fs-1")
    monkeypatch.setattr(freeswitch, "_connector", lambda _ctx, _pbx_id: (target, _DummyESL()))

    _target, data = freeswitch.route_check(
        SimpleNamespace(settings=None),
        {
            "pbx_id": "fs-1",
            "destination": "1001",
            "context": "default",
            "include_evidence": True,
        },
    )
    assert data["route_status"] == "route_found"
    assert data["raw_evidence"]["dialplan"]["truncated"] is True
    assert len(data["raw_evidence"]["dialplan"]["text"]) == 4096
