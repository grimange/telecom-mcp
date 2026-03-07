"""FreeSWITCH ESL connector with framed protocol handling."""

from __future__ import annotations

from dataclasses import dataclass
import socket
import time
from typing import Any

from ..config import ESLConfig
from ..errors import (
    AUTH_FAILED,
    CONNECTION_FAILED,
    NOT_ALLOWED,
    TIMEOUT,
    UPSTREAM_ERROR,
    ToolError,
)


@dataclass
class _ESLFrame:
    headers: dict[str, str]
    body: bytes

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "").strip().lower()

    def reply_text(self) -> str:
        return self.headers.get("reply-text", "")

    def body_text(self) -> str:
        return self.body.decode("utf-8", errors="replace")

    def payload_text(self) -> str:
        body = self.body_text()
        if body:
            return body
        return self.reply_text()


class FreeSWITCHESLConnector:
    def __init__(self, config: ESLConfig, *, timeout_s: float = 4.0) -> None:
        self.config = config
        self.timeout_s = timeout_s
        self.max_retries = 1
        self._sock: socket.socket | Any | None = None
        self._recv_buffer = bytearray()
        self._authenticated = False

    def connect(self) -> None:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                self._sock = socket.create_connection(
                    (self.config.host, self.config.port), timeout=self.timeout_s
                )
                self._sock.settimeout(self.timeout_s)
                self._recv_buffer.clear()
                self._authenticated = False
                return
            except TimeoutError as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    raise ToolError(TIMEOUT, "ESL connection timed out") from exc
            except OSError as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    raise ToolError(
                        CONNECTION_FAILED, "ESL connection failed", {"reason": str(exc)}
                    ) from exc
            time.sleep(min(0.05 * (attempt + 1), 0.2))
        if last_error is not None:
            raise ToolError(CONNECTION_FAILED, "ESL connection failed", {"reason": str(last_error)})

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None
                self._recv_buffer.clear()
                self._authenticated = False

    def _ensure_socket(self) -> Any:
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

        for attempt in range(self.max_retries + 1):
            sock = self._ensure_socket()
            try:
                self._ensure_authenticated(sock)
                self._send(sock, f"api {cmd}\n\n".encode("utf-8"))
                frame = self._read_expected_frame(
                    sock,
                    expected_types={"api/response"},
                    command=cmd,
                )
                return frame.payload_text()
            except ToolError as exc:
                if exc.code in {TIMEOUT, CONNECTION_FAILED}:
                    self.close()
                    if attempt >= self.max_retries:
                        raise
                    time.sleep(min(0.05 * (attempt + 1), 0.2))
                    continue
                raise
            except TimeoutError as exc:
                self.close()
                if attempt >= self.max_retries:
                    raise ToolError(TIMEOUT, "ESL command timed out", {"cmd": cmd}) from exc
            except OSError as exc:
                self.close()
                if attempt >= self.max_retries:
                    raise ToolError(
                        CONNECTION_FAILED, "ESL I/O error", {"cmd": cmd, "reason": str(exc)}
                    ) from exc
            time.sleep(min(0.05 * (attempt + 1), 0.2))
        raise ToolError(CONNECTION_FAILED, "ESL I/O error", {"cmd": cmd})

    def _send(self, sock: Any, payload: bytes) -> None:
        try:
            sock.sendall(payload)
        except TimeoutError as exc:
            raise ToolError(TIMEOUT, "ESL command timed out") from exc
        except OSError as exc:
            raise ToolError(CONNECTION_FAILED, "ESL I/O error", {"reason": str(exc)}) from exc

    def _ensure_authenticated(self, sock: Any) -> None:
        if self._authenticated:
            return
        greeting = self._read_next_frame(sock, command="greeting")
        if greeting.content_type != "auth/request":
            raise ToolError(
                UPSTREAM_ERROR,
                "Unexpected ESL greeting frame",
                {
                    "expected": "auth/request",
                    "received": greeting.content_type or "unknown",
                    "payload_sample": greeting.payload_text()[:200],
                },
            )

        self._send(sock, f"auth {self._password()}\n\n".encode("utf-8"))
        auth_reply = self._read_expected_frame(
            sock,
            expected_types={"command/reply"},
            command="auth",
            allow_event_frames=False,
        )
        if "+ok" not in auth_reply.payload_text().lower():
            raise ToolError(
                AUTH_FAILED,
                "ESL authentication failed",
                {"reply": auth_reply.payload_text()[:200]},
            )
        self._authenticated = True

    def _read_expected_frame(
        self,
        sock: Any,
        *,
        expected_types: set[str],
        command: str,
        allow_event_frames: bool = True,
    ) -> _ESLFrame:
        while True:
            frame = self._read_next_frame(sock, command=command)
            content_type = frame.content_type
            if content_type in expected_types:
                return frame
            if allow_event_frames and content_type.startswith("text/event-"):
                continue
            raise ToolError(
                UPSTREAM_ERROR,
                "Unexpected ESL frame type",
                {
                    "command": command,
                    "expected_types": sorted(expected_types),
                    "received_type": content_type or "unknown",
                    "payload_sample": frame.payload_text()[:200],
                },
            )

    def _read_next_frame(self, sock: Any, *, command: str) -> _ESLFrame:
        deadline = time.monotonic() + max(self.timeout_s, 0.001)
        while True:
            parsed = _try_parse_frame(self._recv_buffer)
            if parsed is not None:
                return parsed

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ToolError(TIMEOUT, "ESL command timed out", {"cmd": command})

            if hasattr(sock, "settimeout"):
                sock.settimeout(max(0.001, min(self.timeout_s, remaining)))
            try:
                chunk = sock.recv(65535)
            except TimeoutError as exc:
                raise ToolError(TIMEOUT, "ESL command timed out", {"cmd": command}) from exc
            except OSError as exc:
                raise ToolError(
                    CONNECTION_FAILED,
                    "ESL I/O error",
                    {"cmd": command, "reason": str(exc)},
                ) from exc
            if not chunk:
                raise ToolError(
                    CONNECTION_FAILED,
                    "ESL connection closed",
                    {"cmd": command},
                )
            self._recv_buffer.extend(chunk)


def _try_parse_frame(buffer: bytearray) -> _ESLFrame | None:
    header_end, separator_len = _find_header_boundary(buffer)
    if header_end < 0:
        return None

    header_blob = bytes(buffer[:header_end]).decode("utf-8", errors="replace")
    headers: dict[str, str] = {}
    for raw_line in header_blob.replace("\r", "").split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()

    content_length = 0
    if "content-length" in headers:
        try:
            content_length = int(headers["content-length"])
        except ValueError as exc:
            raise ToolError(
                UPSTREAM_ERROR,
                "Malformed ESL frame content-length",
                {"content_length": headers["content-length"]},
            ) from exc
        if content_length < 0:
            raise ToolError(
                UPSTREAM_ERROR,
                "Malformed ESL frame content-length",
                {"content_length": headers["content-length"]},
            )

    frame_size = header_end + separator_len + content_length
    if len(buffer) < frame_size:
        return None

    body = bytes(buffer[header_end + separator_len : frame_size])
    del buffer[:frame_size]
    return _ESLFrame(headers=headers, body=body)


def _find_header_boundary(buffer: bytearray) -> tuple[int, int]:
    raw = bytes(buffer)
    rn = raw.find(b"\r\n\r\n")
    nn = raw.find(b"\n\n")
    if rn == -1 and nn == -1:
        return -1, 0
    if rn != -1 and (nn == -1 or rn <= nn):
        return rn, 4
    return nn, 2
