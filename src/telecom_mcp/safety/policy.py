"""Shared safety policy controls for active telecom operations."""

from __future__ import annotations

import re
from typing import Any

from ..errors import NOT_ALLOWED, VALIDATION_ERROR, ToolError

PROBE_DEST_RE = re.compile(r"^[A-Za-z0-9+*#_.:@/-]{2,64}$")


def _normalized_str(value: Any, *, default: str) -> str:
    cleaned = str(value if value is not None else default).strip().lower()
    return cleaned or default


def target_policy_actual(target: Any) -> dict[str, Any]:
    return {
        "environment": _normalized_str(getattr(target, "environment", "unknown"), default="unknown"),
        "allow_active_validation": bool(getattr(target, "allow_active_validation", False)),
        "safety_tier": _normalized_str(getattr(target, "safety_tier", "standard"), default="standard"),
    }


def target_allows_active_validation(target: Any) -> bool:
    actual = target_policy_actual(target)
    return (
        actual["environment"] == "lab"
        and actual["allow_active_validation"] is True
        and actual["safety_tier"] == "lab_safe"
    )


def require_active_target_lab_safe(target: Any, *, tool_name: str) -> None:
    if target_allows_active_validation(target):
        return
    raise ToolError(
        NOT_ALLOWED,
        f"{tool_name} requires environment=lab and explicit allow_active_validation with safety_tier=lab_safe.",
        {
            "tool": tool_name,
            "required": {
                "environment": "lab",
                "allow_active_validation": True,
                "safety_tier": "lab_safe",
            },
            "actual": target_policy_actual(target),
        },
    )


def validate_probe_destination(destination: str) -> str:
    cleaned = destination.strip()
    if not cleaned:
        raise ToolError(VALIDATION_ERROR, "Field 'destination' must be non-empty")
    if not PROBE_DEST_RE.match(cleaned):
        raise ToolError(
            VALIDATION_ERROR,
            "Field 'destination' contains unsupported characters",
            {"destination": destination, "pattern": PROBE_DEST_RE.pattern},
        )
    return cleaned
