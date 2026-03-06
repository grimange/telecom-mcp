"""FreeSWITCH-specific normalization helpers."""

from __future__ import annotations

import csv
from io import StringIO
import re
from typing import Any

from .common import clamp_items


def _clean_esl_text(raw_text: str) -> str:
    lines = [line.strip() for line in raw_text.replace("\r", "").split("\n")]
    cleaned: list[str] = []
    for line in lines:
        if not line:
            continue
        if line.startswith("Content-Type:"):
            continue
        if line.startswith("Content-Length:"):
            continue
        if line.startswith("+OK"):
            line = line[3:].strip()
            if not line:
                continue
        cleaned.append(line)
    return "\n".join(cleaned)


def _parse_csv_inventory(raw_text: str, expected_first_col: str) -> list[dict[str, str]]:
    cleaned = _clean_esl_text(raw_text)
    lines = [line for line in cleaned.splitlines() if line]
    if not lines:
        return []
    header_index = -1
    for idx, line in enumerate(lines):
        first_col = line.split(",", 1)[0].strip().lower()
        if first_col == expected_first_col:
            header_index = idx
            break
    if header_index < 0:
        return []

    table_lines: list[str] = [lines[header_index]]
    for line in lines[header_index + 1 :]:
        lower = line.lower()
        if "total." in lower or "total " in lower:
            break
        if "," not in line:
            continue
        table_lines.append(line)
    reader = csv.DictReader(StringIO("\n".join(table_lines)))
    rows: list[dict[str, str]] = []
    for row in reader:
        normalized = {str(k).strip(): str(v).strip() for k, v in row.items() if k}
        if normalized:
            rows.append(normalized)
    return rows


def parse_channels(raw_text: str) -> list[dict[str, Any]]:
    rows = _parse_csv_inventory(raw_text, expected_first_col="uuid")
    items: list[dict[str, Any]] = []
    for row in rows:
        items.append(
            {
                "uuid": row.get("uuid", ""),
                "name": row.get("name", ""),
                "state": row.get("callstate") or row.get("state") or "Unknown",
                "caller": row.get("cid_num", ""),
                "callee": row.get("callee_num", ""),
                "duration_s": 0,
            }
        )
    return items


def parse_calls(raw_text: str) -> list[dict[str, Any]]:
    rows = _parse_csv_inventory(raw_text, expected_first_col="uuid")
    calls: list[dict[str, Any]] = []
    for row in rows:
        call_id = row.get("call_uuid") or row.get("uuid") or ""
        calls.append(
            {
                "call_id": call_id,
                "legs": 1,
                "state": row.get("callstate") or row.get("state") or "ACTIVE",
                "duration_s": 0,
            }
        )
    return calls


def parse_registrations(raw_text: str) -> list[dict[str, Any]]:
    cleaned = _clean_esl_text(raw_text)
    status_re = re.compile(r"\b(REGED|UNREGED|FAILED|FAIL_WAIT|EXPIRED|DOWN|UNKNOWN)\b")
    items: list[dict[str, Any]] = []
    for line in cleaned.splitlines():
        if not line:
            continue
        if line.lower().startswith("registrations"):
            continue
        match = status_re.search(line.upper())
        if not match:
            continue
        status = match.group(1)
        fields = line.split()
        user = fields[0] if fields else ""
        contact = fields[2] if len(fields) >= 3 else (fields[1] if len(fields) >= 2 else "")
        items.append(
            {
                "user": user,
                "contact": contact,
                "status": status,
                "expires_in_s": 0,
            }
        )
    return items


def normalize_health(latency_ms: int, version: str = "unknown") -> dict[str, Any]:
    return {
        "esl": {"ok": True, "latency_ms": latency_ms},
        "freeswitch_version": version,
        "profiles": [],
    }


def _extract_profile_name(line: str) -> str:
    match = re.search(
        r"(?i)\bprofile\b(?:\s*[:=]\s*|\s+name\s*[:=]\s*|\s+)([A-Za-z0-9_.-]+)",
        line,
    )
    if not match:
        return ""
    return match.group(1).strip()


