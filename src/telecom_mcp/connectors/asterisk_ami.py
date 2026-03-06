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
        self.max_retries = 1
        self._sock: socket.socket | None = None
        self._authenticated = False

    def connect(self) -> None:
        _ = self._credentials()
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                self._sock = socket.create_connection(
                    (self.config.host, self.config.port), timeout=self.timeout_s
                )
                self._sock.settimeout(self.timeout_s)
                return
            except TimeoutError as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    raise ToolError(TIMEOUT, "AMI connection timed out") from exc
            except OSError as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    raise ToolError(
                        CONNECTION_FAILED, "AMI connection failed", {"reason": str(exc)}
                    ) from exc
            time.sleep(min(0.05 * (attempt + 1), 0.2))
        if last_error is not None:
            raise ToolError(CONNECTION_FAILED, "AMI connection failed", {"reason": str(last_error)})

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
            data = self._read_action_response(sock, action_name=str(action.get("Action", "")))
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

    def _read_action_response(self, sock: socket.socket, *, action_name: str) -> bytes:
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
                raw = b"".join(chunks).decode("utf-8", errors="replace")
                if raw and _ami_response_complete(raw):
                    return b"".join(chunks)
                break
            if not chunk:
                break
            chunks.append(chunk)
            raw = b"".join(chunks).decode("utf-8", errors="replace")
            if _ami_response_complete(raw):
                return b"".join(chunks)

        partial = b"".join(chunks).decode("utf-8", errors="replace")
        details: dict[str, Any] = {"action": action_name}
        if partial:
            details["partial_response"] = partial[:500]
        raise ToolError(TIMEOUT, "AMI action timed out", details)

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
        for attempt in range(self.max_retries + 1):
            try:
                sock = self._ensure_socket()
                self._ensure_logged_in(sock)
                return self._send_raw_action(sock, action)
            except ToolError as exc:
                if exc.code not in {TIMEOUT, CONNECTION_FAILED} or attempt >= self.max_retries:
                    raise
                self.close()
                time.sleep(min(0.05 * (attempt + 1), 0.2))
        raise ToolError(UPSTREAM_ERROR, "AMI action failed after retries")


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


def _ami_response_complete(raw: str) -> bool:
    text = raw.lower()
    if "response:" not in text:
        return False
    if "eventlist: start" in text:
        return "eventlist: complete" in text
    # Single-action responses end on frame boundary.
    return "\r\n\r\n" in raw
