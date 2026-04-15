"""Asterisk-specific normalization helpers."""

from __future__ import annotations

from typing import Any

from .common import clamp_items


def normalize_health(
    ari_ok: bool,
    ari_latency: int,
    ami_ok: bool,
    ami_latency: int,
    ami_connectivity_ok: bool | None = None,
    ami_capability_ok: bool | None = None,
    ami_capabilities: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    version: str = "unknown",
) -> dict[str, Any]:
    connectivity_ok = ami_ok if ami_connectivity_ok is None else ami_connectivity_ok
    capability_ok = ami_ok if ami_capability_ok is None else ami_capability_ok
    warning_items = list(warnings or [])
    degraded = bool(warning_items)
    return {
        "ari": {"ok": ari_ok, "latency_ms": ari_latency},
        "ami": {
            "ok": ami_ok,
            "latency_ms": ami_latency,
            "connectivity_ok": connectivity_ok,
            "capability_ok": capability_ok,
            "capabilities": ami_capabilities or {},
        },
        "asterisk_version": version,
        "pjsip_loaded": True,
        "degraded": degraded,
        "warnings": warning_items,
        "data_quality": {
            "degraded": degraded,
            "issues": warning_items,
        },
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
        endpoint = event.get("ObjectName") or event.get("Endpoint") or _endpoint_from_uri(
            event.get("URI")
        )
        if not endpoint:
            continue
        endpoint_items.append(event)
    if endpoint_items:
        return endpoint_items
    if events:
        return []
    if ami_response and str(ami_response.get("Response", "")).lower() != "error":
        inferred = _infer_endpoint(ami_response)
        if inferred:
            return [ami_response]
    return []


def _endpoint_from_uri(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if "sip:" in text and "@" in text:
        sip_part = text.split("sip:", 1)[1]
        endpoint = sip_part.split("@", 1)[0].strip("<>\"' ")
        if endpoint:
            return endpoint
    return None


def _infer_endpoint(item: dict[str, Any]) -> str | None:
    for key in (
        "endpoint",
        "ObjectName",
        "Endpoint",
        "Aor",
        "AoR",
        "ID",
        "Id",
        "Resource",
        "Contact",
        "URI",
    ):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            if key in {"Contact", "URI"}:
                parsed = _endpoint_from_uri(value)
                if parsed:
                    return parsed
            return value.strip()
    return None


def normalize_pjsip_endpoints(
    items: list[dict[str, Any]], limit: int
) -> dict[str, Any]:
    normalized_by_endpoint: dict[str, dict[str, Any]] = {}
    unknown_rows = 0
    for item in items:
        endpoint = _infer_endpoint(item)
        if not endpoint:
            unknown_rows += 1
            continue
        current = normalized_by_endpoint.setdefault(
            endpoint,
            {"endpoint": endpoint, "state": "Unknown", "contacts": 0},
        )
        state = (
            item.get("state")
            or item.get("Status")
            or item.get("DeviceState")
            or item.get("AorStatus")
            or "Unknown"
        )
        if str(current.get("state", "Unknown")).lower() == "unknown" and str(
            state
        ).strip():
            current["state"] = state

        contacts_raw = item.get("contacts", item.get("Contacts", 0))
        try:
            contacts = int(contacts_raw or 0)
        except (TypeError, ValueError):
            contacts = 0
        event_name = str(item.get("Event", "")).lower()
        if event_name == "contactstatusdetail":
            contacts = max(contacts, 1)
        if contacts > int(current.get("contacts", 0) or 0):
            current["contacts"] = contacts

    quality = {"completeness": "full", "issues": []}
    if unknown_rows:
        quality["completeness"] = "partial"
        quality["issues"].append(
            f"Dropped {unknown_rows} endpoint rows missing identifier."
        )
    normalized = [normalized_by_endpoint[key] for key in sorted(normalized_by_endpoint)]

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
    return {
        "channels": clamp_items(normalized, limit),
        "data_quality": {
            "completeness": "full",
            "issues": [],
            "fallback_used": False,
        },
    }


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


def extract_pjsip_contact_items(ami_response: dict[str, Any]) -> list[dict[str, Any]]:
    raw_text = str(ami_response.get("raw", ""))
    events = parse_ami_event_list(raw_text)
    contacts: list[dict[str, Any]] = []
    for event in events:
        if str(event.get("Event", "")).lower() != "contactlist":
            continue
        contacts.append(event)
    return contacts


def extract_core_show_channel_items(ami_response: dict[str, Any]) -> list[dict[str, Any]]:
    raw_text = str(ami_response.get("raw", ""))
    events = parse_ami_event_list(raw_text)
    items: list[dict[str, Any]] = []
    for event in events:
        if str(event.get("Event", "")).lower() != "coreshowchannel":
            continue
        items.append(event)
    if items:
        return items
    if events:
        return []
    if ami_response and str(ami_response.get("Response", "")).strip().lower() != "error":
        if ami_response.get("Channel") or ami_response.get("Uniqueid"):
            return [ami_response]
    return []


def extract_pjsip_registration_items(ami_response: dict[str, Any]) -> list[dict[str, Any]]:
    raw_text = str(ami_response.get("raw", ""))
    events = parse_ami_event_list(raw_text)
    items: list[dict[str, Any]] = []
    for event in events:
        event_name = str(event.get("Event", "")).lower()
        if event_name in {"outboundregistrationdetail", "registrationsoutbound"}:
            items.append(event)
    if items:
        return items
    if events:
        return []
    if ami_response and str(ami_response.get("Response", "")).strip().lower() != "error":
        if ami_response.get("Registration") or ami_response.get("ObjectName"):
            return [ami_response]
    return []


def normalize_pjsip_contacts(items: list[dict[str, Any]], limit: int) -> dict[str, Any]:
    normalized: list[dict[str, Any]] = []
    for item in items:
        contact = str(item.get("ObjectName", "") or item.get("Contact", "")).strip()
        endpoint = (
            str(item.get("Endpoint", "")).strip()
            or _endpoint_from_uri(item.get("URI"))
            or "unknown"
        )
        status = str(item.get("Status", "") or item.get("ContactStatus", "")).strip() or "Unknown"
        normalized.append(
            {
                "contact": contact or "unknown",
                "endpoint": endpoint,
                "uri": str(item.get("URI", "")).strip(),
                "status": status,
                "aor": str(item.get("AOR", "") or item.get("Aor", "")).strip(),
            }
        )
    return {"items": clamp_items(normalized, limit), "next_cursor": None}


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