def _extract_count(line: str, token: str) -> int | None:
    patterns = [
        rf"(?i)\b{re.escape(token)}s?\b\s*[:=]\s*(\d+)",
        rf"(?i)\b(\d+)\s+{re.escape(token)}s?\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, line)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
    return None


def _extract_state(line: str) -> str:
    match = re.search(
        r"\b(RUNNING|UP|DOWN|STOPPED|STARTING|NOREG|FAILED|UNKNOWN)\b",
        line.upper(),
    )
    if match:
        return match.group(1)
    return "UNKNOWN"


def _parse_sofia_status_structured(
    raw_text: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    cleaned = _clean_esl_text(raw_text)
    profiles: dict[str, dict[str, Any]] = {}
    gateways: list[dict[str, Any]] = []
    seen_gateways: set[tuple[str, str | None]] = set()
    issues: list[str] = []
    current_profile = ""

    for raw_line in cleaned.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lower = line.lower()

        profile_name = _extract_profile_name(line)
        if profile_name:
            current_profile = profile_name
            if current_profile not in profiles:
                profiles[current_profile] = {
                    "name": current_profile,
                    "state": "UNKNOWN",
                    "registrations": 0,
                    "gateways": 0,
                }
            state = _extract_state(line)
            if state != "UNKNOWN":
                profiles[current_profile]["state"] = state

        if current_profile:
            regs = _extract_count(line, "registration")
            if regs is not None:
                profiles[current_profile]["registrations"] = regs
            gateway_count = _extract_count(line, "gateway")
            if gateway_count is not None and not lower.startswith("gateway:"):
                profiles[current_profile]["gateways"] = gateway_count

        if "gateway" in lower:
            gw_match = re.search(
                r"(?i)\bgateway\b(?:\s*[:=]\s*|\s+)([A-Za-z0-9_.-]+)", line
            )
            if gw_match:
                gateway_name = gw_match.group(1).strip()
                gateway_profile: str | None = current_profile or None
                key = (gateway_name, gateway_profile)
                if key not in seen_gateways:
                    seen_gateways.add(key)
                    gateways.append(
                        {
                            "name": gateway_name,
                            "profile": gateway_profile,
                            "state": _extract_state(line),
                        }
                    )

    if not profiles:
        issues.append("No structured SIP profiles parsed from sofia status output.")
    if not gateways:
        issues.append("No structured gateway rows parsed from sofia status output.")

    return list(profiles.values()), gateways, issues


def normalize_sofia_status(raw_text: str) -> dict[str, Any]:
    profiles, gateways, issues = _parse_sofia_status_structured(raw_text)
    reg_items = parse_registrations(raw_text)
    reged = sum(
        1 for item in reg_items if str(item.get("status", "")).strip().upper() == "REGED"
    )
    return {
        "profiles": profiles,
        "gateways": gateways,
        "registrations_summary": {
            "total": len(reg_items),
            "reged": reged,
            "non_reged": max(len(reg_items) - reged, 0),
        },
        "data_quality": {
            "completeness": "full" if profiles or gateways else "partial",
            "issues": issues,
            "parsed_profiles": len(profiles),
            "parsed_gateways": len(gateways),
        },
        "raw": {"esl": raw_text},
    }


def normalize_channels(
    items: list[dict[str, Any]], limit: int, raw_text: str = ""
) -> dict[str, Any]:
    parsed_items = items or parse_channels(raw_text)
    normalized = [
        {
            "uuid": i.get("uuid", ""),
            "name": i.get("name", ""),
            "state": i.get("state", "Unknown"),
            "caller": i.get("caller", ""),
            "callee": i.get("callee", ""),
            "duration_s": int(i.get("duration_s", 0)),
        }
        for i in parsed_items
    ]
    quality = {
        "completeness": "full" if normalized else "partial",
        "issues": [] if normalized else ["No structured channel rows parsed from ESL output."],
        "parsed_items": len(normalized),
    }
    return {
        "channels": clamp_items(normalized, limit),
        "raw": {"esl": raw_text},
        "data_quality": quality,
    }


def normalize_registrations(
    items: list[dict[str, Any]], limit: int, raw: str
) -> dict[str, Any]:
    parsed_items = items or parse_registrations(raw)
    normalized = [
        {
            "user": i.get("user", ""),
            "contact": i.get("contact", ""),
            "status": i.get("status", "Unknown"),
            "expires_in_s": int(i.get("expires_in_s", 0) or 0),
        }
        for i in parsed_items
    ]
    quality = {
        "completeness": "full" if normalized else "partial",
        "issues": [] if normalized else ["No structured registration rows parsed from ESL output."],
        "parsed_items": len(normalized),
    }
    return {
        "items": clamp_items(normalized, limit),
        "raw": {"esl": raw},
        "data_quality": quality,
    }


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
    parsed_items = items or parse_calls(raw)
    normalized = [
        {
            "call_id": i.get("call_id", i.get("uuid", "")),
            "legs": int(i.get("legs", 1) or 1),
            "state": i.get("state", "ACTIVE"),
            "duration_s": int(i.get("duration_s", 0) or 0),
        }
        for i in parsed_items
    ]
    quality = {
        "completeness": "full" if normalized else "partial",
        "issues": [] if normalized else ["No structured call rows parsed from ESL output."],
        "parsed_items": len(normalized),
    }
    return {
        "calls": clamp_items(normalized, limit),
        "raw": {"esl": raw},
        "data_quality": quality,
    }
