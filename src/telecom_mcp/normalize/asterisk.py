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
    response_state = str(ami_response.get("Response", "")).strip().lower()
    exists = bool(ami_response) and response_state != "error"
    state = ami_response.get("Status") or ami_response.get("State") or "Unknown"
    return {
        "endpoint": endpoint,
        "exists": exists,
        "state": state,
        "contacts": ami_response.get("contacts", []),
        "aor": ami_response.get("Aor") or endpoint,
        "raw": {"ami_action": "PJSIPShowEndpoint", "ami_response": ami_response},
    }


def parse_ami_event_list(raw_text: str) -> list[dict[str, Any]]:
    chunks = [chunk.strip() for chunk in raw_text.split("\r\n\r\n") if chunk.strip()]
    events: list[dict[str, Any]] = []
    for chunk in chunks:
        event: dict[str, Any] = {}
        for line in chunk.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            event[key.strip()] = value.strip()
        if event:
            events.append(event)
    return events


def extract_pjsip_endpoint_items(ami_response: dict[str, Any]) -> list[dict[str, Any]]:
    raw_text = str(ami_response.get("raw", ""))
    events = parse_ami_event_list(raw_text)
    endpoint_items: list[dict[str, Any]] = []
    for event in events:
        event_name = str(event.get("Event", "")).lower()
        if event_name not in {"endpointlist", "contactstatusdetail"}:
            continue
        endpoint = event.get("ObjectName") or event.get("Endpoint")
        if not endpoint:
            continue
        endpoint_items.append(event)
    if endpoint_items:
        return endpoint_items
    if ami_response and str(ami_response.get("Response", "")).lower() != "error":
        return [ami_response]
    return []


def normalize_pjsip_endpoints(
    items: list[dict[str, Any]], limit: int
) -> dict[str, Any]:
    normalized: list[dict[str, Any]] = []
    unknown_rows = 0
    for item in items:
        endpoint = (
            item.get("endpoint")
            or item.get("ObjectName")
            or item.get("Endpoint")
            or item.get("Aor")
            or item.get("URI")
        )
        if not endpoint:
            unknown_rows += 1
            endpoint = "unknown"
        contacts_raw = item.get("contacts", item.get("Contacts", 0))
        try:
            contacts = int(contacts_raw or 0)
        except (TypeError, ValueError):
            contacts = 0
        normalized.append(
            {
                "endpoint": endpoint,
                "state": item.get("state") or item.get("Status") or "Unknown",
                "contacts": contacts,
            }
        )

    quality = {"completeness": "full", "issues": []}
    if unknown_rows:
        quality["completeness"] = "partial"
        quality["issues"].append(f"{unknown_rows} endpoint rows missing identifier.")

    return {
        "items": clamp_items(normalized, limit),
        "next_cursor": None,
        "data_quality": quality,
    }


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
