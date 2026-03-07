from __future__ import annotations

import urllib.error
import pytest

from telecom_mcp.connectors.asterisk_ami import AsteriskAMIConnector
from telecom_mcp.connectors.asterisk_ari import AsteriskARIConnector
from telecom_mcp.connectors.freeswitch_esl import FreeSWITCHESLConnector
from telecom_mcp.config import AMIConfig, ARIConfig, ESLConfig
from telecom_mcp.errors import AUTH_FAILED, CONNECTION_FAILED, TIMEOUT, UPSTREAM_ERROR, ToolError


def test_ami_connection_error_maps() -> None:
    connector = AsteriskAMIConnector(
        AMIConfig(host="203.0.113.1", port=9, username_env="U", password_env="P"),
        timeout_s=0.01,
    )
    with pytest.raises(ToolError) as exc:
        connector.connect()
    assert exc.value.code in {AUTH_FAILED, CONNECTION_FAILED, TIMEOUT}


def test_ari_missing_env_auth() -> None:
    connector = AsteriskARIConnector(
        ARIConfig(
            url="http://127.0.0.1:1",
            username_env="NO_USER",
            password_env="NO_PASS",
            app="telecom_mcp",
        ),
        timeout_s=0.01,
    )
    with pytest.raises(ToolError):
        connector.health()
    connector.close()


def test_esl_connection_error_maps() -> None:
    connector = FreeSWITCHESLConnector(
        ESLConfig(host="203.0.113.1", port=9, password_env="P"), timeout_s=0.01
    )
    with pytest.raises(ToolError) as exc:
        connector.connect()
    assert exc.value.code in {CONNECTION_FAILED, TIMEOUT}


def test_esl_api_io_error_maps_to_connection_failed(monkeypatch) -> None:
    class _FailingSocket:
        def __init__(self) -> None:
            self._responses = [b"Content-Type: auth/request\r\nContent-Length: 0\r\n\r\n"]

        def settimeout(self, _timeout):
            return None

        def sendall(self, _data):
            raise OSError("socket down")

        def recv(self, _size):
            if not self._responses:
                return b""
            return self._responses.pop(0)

        def close(self):
            return None

    connector = FreeSWITCHESLConnector(
        ESLConfig(host="127.0.0.1", port=8021, password_env="P"), timeout_s=0.01
    )
    connector.max_retries = 0
    connector._sock = _FailingSocket()  # type: ignore[assignment]
    monkeypatch.setattr(connector, "_password", lambda: "secret")

    with pytest.raises(ToolError) as exc:
        connector.api("status")
    assert exc.value.code == CONNECTION_FAILED


def test_ami_send_action_performs_login_handshake(monkeypatch) -> None:
    monkeypatch.setenv("AST_USER", "user1")
    monkeypatch.setenv("AST_PASS", "pass1")

    class _FakeSocket:
        def __init__(self) -> None:
            self.sent: list[str] = []
            self._responses = [
                b"Response: Success\r\nMessage: Authentication accepted\r\n\r\n",
                b"Response: Success\r\nMessage: Pong\r\n\r\n",
            ]

        def settimeout(self, _timeout):
            return None

        def sendall(self, data: bytes):
            self.sent.append(data.decode("utf-8", errors="replace"))

        def recv(self, _size):
            return self._responses.pop(0)

        def close(self):
            return None

    fake_sock = _FakeSocket()
    monkeypatch.setattr("socket.create_connection", lambda *_args, **_kwargs: fake_sock)

    connector = AsteriskAMIConnector(
        AMIConfig(
            host="127.0.0.1",
            port=5038,
            username_env="AST_USER",
            password_env="AST_PASS",
        ),
        timeout_s=0.01,
    )
    response = connector.send_action({"Action": "Ping"})
    connector.close()

    assert response["Response"] == "Success"
    assert "Action: Login" in fake_sock.sent[0]
    assert "Username: user1" in fake_sock.sent[0]
    assert "Secret: pass1" in fake_sock.sent[0]
    assert "Action: Ping" in fake_sock.sent[1]


