from __future__ import annotations

from types import SimpleNamespace

from telecom_mcp.authz import Mode
from telecom_mcp.tools import freeswitch


def _ctx(
    *,
    environment: str = "lab",
    safety_tier: str = "lab_safe",
    allow_active_validation: bool = True,
) -> SimpleNamespace:
    target = SimpleNamespace(
        id="fs-1",
        type="freeswitch",
        host="127.0.0.1",
        esl=object(),
        environment=environment,
        safety_tier=safety_tier,
        allow_active_validation=allow_active_validation,
    )
    return SimpleNamespace(
        settings=SimpleNamespace(get_target=lambda _pbx_id: target),
        mode=Mode.EXECUTE_FULL,
        server=SimpleNamespace(),
    )


def test_inbound_esl_sessions_parses_targetable_rows(monkeypatch) -> None:
    raw = (
        '[{"listen-id":101,"profile":"mod_event_socket","remote_ip":"10.0.0.50","remote_port":60544,'
        '"listen_ip":"127.0.0.1","listen_port":8021,"created":"2026-04-15T03:00:00Z","type":"inbound esl"},'
        '{"listen-id":102,"profile":"mod_sofia","remote_ip":"10.0.0.60","remote_port":5060}]'
    )

    class _DummyESL:
        def api(self, command: str) -> str:
            assert command == "show management as json"
            return raw

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        freeswitch,
        "_connector",
        lambda _ctx, _pbx_id: (SimpleNamespace(type="freeswitch", id="fs-1"), _DummyESL()),
    )

    _target, data = freeswitch.inbound_esl_sessions(
        SimpleNamespace(settings=None),
        {"pbx_id": "fs-1"},
    )
    assert data["tool"] == "freeswitch.inbound_esl_sessions"
    assert data["counts"]["total"] == 1
    assert data["items"][0]["session_id"] == "101"
    assert data["items"][0]["targetable"] is True
    assert data["items"][0]["is_inbound_esl"] is True


def test_inbound_esl_sessions_marks_missing_listener_id_untargetable(monkeypatch) -> None:
    raw = (
        '[{"profile":"mod_event_socket","remote_ip":"10.0.0.50","remote_port":60544,'
        '"created":"2026-04-15T03:00:00Z","type":"inbound esl"}]'
    )

    class _DummyESL:
        def api(self, _command: str) -> str:
            return raw

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        freeswitch,
        "_connector",
        lambda _ctx, _pbx_id: (SimpleNamespace(type="freeswitch", id="fs-1"), _DummyESL()),
    )

    _target, data = freeswitch.inbound_esl_sessions(
        SimpleNamespace(settings=None),
        {"pbx_id": "fs-1"},
    )
    assert data["counts"]["untargetable"] == 1
    assert data["items"][0]["targetable"] is False
    assert data["degraded"] is True


def test_drop_inbound_esl_session_fails_closed_on_ambiguous_selector(monkeypatch) -> None:
    raw = (
        '[{"listen-id":101,"profile":"mod_event_socket","remote_ip":"10.0.0.50","remote_port":60544,"type":"inbound esl"},'
        '{"listen-id":101,"profile":"mod_event_socket","remote_ip":"10.0.0.51","remote_port":60545,"type":"inbound esl"}]'
    )

    class _DummyESL:
        def api(self, _command: str) -> str:
            return raw

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        freeswitch,
        "_connector",
        lambda _runtime_ctx, _pbx_id: (_ctx().settings.get_target("fs-1"), _DummyESL()),
    )

    _target, data = freeswitch.drop_inbound_esl_session(
        _ctx(),
        {
            "pbx_id": "fs-1",
            "session_id": "101",
            "confirm_session_id": "101",
            "reason": "reconnect validation",
            "change_ticket": "CHG-7001",
        },
    )
    assert data["execution"]["executed"] is False
    assert data["blocker"]["code"] == "AMBIGUOUS_SELECTOR"


def test_drop_inbound_esl_session_fails_closed_on_zero_match(monkeypatch) -> None:
    raw = '[{"listen-id":101,"profile":"mod_event_socket","remote_ip":"10.0.0.50","remote_port":60544,"type":"inbound esl"}]'

    class _DummyESL:
        def api(self, _command: str) -> str:
            return raw

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        freeswitch,
        "_connector",
        lambda _runtime_ctx, _pbx_id: (_ctx().settings.get_target("fs-1"), _DummyESL()),
    )

    _target, data = freeswitch.drop_inbound_esl_session(
        _ctx(),
        {
            "pbx_id": "fs-1",
            "session_id": "999",
            "confirm_session_id": "999",
            "reason": "reconnect validation",
            "change_ticket": "CHG-7002",
        },
    )
    assert data["execution"]["executed"] is False
    assert data["blocker"]["code"] == "NO_MATCH"


def test_drop_inbound_esl_session_reports_unsupported_strategy_with_unique_match(
    monkeypatch,
) -> None:
    raw = '[{"listen-id":101,"profile":"mod_event_socket","remote_ip":"10.0.0.50","remote_port":60544,"type":"inbound esl"}]'

    class _DummyESL:
        def api(self, _command: str) -> str:
            return raw

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        freeswitch,
        "_connector",
        lambda _runtime_ctx, _pbx_id: (_ctx().settings.get_target("fs-1"), _DummyESL()),
    )

    _target, data = freeswitch.drop_inbound_esl_session(
        _ctx(),
        {
            "pbx_id": "fs-1",
            "session_id": "101",
            "confirm_session_id": "101",
            "reason": "reconnect validation",
            "change_ticket": "CHG-7003",
        },
    )
    assert data["execution"]["executed"] is False
    assert data["blocker"]["code"] == "UNSUPPORTED_DISCONNECT_STRATEGY"
    assert data["execution"]["result"] == "unsupported"
    assert data["support_state"] == "unsupported_current_posture"
