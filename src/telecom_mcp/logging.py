"""Audit logging with redaction for telecom-mcp."""

from __future__ import annotations

import json
import logging
import sys
from copy import deepcopy
from typing import Any

SENSITIVE_KEYS = {"password", "token", "secret", "authorization"}


def _is_sensitive_key(key: str) -> bool:
    k = key.lower()
    return any(s in k for s in SENSITIVE_KEYS)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if _is_sensitive_key(key):
                out[key] = "***REDACTED***"
            else:
                out[key] = redact(item)
        return out
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


class AuditLogger:
    def __init__(self, name: str = "telecom_mcp.audit") -> None:
        self._logger = logging.getLogger(name)
        # Rebind handler per instance so tests using capsys/capfd reliably capture stderr.
        self._logger.handlers.clear()
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(message)s"))
        self._logger.addHandler(handler)
        self._logger.propagate = False
        self._logger.setLevel(logging.INFO)

    def log_tool_call(
        self,
        *,
        tool: str,
        args: dict[str, Any],
        pbx_id: str | None,
        duration_ms: int,
        ok: bool,
        correlation_id: str,
        error: dict[str, Any] | None,
    ) -> None:
        record = {
            "event": "tool_call",
            "tool": tool,
            "args": redact(deepcopy(args)),
            "pbx_id": pbx_id,
            "duration_ms": duration_ms,
            "ok": ok,
            "correlation_id": correlation_id,
            "error": redact(error or {}),
        }
        self._logger.info(json.dumps(record, separators=(",", ":")))
