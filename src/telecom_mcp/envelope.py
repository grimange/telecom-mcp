"""Envelope helpers for MCP tool responses."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .errors import ToolError


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_envelope(
    *,
    ok: bool,
    target: dict[str, Any],
    duration_ms: int,
    correlation_id: str,
    data: dict[str, Any] | None = None,
    error: ToolError | dict[str, Any] | None = None,
) -> dict[str, Any]:
    error_payload: dict[str, Any] | None
    if isinstance(error, ToolError):
        error_payload = error.to_dict()
    else:
        error_payload = error

    return {
        "ok": ok,
        "timestamp": utc_now_iso(),
        "target": target,
        "duration_ms": duration_ms,
        "correlation_id": correlation_id,
        "data": data or {},
        "error": error_payload,
    }
