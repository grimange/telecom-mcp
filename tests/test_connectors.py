from __future__ import annotations

import pytest

from telecom_mcp.connectors.asterisk_ami import AsteriskAMIConnector
from telecom_mcp.connectors.asterisk_ari import AsteriskARIConnector
from telecom_mcp.connectors.freeswitch_esl import FreeSWITCHESLConnector
from telecom_mcp.config import AMIConfig, ARIConfig, ESLConfig
from telecom_mcp.errors import AUTH_FAILED, CONNECTION_FAILED, TIMEOUT, ToolError


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
        def sendall(self, _data):
            raise OSError("socket down")

        def recv(self, _size):
            return b""

        def close(self):
            return None

    connector = FreeSWITCHESLConnector(
        ESLConfig(host="127.0.0.1", port=8021, password_env="P"), timeout_s=0.01
    )
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