def test_ami_send_action_reads_fragmented_event_list(monkeypatch) -> None:
    monkeypatch.setenv("AST_USER", "user1")
    monkeypatch.setenv("AST_PASS", "pass1")

    class _FakeSocket:
        def __init__(self) -> None:
            self._responses = [
                b"Response: Success\r\nMessage: Authentication accepted\r\n\r\n",
                b"Response: Success\r\nEventList: start\r\nMessage: list will follow\r\n\r\n"
                b"Event: EndpointList\r\nObjectName: 1001\r\nStatus: Available\r\n\r\n",
                b"Event: EndpointList\r\nObjectName: 1002\r\nStatus: Unavailable\r\n\r\n"
                b"Event: EndpointListComplete\r\nEventList: Complete\r\nListItems: 2\r\n\r\n",
            ]

        def settimeout(self, _timeout):
            return None

        def sendall(self, _data: bytes):
            return None

        def recv(self, _size: int) -> bytes:
            if not self._responses:
                return b""
            return self._responses.pop(0)

        def close(self):
            return None

    fake_sock = _FakeSocket()
    monkeypatch.setattr("socket.create_connection", lambda *_args, **_kwargs: fake_sock)

    connector = AsteriskAMIConnector(
        AMIConfig(
            host="127.0.0.1",
            port=5038,
            username_env="AST_USER",
            password_env="AST_PASS",
        ),
        timeout_s=0.05,
    )
    response = connector.send_action({"Action": "PJSIPShowEndpoints"})
    connector.close()

    assert "ObjectName: 1001" in response["raw"]
    assert "ObjectName: 1002" in response["raw"]
    assert response["EventList"] == "Complete"


def test_esl_api_reads_fragmented_content_length_response(monkeypatch) -> None:
    monkeypatch.setenv("FS_PASS", "secret")

    class _FakeSocket:
        def __init__(self) -> None:
            self._responses = [
                b"Content-Type: auth/request\r\nContent-Length: 0\r\n\r\n",
                b"Content-Type: command/reply\r\nReply-Text: +OK accepted\r\n\r\n",
                b"Content-Type: api/response\r\nContent-Length: 12\r\n\r\n+OK part",
                b"ial\n",
            ]

        def settimeout(self, _timeout):
            return None

        def sendall(self, _data: bytes):
            return None

        def recv(self, _size: int) -> bytes:
            if not self._responses:
                return b""
            return self._responses.pop(0)

        def close(self):
            return None

    connector = FreeSWITCHESLConnector(
        ESLConfig(host="127.0.0.1", port=8021, password_env="FS_PASS"), timeout_s=0.05
    )
    connector._sock = _FakeSocket()  # type: ignore[assignment]
    payload = connector.api("status")
    connector.close()
    assert payload.endswith("+OK partial\n")


