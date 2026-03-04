"""FreeSWITCH-specific normalization helpers."""

from __future__ import annotations

from typing import Any

from .common import clamp_items


def normalize_health(latency_ms: int, version: str = "unknown") -> dict[str, Any]:
    return {
        "esl": {"ok": True, "latency_ms": latency_ms},
        "freeswitch_version": version,
    }


def normalize_sofia_status(raw_text: str) -> dict[str, Any]:
    return {
        "profiles": [],
        "gateways": [],
        "raw": {"esl": raw_text},
    }


def normalize_channels(items: list[dict[str, Any]], limit: int) -> dict[str, Any]:
    normalized = [
        {
            "uuid": i.get("uuid", ""),
            "name": i.get("name", ""),
            "state": i.get("state", "Unknown"),
            "caller": i.get("caller", ""),
            "callee": i.get("callee", ""),
            "duration_s": int(i.get("duration_s", 0)),
        }
        for i in items
    ]
    return {"channels": clamp_items(normalized, limit)}
