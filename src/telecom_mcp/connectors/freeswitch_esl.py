"""Minimal FreeSWITCH ESL connector with bounded calls."""

from __future__ import annotations

import socket
import time

from ..config import ESLConfig
from ..errors import AUTH_FAILED, CONNECTION_FAILED, NOT_ALLOWED, TIMEOUT, UPSTREAM_ERROR, ToolError


class FreeSWITCHESLConnector:
    def __init__(self, config: ESLConfig, *, timeout_s: float = 4.0) -> None:
        self.config = config
        self.timeout_s = timeout_s
        self._sock: socket.socket | None = None

    def connect(self) -> None:
        try:
            self._sock = socket.create_connection((self.config.host, self.config.port), timeout=self.timeout_s)
            self._sock.settimeout(self.timeout_s)
        except TimeoutError as exc:
            raise ToolError(TIMEOUT, "ESL connection timed out") from exc
        except OSError as exc:
            raise ToolError(CONNECTION_FAILED, "ESL connection failed", {"reason": str(exc)}) from exc

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None

    def _ensure_socket(self) -> socket.socket:
        if self._sock is None:
            self.connect()
        assert self._sock is not None
        return self._sock

    def _password(self) -> str:
        import os

        password = os.getenv(self.config.password_env)
        if not password:
            raise ToolError(AUTH_FAILED, "ESL password missing from environment")
        return password

    def ping(self) -> dict[str, int | bool]:
        started = time.monotonic()
        _ = self.api("status")
        return {"ok": True, "latency_ms": int((time.monotonic() - started) * 1000)}

    def api(self, cmd: str) -> str:
        if cmd.strip().lower().startswith("bgapi"):
            raise ToolError(NOT_ALLOWED, "bgapi is not allowed in v1")

        sock = self._ensure_socket()
        auth_payload = f"auth {self._password()}\n\n".encode("utf-8")
        cmd_payload = f"api {cmd}\n\n".encode("utf-8")

        try:
            sock.sendall(auth_payload)
            _ = sock.recv(4096)
            sock.sendall(cmd_payload)
            return sock.recv(65535).decode("utf-8", errors="replace")
        except TimeoutError as exc:
            self.close()
            raise ToolError(TIMEOUT, "ESL command timed out", {"cmd": cmd}) from exc
        except OSError as exc:
            self.close()
            raise ToolError(UPSTREAM_ERROR, "ESL I/O error", {"cmd": cmd, "reason": str(exc)}) from exc
