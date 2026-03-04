"""Shared normalization helpers."""

from __future__ import annotations

from typing import Any


def clamp_items(items: list[Any], limit: int) -> list[Any]:
    if limit <= 0:
        return []
    return items[:limit]
