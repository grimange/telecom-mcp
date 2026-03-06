"""Cross-platform telecom tools."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ..errors import VALIDATION_ERROR, ToolError


def _require_str(args: dict[str, Any], key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value:
        raise ToolError(VALIDATION_ERROR, f"Field '{key}' must be a non-empty string")
    return value


def _dict_arg(args: dict[str, Any], key: str) -> dict[str, Any]:
    value = args.get(key)
    if isinstance(value, dict):
        return value
    return {}


def _collect_asterisk_summary(
    ctx: Any,
    pbx_id: str,
    *,
    channel_limit: int = 200,
    endpoint_limit: int = 500,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    quality_issues: list[str] = []

    health_payload = ctx.call_tool_internal("asterisk.health", {"pbx_id": pbx_id})["data"]
    channels_payload = ctx.call_tool_internal(
        "asterisk.active_channels", {"pbx_id": pbx_id, "limit": channel_limit}
    )["data"]
    endpoints_payload = ctx.call_tool_internal(
        "asterisk.pjsip_show_endpoints", {"pbx_id": pbx_id, "limit": endpoint_limit}
    )["data"]

    channels = channels_payload.get("channels", [])
    if not isinstance(channels, list):
        channels = []
        quality_issues.append("Channel inventory payload was not a list.")

    endpoint_items = endpoints_payload.get("items", [])
    if not isinstance(endpoint_items, list):
        endpoint_items = []
        quality_issues.append("Endpoint inventory payload was not a list.")

    unknown_endpoints = sum(
        1
        for item in endpoint_items
        if str(item.get("endpoint", "")).strip().lower() in {"", "unknown"}
    )
    if unknown_endpoints:
        quality_issues.append(
            f"Endpoint parser emitted {unknown_endpoints} unknown endpoint rows."
        )

    summary_data = {
        "version": health_payload.get("asterisk_version", "unknown"),
        "uptime_seconds": None,
        "channels_active": len(channels),
        "registrations": {
            "endpoints_registered": sum(
                1 for item in endpoint_items if int(item.get("contacts", 0) or 0) > 0
            ),
            "endpoints_unreachable": sum(
                1 for item in endpoint_items if int(item.get("contacts", 0) or 0) == 0
            ),
        },
        "trunks": {"up": None, "down": None},
        "notes": [],
    }
    quality_issues.append("Trunk counters unavailable without trunk parsers.")
    return summary_data, endpoint_items, channels, quality_issues


def _collect_freeswitch_summary(
    ctx: Any,
    pbx_id: str,
    *,
    channel_limit: int = 200,
    registration_limit: int = 500,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    quality_issues: list[str] = []

    health_payload = ctx.call_tool_internal("freeswitch.health", {"pbx_id": pbx_id})[
        "data"
    ]
    channels_payload = ctx.call_tool_internal(
        "freeswitch.channels", {"pbx_id": pbx_id, "limit": channel_limit}
    )["data"]
    registrations_payload = ctx.call_tool_internal(
        "freeswitch.registrations", {"pbx_id": pbx_id, "limit": registration_limit}
    )["data"]

    channels = channels_payload.get("channels", [])
    if not isinstance(channels, list):
        channels = []
        quality_issues.append("Channel parser returned non-list payload.")
    elif not channels:
        quality_issues.append("Channel parser returned no structured channel rows.")

    reg_items = registrations_payload.get("items", [])
    if not isinstance(reg_items, list):
        reg_items = []
        quality_issues.append("Registration parser returned non-list payload.")
    elif not reg_items:
        quality_issues.append("Registration parser returned no structured registration rows.")

    summary_data = {
        "version": health_payload.get("freeswitch_version", "unknown"),
        "uptime_seconds": None,
        "channels_active": len(channels),
        "registrations": {
            "endpoints_registered": sum(
                1
                for item in reg_items
                if str(item.get("status", "")).strip().lower() == "reged"
            ),
            "endpoints_unreachable": sum(
                1
                for item in reg_items
                if str(item.get("status", "")).strip().lower() != "reged"
            ),
        },
        "trunks": {"up": None, "down": None},
        "notes": [],
    }
    quality_issues.append("Trunk counters unavailable without gateway inventory.")
    return summary_data, reg_items, channels, quality_issues


def list_targets(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    if args:
        raise ToolError(VALIDATION_ERROR, "telecom.list_targets takes no arguments")
    items = [{"id": t.id, "type": t.type, "host": t.host} for t in ctx.settings.targets]
    return {"type": "telecom", "id": "all"}, {"targets": items}


def summary(ctx: Any, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_str(args, "pbx_id")
    target = ctx.settings.get_target(pbx_id)

    if target.type == "asterisk":
        summary_data, _, _, quality_issues = _collect_asterisk_summary(ctx, pbx_id)
    else:
        summary_data, _, _, quality_issues = _collect_freeswitch_summary(ctx, pbx_id)

    data = dict(summary_data)
    data["data_quality"] = {
        "completeness": "partial" if quality_issues else "full",
        "issues": quality_issues,
        "sources": [f"{target.type}.health", f"{target.type}.channels"],
    }
    return {"type": target.type, "id": target.id}, data


def capture_snapshot(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_str(args, "pbx_id")
    target = ctx.settings.get_target(pbx_id)

    include = _dict_arg(args, "include")
    limits = _dict_arg(args, "limits")

    include_endpoints = bool(include.get("endpoints", True))
    include_trunks = bool(include.get("trunks", True))
    include_calls = bool(include.get("calls", True))
    include_regs = bool(include.get("registrations", True))

    max_items = limits.get("max_items", 200)
    if not isinstance(max_items, int) or max_items < 1:
        raise ToolError(VALIDATION_ERROR, "limits.max_items must be a positive integer")

    endpoints: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    summary_data: dict[str, Any]
    quality_issues: list[str]
    raw: dict[str, Any] = {
        "asterisk": {"ami": {}, "ari": {}},
        "freeswitch": {"esl": {}},
    }

    if target.type == "asterisk":
        summary_data, endpoint_items, channel_items, quality_issues = _collect_asterisk_summary(
            ctx,
            pbx_id,
            channel_limit=max_items,
            endpoint_limit=max(max_items, 500),
        )
        summary_data["data_quality"] = {
            "completeness": "partial" if quality_issues else "full",
            "issues": quality_issues,
            "sources": ["asterisk.health", "asterisk.active_channels", "asterisk.pjsip_show_endpoints"],
        }
        if include_endpoints:
            endpoints = endpoint_items[:max_items]
        if include_calls:
            calls = channel_items[:max_items]
    else:
        summary_data, registration_items, channel_items, quality_issues = _collect_freeswitch_summary(
            ctx,
            pbx_id,
            channel_limit=max_items,
            registration_limit=max(max_items, 500),
        )
        summary_data["data_quality"] = {
            "completeness": "partial" if quality_issues else "full",
            "issues": quality_issues,
            "sources": ["freeswitch.health", "freeswitch.channels", "freeswitch.registrations"],
        }
        if include_calls:
            calls = channel_items[:max_items]
        if include_regs:
            endpoints = registration_items[:max_items]
        if include_trunks or include_regs:
            raw["freeswitch"]["esl"] = ctx.call_tool_internal(
                "freeswitch.sofia_status", {"pbx_id": pbx_id}
            )["data"]

    data = {
        "snapshot_id": f"snap-{pbx_id}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
        "captured_at": datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "summary": summary_data,
        "endpoints": endpoints,
        "trunks": [],
        "calls": calls,
        "raw": raw,
    }
    return {"type": target.type, "id": target.id}, data
