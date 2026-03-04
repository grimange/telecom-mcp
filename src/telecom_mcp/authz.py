"""Mode gating and authorization helpers."""

from __future__ import annotations

from enum import StrEnum

from .errors import NOT_ALLOWED, ToolError, VALIDATION_ERROR


class Mode(StrEnum):
    INSPECT = "inspect"
    PLAN = "plan"
    EXECUTE_SAFE = "execute_safe"
    EXECUTE_FULL = "execute_full"


MODE_ORDER = {
    Mode.INSPECT: 0,
    Mode.PLAN: 1,
    Mode.EXECUTE_SAFE: 2,
    Mode.EXECUTE_FULL: 3,
}


def parse_mode(value: str | Mode | None) -> Mode:
    if isinstance(value, Mode):
        return value
    if value is None:
        return Mode.INSPECT
    try:
        return Mode(value)
    except ValueError as exc:
        raise ToolError(VALIDATION_ERROR, f"Invalid mode: {value}") from exc


def require_mode(
    tool_name: str, current_mode: str | Mode, minimum_mode: str | Mode
) -> None:
    current = parse_mode(current_mode)
    minimum = parse_mode(minimum_mode)
    if MODE_ORDER[current] < MODE_ORDER[minimum]:
        raise ToolError(
            NOT_ALLOWED,
            f"Tool {tool_name} requires mode {minimum.value} (current: {current.value})",
            {
                "tool": tool_name,
                "minimum_mode": minimum.value,
                "current_mode": current.value,
            },
        )
