"""Optional SSH fallback connector (read-only placeholder for future use)."""

from __future__ import annotations

from ..errors import NOT_ALLOWED, ToolError


def run_read_only_command(_: str) -> str:
    raise ToolError(NOT_ALLOWED, "SSH execution is disabled in v1")
