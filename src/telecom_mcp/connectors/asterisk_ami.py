"""Minimal AMI connector with bounded socket operations."""

from __future__ import annotations

import socket
import time
from typing import Any

from ..config import AMIConfig
from ..errors import AUTH_FAILED, CONNECTION_FAILED, TIMEOUT, UPSTREAM_ERROR, ToolError


class AsteriskAMIConnector:
    def __init__(self, config: AMIConfig, timeout_s: float = 4.0) -> None:
        self.config = config
        self.timeout_s = timeout_s
        self._sock: socket.socket | None = None
        self._authenticated = False

    def connect(self) -> None:
        _ = self._credentials()
        try:
            self._sock = socket.create_connection(
                (self.config.host, self.config.port), timeout=self.timeout_s
            )
            self._sock.settimeout(self.timeout_s)
        except TimeoutError as exc:
            raise ToolError(TIMEOUT, "AMI connection timed out") from exc
        except OSError as exc:
            raise ToolError(
                CONNECTION_FAILED, "AMI connection failed", {"reason": str(exc)}
            ) from exc

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None
                self._authenticated = False

    def _ensure_socket(self) -> socket.socket:
        if self._sock is None:
            self.connect()
        assert self._sock is not None
        return self._sock

    def ping(self) -> dict[str, Any]:
        started = time.monotonic()
        response = self.send_action({"Action": "Ping"})
        latency_ms = int((time.monotonic() - started) * 1000)
        return {"ok": True, "latency_ms": latency_ms, "response": response}

    def _credentials(self) -> tuple[str, str]:
        import os

        user = os.getenv(self.config.username_env)
        password = os.getenv(self.config.password_env)
        if not user or not password:
            raise ToolError(
                AUTH_FAILED,
                "AMI credentials missing from environment",
                {
                    "username_env": self.config.username_env,
                    "password_env": self.config.password_env,
                },
            )
        return user, password

    def _send_raw_action(self, sock: socket.socket, action: dict[str, Any]) -> dict[str, Any]:
        lines = [f"{k}: {v}" for k, v in action.items()]
        payload = "\r\n".join(lines) + "\r\n\r\n"
        try:
            sock.sendall(payload.encode("utf-8"))
            data = sock.recv(65535)
            return _parse_ami_response(data.decode("utf-8", errors="replace"))
        except TimeoutError as exc:
            self.close()
            raise ToolError(
                TIMEOUT, "AMI action timed out", {"action": action.get("Action")}
            ) from exc
        except BrokenPipeError as exc:
            self.close()
            raise ToolError(CONNECTION_FAILED, "AMI connection dropped") from exc
        except OSError as exc:
            self.close()
            raise ToolError(
                UPSTREAM_ERROR, "AMI I/O error", {"reason": str(exc)}
            ) from exc

    def _ensure_logged_in(self, sock: socket.socket) -> None:
        if self._authenticated:
            return
        user, password = self._credentials()
        response = self._send_raw_action(
            sock,
            {
                "Action": "Login",
                "Username": user,
                "Secret": password,
                "Events": "off",
            },
        )
        if str(response.get("Response", "")).strip().lower() != "success":
            message = str(response.get("Message", "")).strip() or "AMI login failed"
            raise ToolError(
                AUTH_FAILED,
                message,
                {"action": "Login", "response": response.get("Response")},
            )
        self._authenticated = True

    def send_action(self, action: dict[str, Any]) -> dict[str, Any]:
        sock = self._ensure_socket()
        self._ensure_logged_in(sock)
        return self._send_raw_action(sock, action)


def _parse_ami_response(raw: str) -> dict[str, Any]:
    result: dict[str, Any] = {"raw": raw}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip()
    message = str(result.get("Message", "")).strip().lower()
    if "authentication" in message and (
        "failed" in message
        or "denied" in message
        or "reject" in message
        or "incorrect" in message
    ):
        raise ToolError(AUTH_FAILED, "AMI authentication failed")
    return result
