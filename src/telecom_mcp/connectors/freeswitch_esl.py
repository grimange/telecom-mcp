"""Minimal FreeSWITCH ESL connector with bounded calls."""

from __future__ import annotations

import socket
import time
from typing import Any

from ..config import ESLConfig
from ..errors import (
    AUTH_FAILED,
    CONNECTION_FAILED,
    NOT_ALLOWED,
    TIMEOUT,
    ToolError,
)


class FreeSWITCHESLConnector:
    def __init__(self, config: ESLConfig, *, timeout_s: float = 4.0) -> None:
        self.config = config
        self.timeout_s = timeout_s
        self._sock: socket.socket | None = None

    def connect(self) -> None:
        try:
            self._sock = socket.create_connection(
                (self.config.host, self.config.port), timeout=self.timeout_s
            )
            self._sock.settimeout(self.timeout_s)
        except TimeoutError as exc:
            raise ToolError(TIMEOUT, "ESL connection timed out") from exc
        except OSError as exc:
            raise ToolError(
                CONNECTION_FAILED, "ESL connection failed", {"reason": str(exc)}
            ) from exc

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

    def ping(self) -> dict[str, int | bool | str]:
        started = time.monotonic()
        raw = self.api("status")
        return {
            "ok": True,
            "latency_ms": int((time.monotonic() - started) * 1000),
            "raw": raw,
        }

    def api(self, cmd: str) -> str:
        if cmd.strip().lower().startswith("bgapi"):
            raise ToolError(NOT_ALLOWED, "bgapi is not allowed in v1")

        sock = self._ensure_socket()
        auth_payload = f"auth {self._password()}\n\n".encode("utf-8")
        cmd_payload = f"api {cmd}\n\n".encode("utf-8")

        try:
            sock.sendall(auth_payload)
            _ = self._read_response(sock, command="auth")
            sock.sendall(cmd_payload)
            return self._read_response(sock, command=cmd)
        except TimeoutError as exc:
            self.close()
            raise ToolError(TIMEOUT, "ESL command timed out", {"cmd": cmd}) from exc
        except OSError as exc:
            self.close()
            raise ToolError(
                CONNECTION_FAILED, "ESL I/O error", {"cmd": cmd, "reason": str(exc)}
            ) from exc

    def _read_response(self, sock: socket.socket, *, command: str) -> str:
        deadline = time.monotonic() + max(self.timeout_s, 0.001)
        chunks: list[bytes] = []

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            sock.settimeout(max(0.001, min(self.timeout_s, remaining)))
            try:
                chunk = sock.recv(65535)
            except TimeoutError:
                text = b"".join(chunks).decode("utf-8", errors="replace")
                if text and _esl_response_complete(text):
                    return text
                break
            if not chunk:
                text = b"".join(chunks).decode("utf-8", errors="replace")
                if text:
                    return text
                break
            chunks.append(chunk)
            text = b"".join(chunks).decode("utf-8", errors="replace")
            if _esl_response_complete(text):
                return text

        partial = b"".join(chunks).decode("utf-8", errors="replace")
        details: dict[str, Any] = {"cmd": command}
        if partial:
            details["partial_response"] = partial[:500]
        raise ToolError(TIMEOUT, "ESL command timed out", details)


def _esl_response_complete(text: str) -> bool:
    normalized = text.replace("\r\n", "\n")
    if "\n\n" not in normalized:
        return False

    header, body = normalized.split("\n\n", 1)
    content_length: int | None = None
    for line in header.splitlines():
        if line.lower().startswith("content-length:"):
            raw = line.split(":", 1)[1].strip()
            if raw.isdigit():
                content_length = int(raw)
            break

    if content_length is not None:
        return len(body.encode("utf-8")) >= content_length

    lowered = normalized.lower()
    if "-err" in lowered:
        return True
    if "+ok" in lowered:
        return True
    return normalized.endswith("\n\n")
