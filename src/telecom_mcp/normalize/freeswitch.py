"""FreeSWITCH-specific normalization helpers."""

from __future__ import annotations

from typing import Any

from .common import clamp_items


def normalize_health(latency_ms: int, version: str = "unknown") -> dict[str, Any]:
    return {
        "esl": {"ok": True, "latency_ms": latency_ms},
        "freeswitch_version": version,
        "profiles": [],
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
    return {"channels": clamp_items(normalized, limit), "raw": {}}


def normalize_registrations(
    items: list[dict[str, Any]], limit: int, raw: str
) -> dict[str, Any]:
    normalized = [
        {
            "user": i.get("user", ""),
            "contact": i.get("contact", ""),
            "status": i.get("status", "Unknown"),
            "expires_in_s": int(i.get("expires_in_s", 0) or 0),
        }
        for i in items
    ]
    return {"items": clamp_items(normalized, limit), "raw": {"esl": raw}}


def normalize_gateway_status(gateway: str, raw: str) -> dict[str, Any]:
    upper = raw.upper()
    if "DOWN" in upper:
        state = "DOWN"
    elif "UP" in upper or "REGED" in upper:
        state = "UP"
    else:
        state = "UNKNOWN"
    return {"gateway": gateway, "state": state, "last_error": None, "raw": {"esl": raw}}


def normalize_calls(
    items: list[dict[str, Any]], limit: int, raw: str
) -> dict[str, Any]:
    normalized = [
        {
            "call_id": i.get("call_id", i.get("uuid", "")),
            "legs": int(i.get("legs", 1) or 1),
            "state": i.get("state", "ACTIVE"),
            "duration_s": int(i.get("duration_s", 0) or 0),
        }
        for i in items
    ]
    return {"calls": clamp_items(normalized, limit), "raw": {"esl": raw}}
