"""Standardized error types and helpers for telecom-mcp."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

TIMEOUT = "TIMEOUT"
AUTH_FAILED = "AUTH_FAILED"
CONNECTION_FAILED = "CONNECTION_FAILED"
NOT_FOUND = "NOT_FOUND"
NOT_ALLOWED = "NOT_ALLOWED"
UPSTREAM_ERROR = "UPSTREAM_ERROR"
VALIDATION_ERROR = "VALIDATION_ERROR"

ALLOWED_ERROR_CODES = {
    TIMEOUT,
    AUTH_FAILED,
    CONNECTION_FAILED,
    NOT_FOUND,
    NOT_ALLOWED,
    UPSTREAM_ERROR,
    VALIDATION_ERROR,
}


@dataclass(slots=True)
class ToolError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.code not in ALLOWED_ERROR_CODES:
            self.code = UPSTREAM_ERROR

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details or {},
        }


def map_exception(exc: Exception) -> ToolError:
    if isinstance(exc, ToolError):
        return exc
    if isinstance(exc, TimeoutError):
        return ToolError(TIMEOUT, "Operation timed out")
    if isinstance(exc, ConnectionError):
        return ToolError(CONNECTION_FAILED, "Connection failed")
    return ToolError(
        UPSTREAM_ERROR, "Unexpected upstream error", {"type": type(exc).__name__}
    )
