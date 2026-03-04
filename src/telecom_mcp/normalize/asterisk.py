"""Asterisk-specific normalization helpers."""

from __future__ import annotations

from typing import Any

from .common import clamp_items


def normalize_health(
    ari_ok: bool,
    ari_latency: int,
    ami_ok: bool,
    ami_latency: int,
    version: str = "unknown",
) -> dict[str, Any]:
    return {
        "ari": {"ok": ari_ok, "latency_ms": ari_latency},
        "ami": {"ok": ami_ok, "latency_ms": ami_latency},
        "asterisk_version": version,
        "pjsip_loaded": True,
    }


def normalize_pjsip_endpoint(
    endpoint: str, ami_response: dict[str, Any]
) -> dict[str, Any]:
    exists = bool(ami_response)
    state = ami_response.get("Status") or ami_response.get("State") or "Unknown"
    return {
        "endpoint": endpoint,
        "exists": exists,
        "state": state,
        "contacts": ami_response.get("contacts", []),
        "aor": ami_response.get("Aor") or endpoint,
        "raw": {"ami_action": "PJSIPShowEndpoint", "ami_response": ami_response},
    }


def normalize_pjsip_endpoints(
    items: list[dict[str, Any]], limit: int
) -> dict[str, Any]:
    normalized = [
        {
            "endpoint": item.get("endpoint") or item.get("ObjectName") or "unknown",
            "state": item.get("state") or item.get("Status") or "Unknown",
            "contacts": int(item.get("contacts", 0)),
        }
        for item in items
    ]
    return {"items": clamp_items(normalized, limit), "next_cursor": None}


def normalize_active_channels(
    channels: list[dict[str, Any]], limit: int
) -> dict[str, Any]:
    normalized = [
        {
            "channel_id": c.get("id") or c.get("Uniqueid") or "unknown",
            "name": c.get("name") or c.get("Channel") or "unknown",
            "state": c.get("state") or c.get("ChannelStateDesc") or "Unknown",
            "caller": c.get("caller") or c.get("CallerIDNum") or "",
            "callee": c.get("callee") or c.get("ConnectedLineNum") or "",
            "duration_s": int(c.get("duration_s", c.get("Duration", 0) or 0)),
        }
        for c in channels
    ]
    return {"channels": clamp_items(normalized, limit)}


def normalize_pjsip_registration(
    registration: str, ami_response: dict[str, Any]
) -> dict[str, Any]:
    state = ami_response.get("Status") or ami_response.get("State") or "Unknown"
    last_error = ami_response.get("Error") or ami_response.get("Message")
    return {
        "registration": registration,
        "state": state,
        "last_error": last_error,
        "raw": ami_response,
    }


def normalize_bridges(bridges: list[dict[str, Any]], limit: int) -> dict[str, Any]:
    normalized = [
        {
            "bridge_id": b.get("id") or b.get("BridgeUniqueid") or "unknown",
            "type": b.get("bridge_type") or b.get("type") or "unknown",
            "channels": (
                len(b.get("channels", []))
                if isinstance(b.get("channels"), list)
                else int(b.get("NumChannels", 0) or 0)
            ),
        }
        for b in bridges
    ]
    return {"bridges": clamp_items(normalized, limit)}


def normalize_channel_details(
    channel_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    return {
        "channel_id": channel_id,
        "name": payload.get("name") or payload.get("Channel") or "unknown",
        "state": payload.get("state") or payload.get("ChannelStateDesc") or "Unknown",
        "caller": payload.get("caller") or payload.get("CallerIDNum") or "",
        "callee": payload.get("callee") or payload.get("ConnectedLineNum") or "",
        "bridge_id": payload.get("bridge_id") or payload.get("BridgeId"),
        "raw": payload,
    }
