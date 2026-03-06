"""Cross-platform telecom tools."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from ..errors import UPSTREAM_ERROR, VALIDATION_ERROR, ToolError


def _require_str(args: dict[str, Any], key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value:
        raise ToolError(VALIDATION_ERROR, f"Field '{key}' must be a non-empty string")
    return value


def _dict_arg(args: dict[str, Any], key: str) -> dict[str, Any]:
    if key not in args:
        return {}
    value = args.get(key)
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    raise ToolError(VALIDATION_ERROR, f"Field '{key}' must be an object")


def _bool_arg(args: dict[str, Any], key: str, default: bool = False) -> bool:
    if key not in args:
        return default
    value = args.get(key)
    if isinstance(value, bool):
        return value
    raise ToolError(VALIDATION_ERROR, f"Field '{key}' must be a boolean")


def _degraded_default_enabled() -> bool:
    return os.getenv("TELECOM_MCP_FAIL_ON_DEGRADED_DEFAULT", "").strip() == "1"


def _failed_tool_set(failed_sources: list[dict[str, Any]]) -> set[str]:
    failed: set[str] = set()
    for source in failed_sources:
        tool = source.get("tool")
        if isinstance(tool, str) and tool:
            failed.add(tool)
    return failed


def _strict_include_flag(include: dict[str, Any], key: str, *, default: bool = True) -> bool:
    if key not in include:
        return default
    value = include.get(key)
    if isinstance(value, bool):
        return value
    raise ToolError(VALIDATION_ERROR, f"Field 'include.{key}' must be a boolean")


def _validate_object_keys(obj: dict[str, Any], *, field_name: str, allowed: set[str]) -> None:
    unknown = sorted(set(obj) - allowed)
    if unknown:
        raise ToolError(
            VALIDATION_ERROR,
            f"Field '{field_name}' contains unsupported keys: {', '.join(unknown)}",
        )


def _quality_completeness(issues: list[str], failed_sources: list[dict[str, Any]]) -> str:
    return "partial" if issues or failed_sources else "full"


def _apply_summary_completeness_guard(
    summary_data: dict[str, Any],
    quality_issues: list[str],
) -> None:
    confidence = summary_data.get("confidence", {})
    if not isinstance(confidence, dict):
        return
    trunks_confidence = str(confidence.get("trunks", "")).strip().lower()
    trunks = summary_data.get("trunks", {})
    trunks_unavailable = isinstance(trunks, dict) and (
        trunks.get("up") is None or trunks.get("down") is None
    )
    if trunks_confidence == "low" and trunks_unavailable:
        quality_issues.append(
            "Trunk inventory is unavailable; summary completeness is partial."
        )


def _call_internal(
    ctx: Any,
    tool_name: str,
    tool_args: dict[str, Any],
    *,
    failed_sources: list[dict[str, Any]],
) -> dict[str, Any]:
    envelope = ctx.call_tool_internal(tool_name, tool_args)
    if "ok" not in envelope and isinstance(envelope.get("data"), dict):
        return envelope["data"]
    if envelope.get("ok") is True:
        data = envelope.get("data")
        if isinstance(data, dict):
            return data
        return {}
    error = envelope.get("error")
    failed_sources.append(
        {
            "tool": tool_name,
            "code": (
                str(error.get("code"))
                if isinstance(error, dict) and error.get("code")
                else UPSTREAM_ERROR
            ),
            "message": (
                str(error.get("message"))
                if isinstance(error, dict) and error.get("message")
                else f"Subcall failed: {tool_name}"
            ),
            "correlation_id": envelope.get("correlation_id"),
        }
    )
    return {}


def _collect_asterisk_summary(
    ctx: Any,
    pbx_id: str,
    *,
    channel_limit: int = 200,
    endpoint_limit: int = 500,
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[str],
    list[dict[str, Any]],
    dict[str, Any],
]:
    quality_issues: list[str] = []
    failed_sources: list[dict[str, Any]] = []

    health_payload = _call_internal(
        ctx,
        "asterisk.health",
        {"pbx_id": pbx_id},
        failed_sources=failed_sources,
    )
    channels_payload = _call_internal(
        ctx,
        "asterisk.active_channels",
        {"pbx_id": pbx_id, "limit": channel_limit},
        failed_sources=failed_sources,
    )
    endpoints_payload = _call_internal(
        ctx,
        "asterisk.pjsip_show_endpoints",
        {"pbx_id": pbx_id, "limit": endpoint_limit},
        failed_sources=failed_sources,
    )
    raw_evidence = {
        "health": health_payload,
        "active_channels": channels_payload,
        "pjsip_show_endpoints": endpoints_payload,
    }

    channels = channels_payload.get("channels", [])
    if not isinstance(channels, list):
        channels = []
        quality_issues.append("Channel inventory payload was not a list.")

    endpoint_items = endpoints_payload.get("items", [])
    if not isinstance(endpoint_items, list):
        endpoint_items = []
        quality_issues.append("Endpoint inventory payload was not a list.")
    endpoint_quality = endpoints_payload.get("data_quality", {})
    endpoint_completeness = "unknown"
    if isinstance(endpoint_quality, dict):
        endpoint_completeness = str(endpoint_quality.get("completeness", "unknown"))
    if endpoint_completeness != "full":
        quality_issues.append(
            "Endpoint inventory completeness is partial; registration counters may be approximate."
        )

    unknown_endpoints = sum(
        1
        for item in endpoint_items
        if str(item.get("endpoint", "")).strip().lower() in {"", "unknown"}
    )
    if unknown_endpoints:
        quality_issues.append(
            f"Endpoint parser emitted {unknown_endpoints} unknown endpoint rows."
        )

    failed_tools = _failed_tool_set(failed_sources)
    endpoints_failed = "asterisk.pjsip_show_endpoints" in failed_tools
    channels_failed = "asterisk.active_channels" in failed_tools
    registrations_confidence = (
        "low" if endpoints_failed or endpoint_completeness != "full" else "high"
    )
    channels_confidence = "low" if channels_failed else "high"
    if endpoints_failed:
        quality_issues.append(
            "Registration counters unavailable because endpoint collection failed."
        )
    if channels_failed:
        quality_issues.append(
            "Channel count unavailable because active channel collection failed."
        )

    summary_data = {
        "version": health_payload.get("asterisk_version", "unknown"),
        "uptime_seconds": None,
        "channels_active": None if channels_failed else len(channels),
        "registrations": {
            "endpoints_registered": (
                None
                if endpoints_failed
                else sum(
                    1 for item in endpoint_items if int(item.get("contacts", 0) or 0) > 0
                )
            ),
            "endpoints_unreachable": (
                None
                if endpoints_failed
                else sum(
                    1 for item in endpoint_items if int(item.get("contacts", 0) or 0) == 0
                )
            ),
        },
        "trunks": {"up": None, "down": None},
        "confidence": {
            "channels": channels_confidence,
            "registrations": registrations_confidence,
            "trunks": "low",
        },
        "notes": [],
    }
    summary_data["notes"].append("Trunk counters unavailable without trunk parsers.")
    return (
        summary_data,
        endpoint_items,
        channels,
        quality_issues,
        failed_sources,
        raw_evidence,
    )


def _collect_freeswitch_summary(
    ctx: Any,
    pbx_id: str,
    *,
    channel_limit: int = 200,
    registration_limit: int = 500,
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[str],
    list[dict[str, Any]],
    dict[str, Any],
]:
    quality_issues: list[str] = []
    failed_sources: list[dict[str, Any]] = []

    health_payload = _call_internal(
        ctx,
        "freeswitch.health",
        {"pbx_id": pbx_id},
        failed_sources=failed_sources,
    )
    channels_payload = _call_internal(
        ctx,
        "freeswitch.channels",
        {"pbx_id": pbx_id, "limit": channel_limit},
        failed_sources=failed_sources,
    )
    registrations_payload = _call_internal(
        ctx,
        "freeswitch.registrations",
        {"pbx_id": pbx_id, "limit": registration_limit},
        failed_sources=failed_sources,
    )
    raw_evidence = {
        "health": health_payload,
        "channels": channels_payload,
        "registrations": registrations_payload,
    }

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

    failed_tools = _failed_tool_set(failed_sources)
    channels_failed = "freeswitch.channels" in failed_tools
    registrations_failed = "freeswitch.registrations" in failed_tools
    channels_confidence = "low" if channels_failed else "high"
    registrations_confidence = "low" if registrations_failed else "high"
    if channels_failed:
        quality_issues.append(
            "Channel count unavailable because channel collection failed."
        )
    if registrations_failed:
        quality_issues.append(
            "Registration counters unavailable because registration collection failed."
        )

    summary_data = {
        "version": health_payload.get("freeswitch_version", "unknown"),
        "uptime_seconds": None,
        "channels_active": None if channels_failed else len(channels),
        "registrations": {
            "endpoints_registered": (
                None
                if registrations_failed
                else sum(
                    1
                    for item in reg_items
                    if str(item.get("status", "")).strip().lower() == "reged"
                )
            ),
            "endpoints_unreachable": (
                None
                if registrations_failed
                else sum(
                    1
                    for item in reg_items
                    if str(item.get("status", "")).strip().lower() != "reged"
                )
            ),
        },
        "trunks": {"up": None, "down": None},
        "confidence": {
            "channels": channels_confidence,
            "registrations": registrations_confidence,
            "trunks": "low",
        },
        "notes": [],
    }
    summary_data["notes"].append("Trunk counters unavailable without gateway inventory.")
    return (
        summary_data,
        reg_items,
        channels,
        quality_issues,
        failed_sources,
        raw_evidence,
    )


def list_targets(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    if args:
        raise ToolError(VALIDATION_ERROR, "telecom.list_targets takes no arguments")
    items = [{"id": t.id, "type": t.type, "host": t.host} for t in ctx.settings.targets]
    return {"type": "telecom", "id": "all"}, {"targets": items}


def summary(ctx: Any, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_str(args, "pbx_id")
    fail_on_degraded = _bool_arg(
        args, "fail_on_degraded", default=_degraded_default_enabled()
    )
    target = ctx.settings.get_target(pbx_id)

    if target.type == "asterisk":
        summary_data, _, _, quality_issues, failed_sources, _ = _collect_asterisk_summary(
            ctx, pbx_id
        )
    else:
        summary_data, _, _, quality_issues, failed_sources, _ = _collect_freeswitch_summary(
            ctx, pbx_id
        )

    data = dict(summary_data)
    if target.type == "asterisk":
        sources = [
            "asterisk.health",
            "asterisk.active_channels",
            "asterisk.pjsip_show_endpoints",
        ]
    else:
        sources = [
            "freeswitch.health",
            "freeswitch.channels",
            "freeswitch.registrations",
        ]
    degraded = bool(failed_sources)
    if degraded:
        quality_issues.append("One or more internal collectors failed.")
    _apply_summary_completeness_guard(data, quality_issues)
    warnings = list(quality_issues)
    if degraded:
        warnings.append("Summary is degraded; inspect data_quality.failed_sources.")
    completeness = _quality_completeness(quality_issues, failed_sources)
    data["data_quality"] = {
        "completeness": completeness,
        "issues": quality_issues,
        "degraded": degraded,
        "failed_sources": failed_sources,
        "sources": sources,
    }
    data["degraded"] = degraded
    data["warnings"] = warnings
    if fail_on_degraded and completeness != "full":
        raise ToolError(
            UPSTREAM_ERROR,
            "Summary quality not full and fail_on_degraded=true",
            {
                "completeness": completeness,
                "failed_sources": failed_sources,
                "issues": quality_issues,
            },
        )
    return {"type": target.type, "id": target.id}, data


def capture_snapshot(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_str(args, "pbx_id")
    fail_on_degraded = _bool_arg(
        args, "fail_on_degraded", default=_degraded_default_enabled()
    )
    target = ctx.settings.get_target(pbx_id)

    include = _dict_arg(args, "include")
    limits = _dict_arg(args, "limits")
    _validate_object_keys(
        include,
        field_name="include",
        allowed={"endpoints", "trunks", "calls", "registrations"},
    )
    _validate_object_keys(
        limits,
        field_name="limits",
        allowed={"max_items"},
    )

    include_endpoints = _strict_include_flag(include, "endpoints", default=True)
    include_trunks = _strict_include_flag(include, "trunks", default=True)
    include_calls = _strict_include_flag(include, "calls", default=True)
    include_regs = _strict_include_flag(include, "registrations", default=True)

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
        (
            summary_data,
            endpoint_items,
            channel_items,
            quality_issues,
            failed_sources,
            asterisk_raw,
        ) = _collect_asterisk_summary(
            ctx,
            pbx_id,
            channel_limit=max_items,
            endpoint_limit=max(max_items, 500),
        )
        degraded = bool(failed_sources)
        if degraded:
            quality_issues.append("One or more internal collectors failed.")
        _apply_summary_completeness_guard(summary_data, quality_issues)
        completeness = _quality_completeness(quality_issues, failed_sources)
        summary_data["data_quality"] = {
            "completeness": completeness,
            "issues": quality_issues,
            "degraded": degraded,
            "failed_sources": failed_sources,
            "sources": ["asterisk.health", "asterisk.active_channels", "asterisk.pjsip_show_endpoints"],
        }
        summary_data["degraded"] = degraded
        warnings = list(quality_issues)
        if degraded:
            warnings.append("Summary is degraded; inspect data_quality.failed_sources.")
        summary_data["warnings"] = warnings
        if include_endpoints:
            endpoints = endpoint_items[:max_items]
        if include_calls:
            calls = channel_items[:max_items]
        raw["asterisk"]["ami"] = {
            "pjsip_show_endpoints": {
                **asterisk_raw.get("pjsip_show_endpoints", {}),
                "items": endpoint_items[:max_items],
            }
        }
        raw["asterisk"]["ari"] = {
            "active_channels": {
                **asterisk_raw.get("active_channels", {}),
                "channels": channel_items[:max_items],
            }
        }
    else:
        (
            summary_data,
            registration_items,
            channel_items,
            quality_issues,
            failed_sources,
            freeswitch_raw,
        ) = _collect_freeswitch_summary(
            ctx,
            pbx_id,
            channel_limit=max_items,
            registration_limit=max(max_items, 500),
        )
        if include_calls:
            calls = channel_items[:max_items]
        if include_regs:
            endpoints = registration_items[:max_items]
        registrations_raw = freeswitch_raw.get("registrations", {})
        if not isinstance(registrations_raw, dict):
            registrations_raw = {}
        raw["freeswitch"]["esl"] = {
            **registrations_raw,
            "items": registration_items[:max_items],
            "channels": channel_items[:max_items],
        }
        if include_trunks or include_regs:
            sofia_payload = _call_internal(
                ctx,
                "freeswitch.sofia_status",
                {"pbx_id": pbx_id},
                failed_sources=failed_sources,
            )
            raw["freeswitch"]["esl"]["sofia_status"] = sofia_payload
        degraded = bool(failed_sources)
        if degraded:
            quality_issues.append("One or more internal collectors failed.")
        _apply_summary_completeness_guard(summary_data, quality_issues)
        completeness = _quality_completeness(quality_issues, failed_sources)
        summary_data["data_quality"] = {
            "completeness": completeness,
            "issues": quality_issues,
            "degraded": degraded,
            "failed_sources": failed_sources,
            "sources": ["freeswitch.health", "freeswitch.channels", "freeswitch.registrations"],
        }
        summary_data["degraded"] = degraded
        warnings = list(quality_issues)
        if degraded:
            warnings.append("Summary is degraded; inspect data_quality.failed_sources.")
        summary_data["warnings"] = warnings

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
    quality = summary_data.get("data_quality", {})
    completeness = (
        str(quality.get("completeness", "unknown")) if isinstance(quality, dict) else "unknown"
    )
    if fail_on_degraded and completeness != "full":
        failed_sources = (
            quality.get("failed_sources", []) if isinstance(quality, dict) else []
        )
        issues = quality.get("issues", []) if isinstance(quality, dict) else []
        raise ToolError(
            UPSTREAM_ERROR,
            "Snapshot quality not full and fail_on_degraded=true",
            {
                "completeness": completeness,
                "failed_sources": failed_sources,
                "issues": issues,
            },
        )
    return {"type": target.type, "id": target.id}, data
