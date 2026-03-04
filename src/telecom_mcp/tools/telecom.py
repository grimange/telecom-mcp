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
        payload = ctx.call_tool_internal("asterisk.health", {"pbx_id": pbx_id})["data"]
        version = payload.get("asterisk_version", "unknown")
    else:
        payload = ctx.call_tool_internal("freeswitch.health", {"pbx_id": pbx_id})[
            "data"
        ]
        version = payload.get("freeswitch_version", "unknown")

    data = {
        "version": version,
        "uptime_seconds": 0,
        "channels_active": 0,
        "registrations": {"endpoints_registered": 0, "endpoints_unreachable": 0},
        "trunks": {"up": 0, "down": 0},
        "notes": ["Summary uses health data until deeper parsers are configured."],
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

    summary_data = ctx.call_tool_internal("telecom.summary", {"pbx_id": pbx_id})["data"]
    endpoints: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    raw: dict[str, Any] = {
        "asterisk": {"ami": {}, "ari": {}},
        "freeswitch": {"esl": {}},
    }

    if target.type == "asterisk":
        if include_endpoints:
            endpoints_payload = ctx.call_tool_internal(
                "asterisk.pjsip_show_endpoints", {"pbx_id": pbx_id, "limit": max_items}
            )["data"]
            endpoints = endpoints_payload.get("items", [])
        if include_calls:
            calls_payload = ctx.call_tool_internal(
                "asterisk.active_channels", {"pbx_id": pbx_id, "limit": max_items}
            )["data"]
            calls = calls_payload.get("channels", [])
    else:
        if include_calls:
            calls_payload = ctx.call_tool_internal(
                "freeswitch.channels", {"pbx_id": pbx_id, "limit": max_items}
            )["data"]
            calls = calls_payload.get("channels", [])
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
        "endpoints": endpoints[:max_items],
        "trunks": [],
        "calls": calls[:max_items],
        "raw": raw,
    }
    return {"type": target.type, "id": target.id}, data