def test_ami_connect_retries_once_before_success(monkeypatch) -> None:
    monkeypatch.setenv("AST_USER", "user1")
    monkeypatch.setenv("AST_PASS", "pass1")
    attempts = {"count": 0}

    class _FakeSocket:
        def settimeout(self, _timeout):
            return None

        def close(self):
            return None

    def _fake_create_connection(*_args, **_kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise OSError("temporary failure")
        return _FakeSocket()

    monkeypatch.setattr("socket.create_connection", _fake_create_connection)

    connector = AsteriskAMIConnector(
        AMIConfig(host="127.0.0.1", port=5038, username_env="AST_USER", password_env="AST_PASS"),
        timeout_s=0.01,
    )
    connector.connect()
    assert attempts["count"] == 2


def test_ari_get_retries_once_on_transient_url_error(monkeypatch) -> None:
    monkeypatch.setenv("AST_USER", "user1")
    monkeypatch.setenv("AST_PASS", "pass1")
    attempts = {"count": 0}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"ok": true}'

    def _fake_urlopen(*_args, **_kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise urllib.error.URLError("temporary down")
        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    connector = AsteriskARIConnector(
        ARIConfig(url="http://127.0.0.1:8088", username_env="AST_USER", password_env="AST_PASS", app="telecom_mcp"),
        timeout_s=0.01,
    )
    payload = connector.get("asterisk/info")
    assert payload == {"ok": True}
    assert attempts["count"] == 2


def test_esl_api_retries_once_on_transient_send_error(monkeypatch) -> None:
    monkeypatch.setenv("FS_PASS", "secret")
    attempts = {"count": 0}

    class _FlakySocket:
        def __init__(self, *, fail_first_send: bool) -> None:
            self._responses = [
                b"Content-Type: auth/request\r\nContent-Length: 0\r\n\r\n",
                b"Content-Type: command/reply\r\nReply-Text: +OK accepted\r\n\r\n",
                b"Content-Type: api/response\r\nContent-Length: 8\r\n\r\n+OK done",
            ]
            self._fail_first_send = fail_first_send

        def settimeout(self, _timeout):
            return None

        def sendall(self, _data):
            attempts["count"] += 1
            if self._fail_first_send:
                self._fail_first_send = False
                raise OSError("temporary send failure")

        def recv(self, _size):
            if not self._responses:
                return b""
            return self._responses.pop(0)

        def close(self):
            return None

    sockets = [_FlakySocket(fail_first_send=True), _FlakySocket(fail_first_send=False)]

    def _fake_create_connection(*_a, **_k):
        return sockets.pop(0)

    monkeypatch.setattr("socket.create_connection", _fake_create_connection)
    connector = FreeSWITCHESLConnector(
        ESLConfig(host="127.0.0.1", port=8021, password_env="FS_PASS"), timeout_s=0.05
    )
    payload = connector.api("status")
    assert payload == "+OK done"
    assert attempts["count"] >= 2


def test_esl_api_ignores_interleaved_event_frame(monkeypatch) -> None:
    monkeypatch.setenv("FS_PASS", "secret")

    class _FakeSocket:
        def __init__(self) -> None:
            self._responses = [
                b"Content-Type: auth/request\r\nContent-Length: 0\r\n\r\n",
                b"Content-Type: command/reply\r\nReply-Text: +OK accepted\r\n\r\n",
                (
                    b"Content-Type: text/event-plain\r\nContent-Length: 22\r\n\r\n"
                    b"Event-Name: HEARTBEAT\n\n"
                    b"Content-Type: api/response\r\nContent-Length: 8\r\n\r\n+OK done"
                ),
            ]

        def settimeout(self, _timeout):
            return None

        def sendall(self, _data: bytes):
            return None

        def recv(self, _size: int) -> bytes:
            if not self._responses:
                return b""
            return self._responses.pop(0)

        def close(self):
            return None

    connector = FreeSWITCHESLConnector(
        ESLConfig(host="127.0.0.1", port=8021, password_env="FS_PASS"), timeout_s=0.05
    )
    connector._sock = _FakeSocket()  # type: ignore[assignment]
    payload = connector.api("status")
    assert payload == "+OK done"


def test_esl_api_rejects_unexpected_non_event_frame_type(monkeypatch) -> None:
    monkeypatch.setenv("FS_PASS", "secret")

    class _FakeSocket:
        def __init__(self) -> None:
            self._responses = [
                b"Content-Type: auth/request\r\nContent-Length: 0\r\n\r\n",
                b"Content-Type: command/reply\r\nReply-Text: +OK accepted\r\n\r\n",
                b"Content-Type: command/reply\r\nReply-Text: +OK accepted\r\n\r\n",
            ]

        def settimeout(self, _timeout):
            return None

        def sendall(self, _data: bytes):
            return None

        def recv(self, _size: int) -> bytes:
            if not self._responses:
                return b""
            return self._responses.pop(0)

        def close(self):
            return None

    connector = FreeSWITCHESLConnector(
        ESLConfig(host="127.0.0.1", port=8021, password_env="FS_PASS"), timeout_s=0.05
    )
    connector._sock = _FakeSocket()  # type: ignore[assignment]

    with pytest.raises(ToolError) as exc:
        connector.api("status")
    assert exc.value.code == UPSTREAM_ERROR


def test_esl_api_rejects_malformed_content_length(monkeypatch) -> None:
    monkeypatch.setenv("FS_PASS", "secret")

    class _FakeSocket:
        def __init__(self) -> None:
            self._responses = [
                b"Content-Type: auth/request\r\nContent-Length: 0\r\n\r\n",
                b"Content-Type: command/reply\r\nReply-Text: +OK accepted\r\n\r\n",
                b"Content-Type: api/response\r\nContent-Length: nope\r\n\r\n+OK ignored",
            ]

        def settimeout(self, _timeout):
            return None

        def sendall(self, _data: bytes):
            return None

        def recv(self, _size: int) -> bytes:
            if not self._responses:
                return b""
            return self._responses.pop(0)

        def close(self):
            return None

    connector = FreeSWITCHESLConnector(
        ESLConfig(host="127.0.0.1", port=8021, password_env="FS_PASS"), timeout_s=0.05
    )
    connector._sock = _FakeSocket()  # type: ignore[assignment]

    with pytest.raises(ToolError) as exc:
        connector.api("status")
    assert exc.value.code == UPSTREAM_ERROR
