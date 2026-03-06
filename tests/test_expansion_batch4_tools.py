from __future__ import annotations

from types import SimpleNamespace

import pytest

from telecom_mcp.errors import NOT_ALLOWED, ToolError
from telecom_mcp.tools import asterisk, freeswitch, telecom


@pytest.fixture(autouse=True)
def _reset_probe_state():
    telecom._PROBE_RATE_HISTORY.clear()
    telecom._PROBE_REGISTRY.clear()
    yield


class _Ctx:
    def __init__(self, target_type: str = "asterisk") -> None:
        self._target = SimpleNamespace(
            id="pbx-1" if target_type == "asterisk" else "fs-1",
            type=target_type,
            host="127.0.0.1",
            ami=object() if target_type == "asterisk" else None,
            ari=object() if target_type == "asterisk" else None,
            esl=object() if target_type == "freeswitch" else None,
            logs=None,
        )
        self.settings = SimpleNamespace(get_target=lambda _pbx_id: self._target)

    def call_tool_internal(self, tool_name: str, args: dict[str, object]):
        if tool_name in {"asterisk.health", "freeswitch.health"}:
            return {"ok": True, "data": {"ok": True}}
        if tool_name in {"asterisk.pjsip_show_endpoints", "freeswitch.registrations"}:
            return {"ok": True, "data": {"items": [{"id": "x"}]}}
        if tool_name in {"asterisk.active_channels", "freeswitch.channels"}:
            return {"ok": True, "data": {"channels": []}}
        if tool_name == "telecom.summary":
            return {
                "ok": True,
                "data": {
                    "channels_active": 2,
                    "registrations": {"endpoints_registered": 5, "endpoints_unreachable": 0},
                },
            }
        if tool_name in {"asterisk.version", "freeswitch.version"}:
            return {"ok": True, "data": {"version": "1.0.0"}}
        if tool_name == "telecom.calls":
            return {
                "ok": True,
                "data": {
                    "items": [
                        {"call_id": "normal-1", "caller": "1001", "callee": "1002"},
                        {"call_id": "probe-2", "caller": "probe", "callee": "2002"},
                    ]
                },
            }
        if tool_name in {"asterisk.originate_probe", "freeswitch.originate_probe"}:
            return {"ok": True, "data": {"probe_id": "probe-123", "initiated": True}}
        raise AssertionError(f"unexpected tool call: {tool_name}")


def test_run_smoke_test_returns_summary() -> None:
    _target, data = telecom.run_smoke_test(_Ctx("asterisk"), {"pbx_id": "pbx-1"})
    assert data["tool"] == "telecom.run_smoke_test"
    assert data["counts"]["total"] == 3


def test_assert_state_min_registered_passes() -> None:
    _target, data = telecom.assert_state(
        _Ctx("asterisk"),
        {"pbx_id": "pbx-1", "assertion": "min_registered", "params": {"value": 3}},
    )
    assert data["passed"] is True


def test_run_registration_probe_requires_explicit_enable(monkeypatch) -> None:
    monkeypatch.delenv("TELECOM_MCP_ENABLE_ACTIVE_PROBES", raising=False)
    with pytest.raises(ToolError) as exc:
        telecom.run_registration_probe(
            _Ctx("asterisk"),
            {"pbx_id": "pbx-1", "destination": "1001"},
        )
    assert exc.value.code == NOT_ALLOWED


def test_run_registration_probe_delegates_when_enabled(monkeypatch) -> None:
    monkeypatch.setenv("TELECOM_MCP_ENABLE_ACTIVE_PROBES", "1")
    _target, data = telecom.run_registration_probe(
        _Ctx("asterisk"),
        {"pbx_id": "pbx-1", "destination": "1001", "timeout_s": 12},
    )
    assert data["tool"] == "telecom.run_registration_probe"
    assert data["items"][0]["probe_id"] == "probe-123"


def test_run_registration_probe_rejects_bad_destination(monkeypatch) -> None:
    monkeypatch.setenv("TELECOM_MCP_ENABLE_ACTIVE_PROBES", "1")
    with pytest.raises(ToolError) as exc:
        telecom.run_registration_probe(
            _Ctx("asterisk"),
            {"pbx_id": "pbx-1", "destination": "bad destination with spaces"},
        )
    assert exc.value.code == "VALIDATION_ERROR"


def test_run_registration_probe_rate_limit(monkeypatch) -> None:
    monkeypatch.setenv("TELECOM_MCP_ENABLE_ACTIVE_PROBES", "1")
    monkeypatch.setenv("TELECOM_MCP_PROBE_MAX_PER_MINUTE", "1")
    _ = telecom.run_registration_probe(
        _Ctx("asterisk"),
        {"pbx_id": "pbx-1", "destination": "1001", "timeout_s": 12},
    )
    with pytest.raises(ToolError) as exc:
        telecom.run_registration_probe(
            _Ctx("asterisk"),
            {"pbx_id": "pbx-1", "destination": "1001", "timeout_s": 12},
        )
    assert exc.value.code == NOT_ALLOWED


def test_verify_cleanup_detects_leftovers() -> None:
    _target, data = telecom.verify_cleanup(_Ctx("asterisk"), {"pbx_id": "pbx-1"})
    assert data["clean"] is False
    assert data["counts"]["probe_leftovers"] == 1


def test_asterisk_originate_probe_guards_and_executes(monkeypatch) -> None:
    class _DummyAmi:
        def send_action(self, action):
            assert action["Action"] == "Originate"
            return {"Response": "Success", "Message": "Originate successfully queued"}

        def close(self):
            return None

    monkeypatch.setattr(
        asterisk,
        "_connectors",
        lambda _ctx, _pbx_id: (SimpleNamespace(type="asterisk", id="pbx-1"), _DummyAmi(), None),
    )
    monkeypatch.setenv("TELECOM_MCP_ENABLE_ACTIVE_PROBES", "1")
    _target, data = asterisk.originate_probe(
        SimpleNamespace(settings=None),
        {"pbx_id": "pbx-1", "destination": "1001", "timeout_s": 10},
    )
    assert data["initiated"] is True


def test_freeswitch_originate_probe_guards_and_executes(monkeypatch) -> None:
    class _DummyEsl:
        def api(self, cmd):
            assert cmd.startswith("originate ")
            return "+OK 4d9d9a48-xxxx"

        def close(self):
            return None

    monkeypatch.setattr(
        freeswitch,
        "_connector",
        lambda _ctx, _pbx_id: (SimpleNamespace(type="freeswitch", id="fs-1"), _DummyEsl()),
    )
    monkeypatch.setenv("TELECOM_MCP_ENABLE_ACTIVE_PROBES", "1")
    _target, data = freeswitch.originate_probe(
        SimpleNamespace(settings=None),
        {"pbx_id": "fs-1", "destination": "1002", "timeout_s": 10},
    )
    assert data["initiated"] is True
