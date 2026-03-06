"""Cross-platform telecom tools."""

from __future__ import annotations

import os
import re
import hashlib
import json
from datetime import UTC, datetime
import time
from typing import Any

from ..errors import NOT_ALLOWED, NOT_FOUND, UPSTREAM_ERROR, VALIDATION_ERROR, ToolError

_PROBE_DEST_RE = re.compile(r"^[A-Za-z0-9+*#_.:@/-]{2,64}$")
_PROBE_RATE_WINDOW_S = 60
_PROBE_RATE_HISTORY: dict[str, list[float]] = {}
_PROBE_REGISTRY: dict[str, list[dict[str, Any]]] = {}
_DEFAULT_CRITICAL_MODULES: dict[str, list[str]] = {
    "asterisk": ["res_pjsip.so", "chan_pjsip.so"],
    "freeswitch": ["mod_sofia", "mod_commands"],
}
_DEFAULT_RISKY_PATTERNS: tuple[str, ...] = (
    "app_system.so",
    "func_shell.so",
    "mod_shell_stream",
)


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


def _optional_str(args: dict[str, Any], key: str) -> str | None:
    if key not in args:
        return None
    value = args.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ToolError(VALIDATION_ERROR, f"Field '{key}' must be a string")
    cleaned = value.strip()
    return cleaned if cleaned else None


def _positive_int_arg(
    args: dict[str, Any], key: str, *, default: int, max_value: int
) -> int:
    value = args.get(key, default)
    if not isinstance(value, int) or value < 1:
        raise ToolError(VALIDATION_ERROR, f"Field '{key}' must be a positive integer")
    return min(value, max_value)


def _snapshot_arg(args: dict[str, Any], key: str) -> dict[str, Any]:
    value = args.get(key)
    if not isinstance(value, dict):
        raise ToolError(VALIDATION_ERROR, f"Field '{key}' must be an object snapshot payload")
    return value


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


def _normalized_response(
    *,
    pbx_id: str,
    platform: str,
    tool: str,
    summary: str,
    items: list[dict[str, Any]],
    counts: dict[str, Any],
    warnings: list[str] | None = None,
    truncated: bool = False,
    source_command: str | None = None,
) -> dict[str, Any]:
    payload = {
        "pbx_id": pbx_id,
        "platform": platform,
        "tool": tool,
        "summary": summary,
        "counts": counts,
        "items": items,
        "warnings": warnings or [],
        "truncated": truncated,
        "captured_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    if source_command:
        payload["source_command"] = source_command
    return payload


def _active_probes_enabled() -> bool:
    return os.getenv("TELECOM_MCP_ENABLE_ACTIVE_PROBES", "").strip() == "1"


def _assertion_params(args: dict[str, Any]) -> dict[str, Any]:
    params = _dict_arg(args, "params")
    return params


def _validate_probe_destination(destination: str) -> str:
    cleaned = destination.strip()
    if not cleaned:
        raise ToolError(VALIDATION_ERROR, "Field 'destination' must be non-empty")
    if not _PROBE_DEST_RE.match(cleaned):
        raise ToolError(
            VALIDATION_ERROR,
            "Field 'destination' contains unsupported characters",
            {"destination": destination, "pattern": _PROBE_DEST_RE.pattern},
        )
    return cleaned


def _probe_timeout_arg(args: dict[str, Any], *, default: int = 20) -> int:
    timeout = _positive_int_arg(args, "timeout_s", default=default, max_value=60)
    max_timeout = os.getenv("TELECOM_MCP_PROBE_MAX_TIMEOUT_S", "").strip()
    if max_timeout.isdigit():
        timeout = min(timeout, max(1, int(max_timeout)))
    return timeout


def _enforce_probe_rate_limit(pbx_id: str) -> None:
    limit_raw = os.getenv("TELECOM_MCP_PROBE_MAX_PER_MINUTE", "").strip()
    limit = int(limit_raw) if limit_raw.isdigit() else 5
    now = time.time()
    history = _PROBE_RATE_HISTORY.get(pbx_id, [])
    history = [ts for ts in history if now - ts <= _PROBE_RATE_WINDOW_S]
    if len(history) >= limit:
        raise ToolError(
            NOT_ALLOWED,
            "Probe rate limit exceeded for target",
            {
                "pbx_id": pbx_id,
                "max_per_minute": limit,
                "window_seconds": _PROBE_RATE_WINDOW_S,
            },
        )
    history.append(now)
    _PROBE_RATE_HISTORY[pbx_id] = history


def _register_probe(
    *,
    pbx_id: str,
    probe_id: str,
    destination: str,
    probe_type: str,
) -> None:
    entries = _PROBE_REGISTRY.get(pbx_id, [])
    entries.append(
        {
            "probe_id": probe_id,
            "destination": destination,
            "probe_type": probe_type,
            "issued_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }
    )
    _PROBE_REGISTRY[pbx_id] = entries[-200:]


def _module_policies(platform: str) -> tuple[list[str], list[str]]:
    critical_env = os.getenv("TELECOM_MCP_CRITICAL_MODULES", "").strip()
    risky_env = os.getenv("TELECOM_MCP_RISKY_MODULE_PATTERNS", "").strip()
    if critical_env:
        critical = [item.strip() for item in critical_env.split(",") if item.strip()]
    else:
        critical = list(_DEFAULT_CRITICAL_MODULES.get(platform, []))
    if risky_env:
        risky = [item.strip().lower() for item in risky_env.split(",") if item.strip()]
    else:
        risky = list(_DEFAULT_RISKY_PATTERNS)
    return critical, risky


def _module_names(modules_items: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for item in modules_items:
        if not isinstance(item, dict):
            continue
        module = item.get("module")
        if isinstance(module, str) and module.strip():
            names.append(module.strip())
    return names


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


def endpoints(ctx: Any, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_str(args, "pbx_id")
    target = ctx.settings.get_target(pbx_id)
    filter_obj = _dict_arg(args, "filter")
    _validate_object_keys(
        filter_obj,
        field_name="filter",
        allowed={"starts_with", "contains"},
    )
    limit = _positive_int_arg(args, "limit", default=200, max_value=2000)
    tool_name = (
        "asterisk.pjsip_show_endpoints"
        if target.type == "asterisk"
        else "freeswitch.registrations"
    )
    subcall_args: dict[str, Any] = {"pbx_id": pbx_id, "limit": limit}
    if filter_obj:
        subcall_args["filter"] = filter_obj
    payload = _call_internal(ctx, tool_name, subcall_args, failed_sources=[])
    items_key = "items"
    raw_items = payload.get(items_key, [])
    if not isinstance(raw_items, list):
        raw_items = []
    normalized_items: list[dict[str, Any]] = []
    for row in raw_items:
        if not isinstance(row, dict):
            continue
        if target.type == "asterisk":
            contacts = int(row.get("contacts", 0) or 0)
            normalized_items.append(
                {
                    "endpoint": str(row.get("endpoint", "unknown")),
                    "state": str(row.get("state", "Unknown")),
                    "status": "available" if contacts > 0 else "unavailable",
                    "contacts": contacts,
                }
            )
        else:
            status = str(row.get("status", "Unknown")).strip().lower()
            normalized_items.append(
                {
                    "endpoint": str(row.get("user", "")),
                    "state": str(row.get("status", "Unknown")),
                    "status": "available" if status == "reged" else "unavailable",
                    "contacts": 1 if status == "reged" else 0,
                }
            )
    available = sum(1 for item in normalized_items if item.get("status") == "available")
    unavailable = max(len(normalized_items) - available, 0)
    data = _normalized_response(
        pbx_id=pbx_id,
        platform=target.type,
        tool="telecom.endpoints",
        summary=f"{len(normalized_items)} endpoints found, {unavailable} unavailable",
        items=normalized_items[:limit],
        counts={
            "total": len(normalized_items),
            "available": available,
            "unavailable": unavailable,
        },
        warnings=[],
        truncated=len(normalized_items) > limit,
    )
    return {"type": target.type, "id": target.id}, data


def registrations(ctx: Any, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_str(args, "pbx_id")
    target = ctx.settings.get_target(pbx_id)
    limit = _positive_int_arg(args, "limit", default=200, max_value=2000)
    if target.type == "asterisk":
        tool_name = "asterisk.pjsip_show_endpoints"
        subcall_args = {"pbx_id": pbx_id, "limit": limit}
        payload = _call_internal(ctx, tool_name, subcall_args, failed_sources=[])
        rows = payload.get("items", [])
        if not isinstance(rows, list):
            rows = []
        items = [
            {
                "registration": str(row.get("endpoint", "unknown")),
                "state": "Registered" if int(row.get("contacts", 0) or 0) > 0 else "Unregistered",
                "contacts": int(row.get("contacts", 0) or 0),
            }
            for row in rows
            if isinstance(row, dict)
        ]
    else:
        tool_name = "freeswitch.registrations"
        payload = _call_internal(
            ctx, tool_name, {"pbx_id": pbx_id, "limit": limit}, failed_sources=[]
        )
        rows = payload.get("items", [])
        if not isinstance(rows, list):
            rows = []
        items = [
            {
                "registration": str(row.get("user", "")),
                "state": str(row.get("status", "Unknown")),
                "contact": str(row.get("contact", "")),
            }
            for row in rows
            if isinstance(row, dict)
        ]
    registered = sum(
        1
        for item in items
        if str(item.get("state", "")).strip().lower() in {"registered", "reged"}
    )
    unavailable = max(len(items) - registered, 0)
    data = _normalized_response(
        pbx_id=pbx_id,
        platform=target.type,
        tool="telecom.registrations",
        summary=f"{len(items)} registrations found, {unavailable} non-registered",
        items=items[:limit],
        counts={
            "total": len(items),
            "registered": registered,
            "unavailable": unavailable,
        },
        warnings=[],
        truncated=len(items) > limit,
    )
    return {"type": target.type, "id": target.id}, data


def channels(ctx: Any, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_str(args, "pbx_id")
    target = ctx.settings.get_target(pbx_id)
    limit = _positive_int_arg(args, "limit", default=200, max_value=2000)
    tool_name = "asterisk.active_channels" if target.type == "asterisk" else "freeswitch.channels"
    payload = _call_internal(ctx, tool_name, {"pbx_id": pbx_id, "limit": limit}, failed_sources=[])
    rows = payload.get("channels", [])
    if not isinstance(rows, list):
        rows = []
    items = [
        {
            "channel_id": str(
                row.get("channel_id") or row.get("uuid") or row.get("id") or "unknown"
            ),
            "name": str(row.get("name", "")),
            "state": str(row.get("state", "Unknown")),
            "caller": str(row.get("caller", "")),
            "callee": str(row.get("callee", "")),
        }
        for row in rows
        if isinstance(row, dict)
    ]
    data = _normalized_response(
        pbx_id=pbx_id,
        platform=target.type,
        tool="telecom.channels",
        summary=f"{len(items)} active channels",
        items=items[:limit],
        counts={"total": len(items), "active": len(items)},
        warnings=[],
        truncated=len(items) > limit,
    )
    return {"type": target.type, "id": target.id}, data


def calls(ctx: Any, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_str(args, "pbx_id")
    target = ctx.settings.get_target(pbx_id)
    limit = _positive_int_arg(args, "limit", default=200, max_value=2000)
    if target.type == "asterisk":
        payload = _call_internal(
            ctx, "asterisk.active_channels", {"pbx_id": pbx_id, "limit": limit}, failed_sources=[]
        )
        rows = payload.get("channels", [])
        if not isinstance(rows, list):
            rows = []
        items = [
            {
                "call_id": str(
                    row.get("bridge_id") or row.get("channel_id") or row.get("uuid") or "unknown"
                ),
                "state": str(row.get("state", "Unknown")),
                "legs": 1,
                "duration_s": int(row.get("duration_s", 0) or 0),
            }
            for row in rows
            if isinstance(row, dict)
        ]
    else:
        payload = _call_internal(
            ctx, "freeswitch.calls", {"pbx_id": pbx_id, "limit": limit}, failed_sources=[]
        )
        rows = payload.get("calls", [])
        if not isinstance(rows, list):
            rows = []
        items = [
            {
                "call_id": str(row.get("call_id", "")),
                "state": str(row.get("state", "Unknown")),
                "legs": int(row.get("legs", 1) or 1),
                "duration_s": int(row.get("duration_s", 0) or 0),
            }
            for row in rows
            if isinstance(row, dict)
        ]
    data = _normalized_response(
        pbx_id=pbx_id,
        platform=target.type,
        tool="telecom.calls",
        summary=f"{len(items)} active calls",
        items=items[:limit],
        counts={"total": len(items), "active": len(items)},
        warnings=[],
        truncated=len(items) > limit,
    )
    return {"type": target.type, "id": target.id}, data


def logs(ctx: Any, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_str(args, "pbx_id")
    target = ctx.settings.get_target(pbx_id)
    grep = _optional_str(args, "grep")
    level = _optional_str(args, "level")
    tail = _positive_int_arg(args, "tail", default=200, max_value=2000)
    delegated_tool = "asterisk.logs" if target.type == "asterisk" else "freeswitch.logs"
    delegated_args: dict[str, Any] = {"pbx_id": pbx_id, "tail": tail}
    if grep is not None:
        delegated_args["grep"] = grep
    if level is not None:
        delegated_args["level"] = level
    payload = _call_internal(ctx, delegated_tool, delegated_args, failed_sources=[])
    rows = payload.get("items", [])
    if not isinstance(rows, list):
        rows = []
    items = [row for row in rows if isinstance(row, dict)]
    counts = payload.get("counts")
    total = len(items)
    if isinstance(counts, dict) and isinstance(counts.get("total"), int):
        total = counts["total"]
    data = _normalized_response(
        pbx_id=pbx_id,
        platform=target.type,
        tool="telecom.logs",
        summary=f"{len(items)} log lines returned",
        items=items,
        counts={"total": total},
        warnings=payload.get("warnings") if isinstance(payload.get("warnings"), list) else [],
        truncated=bool(payload.get("truncated", False)),
        source_command=(
            str(payload.get("source_command"))
            if isinstance(payload.get("source_command"), str)
            else None
        ),
    )
    return {"type": target.type, "id": target.id}, data


def inventory(ctx: Any, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_str(args, "pbx_id")
    target = ctx.settings.get_target(pbx_id)
    failed_sources: list[dict[str, Any]] = []
    summary_payload = _call_internal(
        ctx, "telecom.summary", {"pbx_id": pbx_id}, failed_sources=failed_sources
    )
    version_tool = "asterisk.version" if target.type == "asterisk" else "freeswitch.version"
    modules_tool = "asterisk.modules" if target.type == "asterisk" else "freeswitch.modules"
    version_payload = _call_internal(
        ctx, version_tool, {"pbx_id": pbx_id}, failed_sources=failed_sources
    )
    modules_payload = _call_internal(
        ctx, modules_tool, {"pbx_id": pbx_id}, failed_sources=failed_sources
    )
    endpoint_tool = (
        "asterisk.pjsip_show_endpoints"
        if target.type == "asterisk"
        else "freeswitch.registrations"
    )
    endpoints_payload = _call_internal(
        ctx, endpoint_tool, {"pbx_id": pbx_id, "limit": 200}, failed_sources=failed_sources
    )
    raw_items = endpoints_payload.get("items", [])
    endpoint_items = raw_items if isinstance(raw_items, list) else []
    degraded = bool(failed_sources)
    if degraded:
        raise ToolError(
            UPSTREAM_ERROR,
            "Inventory collection degraded due to failed subcalls",
            {"failed_sources": failed_sources},
        )
    connectors = {
        "ami": bool(getattr(target, "ami", None)),
        "ari": bool(getattr(target, "ari", None)),
        "esl": bool(getattr(target, "esl", None)),
    }
    baseline = {
        "platform": target.type,
        "host": target.host,
        "version": version_payload.get("version", "unknown"),
        "connectors": connectors,
        "logs_configured": bool(getattr(target, "logs", None)),
        "modules_total": (
            modules_payload.get("counts", {}).get("total")
            if isinstance(modules_payload.get("counts"), dict)
            else None
        ),
    }
    modules_items = modules_payload.get("items", [])
    if not isinstance(modules_items, list):
        modules_items = []
    module_names = _module_names(modules_items)
    critical_expected, risky_patterns = _module_policies(target.type)
    module_names_lower = {name.lower() for name in module_names}
    critical_missing = [
        module
        for module in critical_expected
        if module.lower() not in module_names_lower
    ]
    risky_loaded = sorted(
        name
        for name in module_names
        if any(pattern in name.lower() for pattern in risky_patterns)
    )
    posture = {
        "version_posture": {
            "reported": version_payload.get("version", "unknown"),
            "status": (
                "known"
                if str(version_payload.get("version", "unknown")).strip().lower()
                != "unknown"
                else "unknown"
            ),
        },
        "config_posture": {
            "connectors_present": connectors,
            "logs_source_configured": bool(getattr(target, "logs", None)),
            "status": "ok" if any(connectors.values()) else "partial",
        },
        "module_posture": {
            "status": (
                "risk"
                if critical_missing
                else ("review" if risky_loaded else ("known" if modules_items else "partial"))
            ),
            "counts": {"total": len(modules_items)},
            "sample": modules_items[:20],
            "critical_expected": critical_expected,
            "critical_missing": critical_missing,
            "risky_loaded": risky_loaded,
            "notes": (
                []
                if modules_items
                else ["No module rows parsed from backend output."]
            ),
        },
    }
    data = {
        "pbx_id": pbx_id,
        "platform": target.type,
        "tool": "telecom.inventory",
        "summary": "Target inventory collected",
        "items": [
            {"key": "platform", "value": target.type},
            {"key": "host", "value": target.host},
            {"key": "version", "value": version_payload.get("version", "unknown")},
            {"key": "channels_active", "value": summary_payload.get("channels_active")},
            {
                "key": "registrations_registered",
                "value": summary_payload.get("registrations", {}).get("endpoints_registered")
                if isinstance(summary_payload.get("registrations"), dict)
                else None,
            },
            {"key": "endpoints_total", "value": len(endpoint_items)},
        ],
        "counts": {"total": 6},
        "warnings": [],
        "truncated": False,
        "captured_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "sources": ["telecom.summary", version_tool, modules_tool, endpoint_tool],
        "baseline": baseline,
        "posture": posture,
    }
    return {"type": target.type, "id": target.id}, data


def _inventory_map(data: dict[str, Any]) -> dict[str, Any]:
    baseline = data.get("baseline", {})
    if isinstance(baseline, dict) and baseline:
        return baseline
    items = data.get("items", [])
    if not isinstance(items, list):
        return {}
    mapped: dict[str, Any] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        if isinstance(key, str) and key:
            mapped[key] = item.get("value")
    return mapped


def compare_targets(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_a = _require_str(args, "pbx_a")
    pbx_b = _require_str(args, "pbx_b")
    if pbx_a == pbx_b:
        raise ToolError(VALIDATION_ERROR, "Fields 'pbx_a' and 'pbx_b' must differ")

    failed_sources: list[dict[str, Any]] = []
    inv_a = _call_internal(
        ctx, "telecom.inventory", {"pbx_id": pbx_a}, failed_sources=failed_sources
    )
    inv_b = _call_internal(
        ctx, "telecom.inventory", {"pbx_id": pbx_b}, failed_sources=failed_sources
    )
    map_a = _inventory_map(inv_a)
    map_b = _inventory_map(inv_b)
    posture_a = inv_a.get("posture", {}) if isinstance(inv_a.get("posture"), dict) else {}
    posture_b = inv_b.get("posture", {}) if isinstance(inv_b.get("posture"), dict) else {}

    keys = sorted(set(map_a) | set(map_b))
    differences: list[dict[str, Any]] = []
    for key in keys:
        left = map_a.get(key)
        right = map_b.get(key)
        if left != right:
            differences.append({"field": key, "pbx_a": left, "pbx_b": right})

    drift_categories: list[dict[str, Any]] = []
    module_a = posture_a.get("module_posture", {}) if isinstance(posture_a.get("module_posture"), dict) else {}
    module_b = posture_b.get("module_posture", {}) if isinstance(posture_b.get("module_posture"), dict) else {}
    missing_a = module_a.get("critical_missing", []) if isinstance(module_a.get("critical_missing"), list) else []
    missing_b = module_b.get("critical_missing", []) if isinstance(module_b.get("critical_missing"), list) else []
    risky_a = module_a.get("risky_loaded", []) if isinstance(module_a.get("risky_loaded"), list) else []
    risky_b = module_b.get("risky_loaded", []) if isinstance(module_b.get("risky_loaded"), list) else []
    if missing_a or missing_b:
        drift_categories.append(
            {
                "category": "critical_modules_missing",
                "pbx_a": sorted(str(x) for x in missing_a),
                "pbx_b": sorted(str(x) for x in missing_b),
            }
        )
    if risky_a or risky_b:
        drift_categories.append(
            {
                "category": "risky_modules_loaded",
                "pbx_a": sorted(str(x) for x in risky_a),
                "pbx_b": sorted(str(x) for x in risky_b),
            }
        )
    if map_a.get("connectors") != map_b.get("connectors"):
        drift_categories.append(
            {
                "category": "connector_coverage",
                "pbx_a": map_a.get("connectors"),
                "pbx_b": map_b.get("connectors"),
            }
        )
    if map_a.get("version") != map_b.get("version"):
        drift_categories.append(
            {
                "category": "version_mismatch",
                "pbx_a": map_a.get("version"),
                "pbx_b": map_b.get("version"),
            }
        )

    warnings: list[str] = []
    if failed_sources:
        warnings.append("Comparison is partial due to failed inventory subcalls.")
    data = {
        "pbx_id": f"{pbx_a}::{pbx_b}",
        "platform": "telecom",
        "tool": "telecom.compare_targets",
        "summary": (
            f"Compared {pbx_a} vs {pbx_b}; {len(differences)} differing baseline fields"
        ),
        "counts": {
            "fields_compared": len(keys),
            "differences": len(differences),
            "drift_categories": len(drift_categories),
        },
        "items": differences,
        "warnings": warnings,
        "truncated": False,
        "captured_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "targets": {
            "pbx_a": {"id": pbx_a, "platform": str(inv_a.get("platform", "unknown"))},
            "pbx_b": {"id": pbx_b, "platform": str(inv_b.get("platform", "unknown"))},
        },
        "failed_sources": failed_sources,
        "drift_categories": drift_categories,
    }
    return {"type": "telecom", "id": f"{pbx_a}::{pbx_b}"}, data


def run_smoke_test(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_str(args, "pbx_id")
    target = ctx.settings.get_target(pbx_id)
    failed_sources: list[dict[str, Any]] = []

    if target.type == "asterisk":
        checks = [
            ("asterisk.health", {"pbx_id": pbx_id}),
            ("asterisk.pjsip_show_endpoints", {"pbx_id": pbx_id, "limit": 20}),
            ("asterisk.active_channels", {"pbx_id": pbx_id, "limit": 20}),
        ]
    else:
        checks = [
            ("freeswitch.health", {"pbx_id": pbx_id}),
            ("freeswitch.registrations", {"pbx_id": pbx_id, "limit": 20}),
            ("freeswitch.channels", {"pbx_id": pbx_id, "limit": 20}),
        ]

    items: list[dict[str, Any]] = []
    passed = 0
    for tool_name, tool_args in checks:
        payload = _call_internal(ctx, tool_name, tool_args, failed_sources=failed_sources)
        ok = bool(payload)
        if ok:
            passed += 1
        items.append({"check": tool_name, "ok": ok})

    total = len(checks)
    warnings: list[str] = []
    if failed_sources:
        warnings.append("One or more smoke checks failed; inspect failed_sources.")
    return {"type": target.type, "id": target.id}, {
        "pbx_id": pbx_id,
        "platform": target.type,
        "tool": "telecom.run_smoke_test",
        "summary": f"{passed}/{total} smoke checks passed",
        "counts": {"total": total, "passed": passed, "failed": total - passed},
        "items": items,
        "warnings": warnings,
        "truncated": False,
        "captured_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "failed_sources": failed_sources,
        "passed": passed == total,
    }


def assert_state(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_str(args, "pbx_id")
    assertion = _require_str(args, "assertion")
    params = _assertion_params(args)
    target = ctx.settings.get_target(pbx_id)
    failed_sources: list[dict[str, Any]] = []

    assertion_key = assertion.strip().lower()
    allowed = {
        "min_registered",
        "max_active_calls",
        "target_type",
        "version_known",
    }
    if assertion_key not in allowed:
        raise ToolError(
            VALIDATION_ERROR,
            "Unsupported assertion",
            {"assertion": assertion, "allowed_assertions": sorted(allowed)},
        )

    summary_payload = _call_internal(
        ctx, "telecom.summary", {"pbx_id": pbx_id}, failed_sources=failed_sources
    )
    version_tool = "asterisk.version" if target.type == "asterisk" else "freeswitch.version"
    version_payload = _call_internal(
        ctx, version_tool, {"pbx_id": pbx_id}, failed_sources=failed_sources
    )

    ok = False
    actual: Any = None
    expected: Any = None
    message = ""
    if assertion_key == "min_registered":
        expected = params.get("value")
        if not isinstance(expected, int) or expected < 0:
            raise ToolError(
                VALIDATION_ERROR,
                "Assertion 'min_registered' requires params.value non-negative integer",
            )
        regs = summary_payload.get("registrations", {})
        actual = regs.get("endpoints_registered") if isinstance(regs, dict) else None
        ok = isinstance(actual, int) and actual >= expected
        message = f"registered endpoints {actual} >= {expected}"
    elif assertion_key == "max_active_calls":
        expected = params.get("value")
        if not isinstance(expected, int) or expected < 0:
            raise ToolError(
                VALIDATION_ERROR,
                "Assertion 'max_active_calls' requires params.value non-negative integer",
            )
        actual = summary_payload.get("channels_active")
        ok = isinstance(actual, int) and actual <= expected
        message = f"active channels {actual} <= {expected}"
    elif assertion_key == "target_type":
        expected = params.get("value")
        if not isinstance(expected, str) or not expected.strip():
            raise ToolError(
                VALIDATION_ERROR,
                "Assertion 'target_type' requires params.value non-empty string",
            )
        expected = expected.strip().lower()
        actual = target.type
        ok = actual == expected
        message = f"target type {actual} == {expected}"
    elif assertion_key == "version_known":
        expected = True
        actual = str(version_payload.get("version", "unknown")).strip().lower()
        ok = actual != "unknown"
        message = "version is known"

    warnings: list[str] = []
    if failed_sources:
        warnings.append("Assertion evaluated with degraded source collection.")
    return {"type": target.type, "id": target.id}, {
        "pbx_id": pbx_id,
        "platform": target.type,
        "tool": "telecom.assert_state",
        "summary": f"assertion '{assertion_key}' {'passed' if ok else 'failed'}",
        "counts": {"total": 1, "passed": 1 if ok else 0, "failed": 0 if ok else 1},
        "items": [
            {
                "assertion": assertion_key,
                "ok": ok,
                "expected": expected,
                "actual": actual,
                "message": message,
            }
        ],
        "warnings": warnings,
        "truncated": False,
        "captured_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "failed_sources": failed_sources,
        "passed": ok,
    }


def run_registration_probe(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_str(args, "pbx_id")
    destination = _validate_probe_destination(_require_str(args, "destination"))
    target = ctx.settings.get_target(pbx_id)
    if not _active_probes_enabled():
        raise ToolError(
            NOT_ALLOWED,
            "Active probes are disabled; set TELECOM_MCP_ENABLE_ACTIVE_PROBES=1",
            {"required_env": "TELECOM_MCP_ENABLE_ACTIVE_PROBES"},
        )
    delegated_tool = (
        "asterisk.originate_probe"
        if target.type == "asterisk"
        else "freeswitch.originate_probe"
    )
    _enforce_probe_rate_limit(pbx_id)
    probe_id = f"probe-{pbx_id}-{int(time.time())}"
    delegated_args = {
        "pbx_id": pbx_id,
        "destination": destination,
        "timeout_s": _probe_timeout_arg(args),
        "probe_id": probe_id,
    }
    payload = _call_internal(ctx, delegated_tool, delegated_args, failed_sources=[])
    effective_probe_id = str(payload.get("probe_id", probe_id)) if isinstance(payload, dict) else probe_id
    _register_probe(
        pbx_id=pbx_id,
        probe_id=effective_probe_id,
        destination=destination,
        probe_type="registration",
    )
    return {"type": target.type, "id": target.id}, {
        "pbx_id": pbx_id,
        "platform": target.type,
        "tool": "telecom.run_registration_probe",
        "summary": f"registration probe requested for {destination}",
        "counts": {"total": 1},
        "items": [payload] if isinstance(payload, dict) else [],
        "warnings": [],
        "truncated": False,
        "captured_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }


def run_trunk_probe(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_str(args, "pbx_id")
    destination = _validate_probe_destination(_require_str(args, "destination"))
    target = ctx.settings.get_target(pbx_id)
    if not _active_probes_enabled():
        raise ToolError(
            NOT_ALLOWED,
            "Active probes are disabled; set TELECOM_MCP_ENABLE_ACTIVE_PROBES=1",
            {"required_env": "TELECOM_MCP_ENABLE_ACTIVE_PROBES"},
        )
    delegated_tool = (
        "asterisk.originate_probe"
        if target.type == "asterisk"
        else "freeswitch.originate_probe"
    )
    _enforce_probe_rate_limit(pbx_id)
    probe_id = f"probe-{pbx_id}-{int(time.time())}"
    delegated_args = {
        "pbx_id": pbx_id,
        "destination": destination,
        "timeout_s": _probe_timeout_arg(args),
        "probe_id": probe_id,
    }
    payload = _call_internal(ctx, delegated_tool, delegated_args, failed_sources=[])
    effective_probe_id = str(payload.get("probe_id", probe_id)) if isinstance(payload, dict) else probe_id
    _register_probe(
        pbx_id=pbx_id,
        probe_id=effective_probe_id,
        destination=destination,
        probe_type="trunk",
    )
    return {"type": target.type, "id": target.id}, {
        "pbx_id": pbx_id,
        "platform": target.type,
        "tool": "telecom.run_trunk_probe",
        "summary": f"trunk probe requested for {destination}",
        "counts": {"total": 1},
        "items": [payload] if isinstance(payload, dict) else [],
        "warnings": [],
        "truncated": False,
        "captured_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }


def verify_cleanup(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_str(args, "pbx_id")
    probe_id = args.get("probe_id")
    if probe_id is not None and (not isinstance(probe_id, str) or not probe_id.strip()):
        raise ToolError(VALIDATION_ERROR, "Field 'probe_id' must be a non-empty string")
    probe_id_filter = probe_id.strip() if isinstance(probe_id, str) else None
    target = ctx.settings.get_target(pbx_id)
    failed_sources: list[dict[str, Any]] = []
    calls_payload = _call_internal(
        ctx, "telecom.calls", {"pbx_id": pbx_id, "limit": 500}, failed_sources=failed_sources
    )
    items = calls_payload.get("items", []) if isinstance(calls_payload, dict) else []
    if not isinstance(items, list):
        items = []
    expected = _PROBE_REGISTRY.get(pbx_id, [])
    if probe_id_filter:
        expected = [row for row in expected if str(row.get("probe_id")) == probe_id_filter]
    expected_ids = {str(row.get("probe_id")) for row in expected if row.get("probe_id")}
    leftovers = []
    for item in items:
        if not isinstance(item, dict):
            continue
        call_id = str(item.get("call_id", ""))
        related_probe_ids = item.get("probe_ids")
        probe_ids: set[str] = set()
        if isinstance(related_probe_ids, list):
            for value in related_probe_ids:
                if isinstance(value, str) and value:
                    probe_ids.add(value)
        for key in ("probe_id", "metadata_probe_id"):
            value = item.get(key)
            if isinstance(value, str) and value:
                probe_ids.add(value)
        if isinstance(call_id, str) and call_id.startswith("probe-"):
            probe_ids.add(call_id)
        if expected_ids:
            if probe_ids.intersection(expected_ids):
                leftovers.append(item)
        elif probe_ids:
            leftovers.append(item)
    clean = len(leftovers) == 0
    warnings: list[str] = []
    if failed_sources:
        warnings.append("Cleanup check is partial due to call collection failures.")
    return {"type": target.type, "id": target.id}, {
        "pbx_id": pbx_id,
        "platform": target.type,
        "tool": "telecom.verify_cleanup",
        "summary": (
            "No probe leftovers detected"
            if clean
            else f"{len(leftovers)} potential probe leftovers detected"
        ),
        "counts": {"total_calls": len(items), "probe_leftovers": len(leftovers)},
        "items": leftovers,
        "warnings": warnings,
        "truncated": False,
        "captured_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "failed_sources": failed_sources,
        "expected_probe_ids": sorted(expected_ids),
        "clean": clean,
    }


def _snapshot_item_key(item: dict[str, Any]) -> str:
    for key in ("endpoint", "channel_id", "call_id", "registration", "user", "uuid", "id"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return f"{key}:{value.strip()}"
    return ""


def _snapshot_item_map(snapshot: dict[str, Any], key: str) -> dict[str, dict[str, Any]]:
    raw_items = snapshot.get(key, [])
    if not isinstance(raw_items, list):
        return {}
    indexed: dict[str, dict[str, Any]] = {}
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        item_key = _snapshot_item_key(raw_item)
        if not item_key:
            continue
        indexed[item_key] = raw_item
    return indexed


def _summary_counts(snapshot: dict[str, Any]) -> dict[str, int]:
    summary = snapshot.get("summary", {})
    if not isinstance(summary, dict):
        return {}
    registrations = summary.get("registrations", {})
    if not isinstance(registrations, dict):
        registrations = {}
    counts: dict[str, int] = {}
    channels = summary.get("channels_active")
    if isinstance(channels, int):
        counts["channels_active"] = channels
    registered = registrations.get("endpoints_registered")
    if isinstance(registered, int):
        counts["endpoints_registered"] = registered
    unreachable = registrations.get("endpoints_unreachable")
    if isinstance(unreachable, int):
        counts["endpoints_unreachable"] = unreachable
    return counts


def diff_snapshots(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    del ctx
    snapshot_a = _snapshot_arg(args, "snapshot_a")
    snapshot_b = _snapshot_arg(args, "snapshot_b")
    snapshot_id_a = (
        str(snapshot_a.get("snapshot_id", "snapshot_a"))
        if snapshot_a.get("snapshot_id")
        else "snapshot_a"
    )
    snapshot_id_b = (
        str(snapshot_b.get("snapshot_id", "snapshot_b"))
        if snapshot_b.get("snapshot_id")
        else "snapshot_b"
    )
    pbx_id = "unknown"
    for candidate in (snapshot_b, snapshot_a):
        summary = candidate.get("summary", {})
        if isinstance(summary, dict):
            maybe_id = summary.get("pbx_id")
            if isinstance(maybe_id, str) and maybe_id.strip():
                pbx_id = maybe_id.strip()
                break

    section_keys = ("endpoints", "calls", "trunks")
    section_changes: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    total_changed = 0
    for section in section_keys:
        map_a = _snapshot_item_map(snapshot_a, section)
        map_b = _snapshot_item_map(snapshot_b, section)
        keys_a = set(map_a)
        keys_b = set(map_b)
        added = sorted(keys_b - keys_a)
        removed = sorted(keys_a - keys_b)
        changed = sorted(
            key for key in (keys_a & keys_b) if map_a.get(key) != map_b.get(key)
        )
        section_changes[section] = {
            "added": added,
            "removed": removed,
            "changed": changed,
            "counts": {
                "added": len(added),
                "removed": len(removed),
                "changed": len(changed),
            },
        }
        total_changed += len(added) + len(removed) + len(changed)
        if not keys_a and not keys_b:
            warnings.append(f"No comparable keyed rows found for section '{section}'.")

    counts_a = _summary_counts(snapshot_a)
    counts_b = _summary_counts(snapshot_b)
    summary_delta: dict[str, dict[str, int]] = {}
    for key in sorted(set(counts_a) | set(counts_b)):
        before = counts_a.get(key, 0)
        after = counts_b.get(key, 0)
        summary_delta[key] = {"before": before, "after": after, "delta": after - before}

    return {"type": "telecom", "id": pbx_id}, {
        "pbx_id": pbx_id,
        "platform": "telecom",
        "tool": "telecom.diff_snapshots",
        "summary": (
            f"Compared {snapshot_id_a} -> {snapshot_id_b}; "
            f"{total_changed} item-level changes detected"
        ),
        "counts": {"changed_total": total_changed, "sections": len(section_keys)},
        "items": [],
        "warnings": warnings,
        "truncated": False,
        "captured_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "snapshot_a": snapshot_id_a,
        "snapshot_b": snapshot_id_b,
        "sections": section_changes,
        "summary_delta": summary_delta,
    }


_PLAYBOOK_NAMES: tuple[str, ...] = (
    "sip_registration_triage",
    "outbound_call_failure_triage",
    "inbound_delivery_triage",
    "orphan_channel_triage",
    "pbx_drift_comparison",
)

_SMOKE_SUITE_NAMES: tuple[str, ...] = (
    "baseline_read_only_smoke",
    "registration_visibility_smoke",
    "call_state_visibility_smoke",
    "audit_baseline_smoke",
    "active_validation_smoke",
)


def _now_z() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _extract_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("items")
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]
    return []


def _find_channel_id(item: dict[str, Any]) -> str | None:
    for key in ("channel_id", "uuid", "id"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _item_matches_endpoint(item: dict[str, Any], endpoint: str) -> bool:
    needle = endpoint.strip().lower()
    for key in ("endpoint", "id", "username", "contact", "caller", "callee", "uri"):
        value = item.get(key)
        if isinstance(value, str) and needle in value.lower():
            return True
    return False


def _status_rank(status: str) -> int:
    return {"passed": 0, "warning": 1, "failed": 2}.get(status, 2)


def _rollup_status(statuses: list[str]) -> str:
    worst = "passed"
    for status in statuses:
        if _status_rank(status) > _status_rank(worst):
            worst = status
    return worst


def _build_playbook_result(
    *,
    playbook: str,
    pbx_id: str,
    platform: str,
    steps: list[dict[str, Any]],
    summary: str,
    evidence: dict[str, Any],
    warnings: list[str],
    failed_sources: list[dict[str, Any]],
    bucket: str,
) -> dict[str, Any]:
    status = _rollup_status([str(step.get("status", "failed")) for step in steps])
    if failed_sources and status == "passed":
        status = "warning"
    return {
        "playbook": playbook,
        "pbx_id": pbx_id,
        "platform": platform,
        "status": status,
        "bucket": bucket,
        "summary": summary,
        "steps": steps,
        "evidence": evidence,
        "warnings": warnings,
        "failed_sources": failed_sources,
        "captured_at": _now_z(),
    }


def _build_suite_result(
    *,
    suite: str,
    pbx_id: str,
    platform: str,
    checks: list[dict[str, Any]],
    warnings: list[str],
    failed_sources: list[dict[str, Any]],
) -> dict[str, Any]:
    status = _rollup_status([str(check.get("status", "failed")) for check in checks])
    passed = sum(1 for check in checks if check.get("status") == "passed")
    warning = sum(1 for check in checks if check.get("status") == "warning")
    failed = sum(1 for check in checks if check.get("status") == "failed")
    return {
        "suite": suite,
        "pbx_id": pbx_id,
        "platform": platform,
        "status": status,
        "summary": f"{passed}/{len(checks)} checks passed",
        "checks": checks,
        "counts": {"passed": passed, "warning": warning, "failed": failed},
        "warnings": warnings,
        "failed_sources": failed_sources,
        "captured_at": _now_z(),
    }


def _call_check(
    ctx: Any,
    *,
    check_id: str,
    tool: str,
    tool_args: dict[str, Any],
    failed_sources: list[dict[str, Any]],
    required: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = _call_internal(ctx, tool, tool_args, failed_sources=failed_sources)
    ok = bool(payload)
    if ok:
        return {
            "id": check_id,
            "tool": tool,
            "status": "passed",
            "summary": f"{tool} succeeded",
        }, payload
    status = "failed" if required else "warning"
    summary = f"{tool} unavailable"
    return {"id": check_id, "tool": tool, "status": status, "summary": summary}, {}


def _run_sip_registration_triage(
    ctx: Any, pbx_id: str, platform: str, args: dict[str, Any]
) -> dict[str, Any]:
    endpoint = _require_str(args, "endpoint")
    failed_sources: list[dict[str, Any]] = []
    warnings: list[str] = []
    steps: list[dict[str, Any]] = []

    health_tool = "asterisk.health" if platform == "asterisk" else "freeswitch.health"
    step, _health = _call_check(
        ctx,
        check_id="check-health",
        tool=health_tool,
        tool_args={"pbx_id": pbx_id},
        failed_sources=failed_sources,
        required=True,
    )
    steps.append(step)
    if step["status"] != "passed":
        return _build_playbook_result(
            playbook="sip_registration_triage",
            pbx_id=pbx_id,
            platform=platform,
            steps=steps,
            summary="PBX health check failed; cannot continue registration triage.",
            evidence={"endpoint": endpoint, "contacts": 0},
            warnings=warnings,
            failed_sources=failed_sources,
            bucket="pbx_unhealthy",
        )

    endpoint_step, endpoints_payload = _call_check(
        ctx,
        check_id="inspect-endpoint",
        tool="telecom.endpoints",
        tool_args={"pbx_id": pbx_id, "filter": {"contains": endpoint}, "limit": 200},
        failed_sources=failed_sources,
        required=True,
    )
    endpoints = _extract_items(endpoints_payload)
    matching_endpoints = [item for item in endpoints if _item_matches_endpoint(item, endpoint)]
    if not matching_endpoints and endpoint_step["status"] == "passed":
        endpoint_step["status"] = "warning"
        endpoint_step["summary"] = "Endpoint not present in endpoint inventory."
    steps.append(endpoint_step)

    regs_step, regs_payload = _call_check(
        ctx,
        check_id="inspect-registrations",
        tool="telecom.registrations",
        tool_args={"pbx_id": pbx_id, "limit": 500},
        failed_sources=failed_sources,
        required=False,
    )
    regs = _extract_items(regs_payload)
    matching_regs = [item for item in regs if _item_matches_endpoint(item, endpoint)]
    contacts = len(matching_regs)
    if regs_step["status"] == "passed":
        regs_step["summary"] = f"Found {contacts} registration/contact rows for endpoint."
        if contacts == 0:
            regs_step["status"] = "warning"
    steps.append(regs_step)

    logs_step, logs_payload = _call_check(
        ctx,
        check_id="inspect-logs",
        tool="telecom.logs",
        tool_args={"pbx_id": pbx_id, "grep": endpoint, "tail": 120},
        failed_sources=failed_sources,
        required=False,
    )
    logs_items = _extract_items(logs_payload)
    if logs_step["status"] == "passed":
        logs_step["summary"] = f"Collected {len(logs_items)} matching log lines."
    steps.append(logs_step)

    endpoint_present = bool(matching_endpoints)
    unavailable = False
    for item in matching_endpoints:
        state = str(item.get("state", "")).strip().lower()
        status = str(item.get("status", "")).strip().lower()
        if "unavail" in state or "unavail" in status:
            unavailable = True
            break

    bucket = "insufficient_evidence"
    if not endpoint_present:
        bucket = "endpoint_missing"
    elif contacts == 0:
        bucket = "endpoint_present_but_no_contacts"
    elif unavailable:
        bucket = "endpoint_present_unavailable"
    else:
        bucket = "endpoint_present_with_active_contacts"
    if failed_sources:
        warnings.append("One or more subqueries failed; triage result is partial.")

    return _build_playbook_result(
        playbook="sip_registration_triage",
        pbx_id=pbx_id,
        platform=platform,
        steps=steps,
        summary=f"SIP registration triage bucket: {bucket.replace('_', ' ')}.",
        evidence={
            "endpoint": endpoint,
            "endpoint_present": endpoint_present,
            "contacts": contacts,
            "log_hits": len(logs_items),
        },
        warnings=warnings,
        failed_sources=failed_sources,
        bucket=bucket,
    )


def _run_outbound_call_failure_triage(
    ctx: Any, pbx_id: str, platform: str, args: dict[str, Any]
) -> dict[str, Any]:
    failed_sources: list[dict[str, Any]] = []
    warnings: list[str] = []
    steps: list[dict[str, Any]] = []

    endpoint = _optional_str(args, "endpoint")
    destination_hint = _optional_str(args, "destination_hint")
    log_hint = destination_hint or endpoint or "hangup"

    health_tool = "asterisk.health" if platform == "asterisk" else "freeswitch.health"
    step, _health = _call_check(
        ctx,
        check_id="check-health",
        tool=health_tool,
        tool_args={"pbx_id": pbx_id},
        failed_sources=failed_sources,
        required=True,
    )
    steps.append(step)

    calls_step, calls_payload = _call_check(
        ctx,
        check_id="inspect-calls",
        tool="telecom.calls",
        tool_args={"pbx_id": pbx_id, "limit": 200},
        failed_sources=failed_sources,
        required=False,
    )
    calls = _extract_items(calls_payload)
    if calls_step["status"] == "passed":
        calls_step["summary"] = f"Observed {len(calls)} calls."
    steps.append(calls_step)

    channels_step, channels_payload = _call_check(
        ctx,
        check_id="inspect-channels",
        tool="telecom.channels",
        tool_args={"pbx_id": pbx_id, "limit": 200},
        failed_sources=failed_sources,
        required=False,
    )
    channels = _extract_items(channels_payload)
    if channels_step["status"] == "passed":
        channels_step["summary"] = f"Observed {len(channels)} channels."
    steps.append(channels_step)

    bridge_count = 0
    if platform == "asterisk":
        bridges_step, bridges_payload = _call_check(
            ctx,
            check_id="inspect-bridges",
            tool="asterisk.bridges",
            tool_args={"pbx_id": pbx_id, "limit": 200},
            failed_sources=failed_sources,
            required=False,
        )
        bridges = _extract_items(bridges_payload)
        bridge_count = len(bridges)
        if bridges_step["status"] == "passed":
            bridges_step["summary"] = f"Observed {bridge_count} bridges."
        steps.append(bridges_step)

    detail_args: dict[str, Any] | None = None
    if channels:
        channel_id = _find_channel_id(channels[0])
        if channel_id:
            if platform == "asterisk":
                detail_args = {"pbx_id": pbx_id, "channel_id": channel_id}
                detail_tool = "asterisk.channel_details"
            else:
                detail_args = {"pbx_id": pbx_id, "uuid": channel_id}
                detail_tool = "freeswitch.channel_details"
            detail_step, _details = _call_check(
                ctx,
                check_id="inspect-channel-details",
                tool=detail_tool,
                tool_args=detail_args,
                failed_sources=failed_sources,
                required=False,
            )
            steps.append(detail_step)

    logs_step, logs_payload = _call_check(
        ctx,
        check_id="inspect-logs",
        tool="telecom.logs",
        tool_args={"pbx_id": pbx_id, "grep": log_hint, "tail": 150},
        failed_sources=failed_sources,
        required=False,
    )
    logs_items = _extract_items(logs_payload)
    if logs_step["status"] == "passed":
        logs_step["summary"] = f"Collected {len(logs_items)} matching log lines."
    steps.append(logs_step)

    bucket = "insufficient_evidence"
    if not calls and not channels:
        bucket = "no_call_attempt_observed"
    elif calls and bridge_count == 0 and platform == "asterisk":
        bucket = "bridge_never_formed"
    elif calls and not logs_items:
        bucket = "call_attempt_created_but_not_answered"
    elif logs_items:
        bucket = "hangup_cause_indicated_in_logs"
    if failed_sources:
        warnings.append("One or more subqueries failed; triage result is partial.")

    return _build_playbook_result(
        playbook="outbound_call_failure_triage",
        pbx_id=pbx_id,
        platform=platform,
        steps=steps,
        summary=f"Outbound call triage bucket: {bucket.replace('_', ' ')}.",
        evidence={
            "endpoint": endpoint,
            "destination_hint": destination_hint,
            "calls_observed": len(calls),
            "channels_observed": len(channels),
            "bridges_observed": bridge_count,
            "log_hits": len(logs_items),
        },
        warnings=warnings,
        failed_sources=failed_sources,
        bucket=bucket,
    )


def _run_inbound_delivery_triage(
    ctx: Any, pbx_id: str, platform: str, args: dict[str, Any]
) -> dict[str, Any]:
    failed_sources: list[dict[str, Any]] = []
    warnings: list[str] = []
    steps: list[dict[str, Any]] = []

    target_hint = _optional_str(args, "target") or _optional_str(args, "did") or ""

    health_tool = "asterisk.health" if platform == "asterisk" else "freeswitch.health"
    step, _health = _call_check(
        ctx,
        check_id="check-health",
        tool=health_tool,
        tool_args={"pbx_id": pbx_id},
        failed_sources=failed_sources,
        required=True,
    )
    steps.append(step)

    channels_step, channels_payload = _call_check(
        ctx,
        check_id="inspect-channels",
        tool="telecom.channels",
        tool_args={"pbx_id": pbx_id, "limit": 200},
        failed_sources=failed_sources,
        required=False,
    )
    channels = _extract_items(channels_payload)
    if channels_step["status"] == "passed":
        channels_step["summary"] = f"Observed {len(channels)} channels."
    steps.append(channels_step)

    bridge_count = 0
    if platform == "asterisk":
        bridges_step, bridges_payload = _call_check(
            ctx,
            check_id="inspect-bridges",
            tool="asterisk.bridges",
            tool_args={"pbx_id": pbx_id, "limit": 200},
            failed_sources=failed_sources,
            required=False,
        )
        bridges = _extract_items(bridges_payload)
        bridge_count = len(bridges)
        if bridges_step["status"] == "passed":
            bridges_step["summary"] = f"Observed {bridge_count} bridges."
        steps.append(bridges_step)

    regs_step, regs_payload = _call_check(
        ctx,
        check_id="inspect-delivery-registrations",
        tool="telecom.registrations",
        tool_args={"pbx_id": pbx_id, "limit": 500},
        failed_sources=failed_sources,
        required=False,
    )
    regs = _extract_items(regs_payload)
    if regs_step["status"] == "passed":
        regs_step["summary"] = f"Observed {len(regs)} registration rows."
    steps.append(regs_step)

    logs_step, logs_payload = _call_check(
        ctx,
        check_id="inspect-logs",
        tool="telecom.logs",
        tool_args={"pbx_id": pbx_id, "grep": target_hint or "inbound", "tail": 150},
        failed_sources=failed_sources,
        required=False,
    )
    logs_items = _extract_items(logs_payload)
    if logs_step["status"] == "passed":
        logs_step["summary"] = f"Collected {len(logs_items)} matching log lines."
    steps.append(logs_step)

    bucket = "insufficient_evidence"
    if not channels:
        bucket = "no_inbound_activity_observed"
    elif channels and not regs:
        bucket = "endpoint_unavailable"
    elif channels and bridge_count == 0 and platform == "asterisk":
        bucket = "queue_bridge_stage_suspected"
    else:
        bucket = "inbound_reached_pbx_but_not_ringing_endpoint"
    if failed_sources:
        warnings.append("One or more subqueries failed; triage result is partial.")

    return _build_playbook_result(
        playbook="inbound_delivery_triage",
        pbx_id=pbx_id,
        platform=platform,
        steps=steps,
        summary=f"Inbound delivery triage bucket: {bucket.replace('_', ' ')}.",
        evidence={
            "target_hint": target_hint,
            "channels_observed": len(channels),
            "bridges_observed": bridge_count,
            "registrations_observed": len(regs),
            "log_hits": len(logs_items),
        },
        warnings=warnings,
        failed_sources=failed_sources,
        bucket=bucket,
    )


def _duration_seconds(item: dict[str, Any]) -> int | None:
    for key in ("duration_s", "age_s", "uptime_s"):
        value = item.get(key)
        if isinstance(value, int):
            return value
    return None


def _run_orphan_channel_triage(
    ctx: Any, pbx_id: str, platform: str, args: dict[str, Any]
) -> dict[str, Any]:
    failed_sources: list[dict[str, Any]] = []
    warnings: list[str] = []
    steps: list[dict[str, Any]] = []
    threshold = _positive_int_arg(args, "age_threshold_s", default=600, max_value=86400)

    channels_step, channels_payload = _call_check(
        ctx,
        check_id="collect-channels",
        tool="telecom.channels",
        tool_args={"pbx_id": pbx_id, "limit": 500},
        failed_sources=failed_sources,
        required=True,
    )
    channels = _extract_items(channels_payload)
    steps.append(channels_step)

    bridge_ids: set[str] = set()
    if platform == "asterisk":
        bridges_step, bridges_payload = _call_check(
            ctx,
            check_id="collect-bridges",
            tool="asterisk.bridges",
            tool_args={"pbx_id": pbx_id, "limit": 500},
            failed_sources=failed_sources,
            required=False,
        )
        bridges = _extract_items(bridges_payload)
        for bridge in bridges:
            bridge_id = bridge.get("bridge_id") or bridge.get("id")
            if isinstance(bridge_id, str) and bridge_id.strip():
                bridge_ids.add(bridge_id.strip())
        steps.append(bridges_step)

    stale_channels = []
    orphan_channels = []
    for channel in channels:
        duration_s = _duration_seconds(channel)
        channel_id = _find_channel_id(channel) or "unknown"
        if isinstance(duration_s, int) and duration_s >= threshold:
            stale_channels.append(channel_id)
        bridge_ref = channel.get("bridge_id")
        if platform == "asterisk" and isinstance(bridge_ref, str) and bridge_ref and bridge_ref not in bridge_ids:
            orphan_channels.append(channel_id)

    classify_step = {
        "id": "classify",
        "tool": "telecom.orphan_heuristics",
        "status": "passed",
        "summary": "No anomalies detected.",
    }
    bucket = "no_anomaly_detected"
    if orphan_channels:
        classify_step["status"] = "warning"
        classify_step["summary"] = f"Detected {len(orphan_channels)} potential orphan channels."
        bucket = "orphan_channel_suspected"
    elif stale_channels:
        classify_step["status"] = "warning"
        classify_step["summary"] = f"Detected {len(stale_channels)} stale channels."
        bucket = "cleanup_lag_suspected"
    elif failed_sources:
        classify_step["status"] = "warning"
        classify_step["summary"] = "PBX query incomplete due to failed subqueries."
        bucket = "pbx_query_incomplete"
    steps.append(classify_step)

    if failed_sources:
        warnings.append("One or more subqueries failed; triage result is partial.")

    return _build_playbook_result(
        playbook="orphan_channel_triage",
        pbx_id=pbx_id,
        platform=platform,
        steps=steps,
        summary=f"Orphan channel triage bucket: {bucket.replace('_', ' ')}.",
        evidence={
            "threshold_seconds": threshold,
            "channels_observed": len(channels),
            "stale_channels": stale_channels[:50],
            "orphan_channels": orphan_channels[:50],
        },
        warnings=warnings,
        failed_sources=failed_sources,
        bucket=bucket,
    )


def _run_pbx_drift_comparison(ctx: Any, args: dict[str, Any]) -> dict[str, Any]:
    pbx_a = _require_str(args, "pbx_a")
    pbx_b = _require_str(args, "pbx_b")
    failed_sources: list[dict[str, Any]] = []
    warnings: list[str] = []

    compare_payload = _call_internal(
        ctx,
        "telecom.compare_targets",
        {"pbx_a": pbx_a, "pbx_b": pbx_b},
        failed_sources=failed_sources,
    )
    differences = _extract_items(compare_payload)
    drift_categories = compare_payload.get("drift_categories", [])
    if not isinstance(drift_categories, list):
        drift_categories = []
    risky = any(
        isinstance(item, dict)
        and str(item.get("category", "")).strip().lower()
        in {"critical_modules_missing", "risky_modules_loaded", "version_mismatch"}
        for item in drift_categories
    )
    bucket = "no_meaningful_drift"
    if risky:
        bucket = "risky_drift"
    elif differences:
        bucket = "informational_drift"
    if failed_sources:
        warnings.append("Comparison is partial due to failed inventory subqueries.")
        bucket = "comparison_incomplete"

    steps = [
        {
            "id": "compare-targets",
            "tool": "telecom.compare_targets",
            "status": "warning" if failed_sources else "passed",
            "summary": compare_payload.get("summary", "Target comparison completed."),
        }
    ]
    return {
        "playbook": "pbx_drift_comparison",
        "pbx_id": f"{pbx_a}::{pbx_b}",
        "platform": "telecom",
        "status": _rollup_status([str(steps[0]["status"])]),
        "bucket": bucket,
        "summary": f"PBX drift comparison bucket: {bucket.replace('_', ' ')}.",
        "steps": steps,
        "evidence": {
            "pbx_a": pbx_a,
            "pbx_b": pbx_b,
            "differences": len(differences),
            "drift_categories": drift_categories,
        },
        "warnings": warnings,
        "failed_sources": failed_sources,
        "captured_at": _now_z(),
    }


def run_playbook(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    name = _require_str(args, "name").strip().lower()
    if name not in _PLAYBOOK_NAMES:
        raise ToolError(
            VALIDATION_ERROR,
            "Unsupported playbook",
            {"name": name, "allowed_playbooks": list(_PLAYBOOK_NAMES)},
        )

    if name == "pbx_drift_comparison":
        data = _run_pbx_drift_comparison(ctx, args)
        return {"type": "telecom", "id": str(data["pbx_id"])}, data

    pbx_id = _require_str(args, "pbx_id")
    target = ctx.settings.get_target(pbx_id)
    builders = {
        "sip_registration_triage": _run_sip_registration_triage,
        "outbound_call_failure_triage": _run_outbound_call_failure_triage,
        "inbound_delivery_triage": _run_inbound_delivery_triage,
        "orphan_channel_triage": _run_orphan_channel_triage,
    }
    builder = builders.get(name)
    if builder is None:
        raise ToolError(VALIDATION_ERROR, "Playbook implementation is not available", {"name": name})
    data = builder(ctx, pbx_id, target.type, args)
    return {"type": target.type, "id": target.id}, data


def _suite_baseline_read_only_smoke(
    ctx: Any, pbx_id: str, platform: str
) -> dict[str, Any]:
    failed_sources: list[dict[str, Any]] = []
    warnings: list[str] = []
    checks: list[dict[str, Any]] = []

    health_tool = "asterisk.health" if platform == "asterisk" else "freeswitch.health"
    checks.append(
        _call_check(
            ctx,
            check_id="health",
            tool=health_tool,
            tool_args={"pbx_id": pbx_id},
            failed_sources=failed_sources,
            required=True,
        )[0]
    )
    checks.append(
        _call_check(
            ctx,
            check_id="summary",
            tool="telecom.summary",
            tool_args={"pbx_id": pbx_id},
            failed_sources=failed_sources,
            required=True,
        )[0]
    )
    checks.append(
        _call_check(
            ctx,
            check_id="endpoints",
            tool="telecom.endpoints",
            tool_args={"pbx_id": pbx_id, "limit": 50},
            failed_sources=failed_sources,
            required=True,
        )[0]
    )
    checks.append(
        _call_check(
            ctx,
            check_id="registrations",
            tool="telecom.registrations",
            tool_args={"pbx_id": pbx_id, "limit": 50},
            failed_sources=failed_sources,
            required=True,
        )[0]
    )
    checks.append(
        _call_check(
            ctx,
            check_id="channels",
            tool="telecom.channels",
            tool_args={"pbx_id": pbx_id, "limit": 50},
            failed_sources=failed_sources,
            required=True,
        )[0]
    )
    checks.append(
        _call_check(
            ctx,
            check_id="logs",
            tool="telecom.logs",
            tool_args={"pbx_id": pbx_id, "tail": 40},
            failed_sources=failed_sources,
            required=False,
        )[0]
    )
    checks.append(
        _call_check(
            ctx,
            check_id="inventory",
            tool="telecom.inventory",
            tool_args={"pbx_id": pbx_id},
            failed_sources=failed_sources,
            required=False,
        )[0]
    )
    if failed_sources:
        warnings.append("One or more smoke checks failed or degraded.")
    return _build_suite_result(
        suite="baseline_read_only_smoke",
        pbx_id=pbx_id,
        platform=platform,
        checks=checks,
        warnings=warnings,
        failed_sources=failed_sources,
    )


def _suite_registration_visibility_smoke(
    ctx: Any, pbx_id: str, platform: str
) -> dict[str, Any]:
    failed_sources: list[dict[str, Any]] = []
    warnings: list[str] = []
    checks: list[dict[str, Any]] = []

    endpoint_check, endpoint_payload = _call_check(
        ctx,
        check_id="endpoints-load",
        tool="telecom.endpoints",
        tool_args={"pbx_id": pbx_id, "limit": 200},
        failed_sources=failed_sources,
        required=True,
    )
    registration_check, registration_payload = _call_check(
        ctx,
        check_id="registrations-load",
        tool="telecom.registrations",
        tool_args={"pbx_id": pbx_id, "limit": 500},
        failed_sources=failed_sources,
        required=True,
    )
    checks.extend([endpoint_check, registration_check])

    reconcile = {
        "id": "counts-reconcile",
        "tool": "telecom.registration_reconcile",
        "status": "passed",
        "summary": "Endpoint and registration counts are coherent.",
    }
    endpoints = _extract_items(endpoint_payload)
    regs = _extract_items(registration_payload)
    if endpoint_check["status"] != "passed" or registration_check["status"] != "passed":
        reconcile["status"] = "warning"
        reconcile["summary"] = "Count reconciliation skipped due to missing inputs."
    elif len(regs) > max(1, len(endpoints) * 4):
        reconcile["status"] = "warning"
        reconcile["summary"] = (
            f"Registrations ({len(regs)}) exceed expected range for endpoints ({len(endpoints)})."
        )
    checks.append(reconcile)

    if failed_sources:
        warnings.append("Registration visibility smoke executed with partial data.")
    return _build_suite_result(
        suite="registration_visibility_smoke",
        pbx_id=pbx_id,
        platform=platform,
        checks=checks,
        warnings=warnings,
        failed_sources=failed_sources,
    )


def _suite_call_state_visibility_smoke(
    ctx: Any, pbx_id: str, platform: str
) -> dict[str, Any]:
    failed_sources: list[dict[str, Any]] = []
    warnings: list[str] = []
    checks: list[dict[str, Any]] = []

    channels_check, channels_payload = _call_check(
        ctx,
        check_id="channels-query",
        tool="telecom.channels",
        tool_args={"pbx_id": pbx_id, "limit": 200},
        failed_sources=failed_sources,
        required=True,
    )
    checks.append(channels_check)

    if platform == "asterisk":
        bridges_check, bridges_payload = _call_check(
            ctx,
            check_id="bridges-query",
            tool="asterisk.bridges",
            tool_args={"pbx_id": pbx_id, "limit": 200},
            failed_sources=failed_sources,
            required=False,
        )
        checks.append(bridges_check)
        _ = bridges_payload
    else:
        calls_check, _calls_payload = _call_check(
            ctx,
            check_id="calls-query",
            tool="freeswitch.calls",
            tool_args={"pbx_id": pbx_id, "limit": 200},
            failed_sources=failed_sources,
            required=False,
        )
        checks.append(calls_check)

    detail_check = {
        "id": "detail-query",
        "tool": "channel-details",
        "status": "passed",
        "summary": "No channel available; detail query skipped gracefully.",
    }
    channels = _extract_items(channels_payload)
    if channels:
        channel_id = _find_channel_id(channels[0])
        if channel_id:
            if platform == "asterisk":
                detail_tool = "asterisk.channel_details"
                detail_args = {"pbx_id": pbx_id, "channel_id": channel_id}
            else:
                detail_tool = "freeswitch.channel_details"
                detail_args = {"pbx_id": pbx_id, "uuid": channel_id}
            detail_check, _ = _call_check(
                ctx,
                check_id="detail-query",
                tool=detail_tool,
                tool_args=detail_args,
                failed_sources=failed_sources,
                required=False,
            )
    checks.append(detail_check)
    if failed_sources:
        warnings.append("Call state visibility smoke executed with partial data.")
    return _build_suite_result(
        suite="call_state_visibility_smoke",
        pbx_id=pbx_id,
        platform=platform,
        checks=checks,
        warnings=warnings,
        failed_sources=failed_sources,
    )


def _suite_audit_baseline_smoke(
    ctx: Any, pbx_id: str, platform: str, params: dict[str, Any]
) -> dict[str, Any]:
    failed_sources: list[dict[str, Any]] = []
    warnings: list[str] = []
    checks: list[dict[str, Any]] = []

    version_tool = "asterisk.version" if platform == "asterisk" else "freeswitch.version"
    modules_tool = "asterisk.modules" if platform == "asterisk" else "freeswitch.modules"
    checks.append(
        _call_check(
            ctx,
            check_id="version",
            tool=version_tool,
            tool_args={"pbx_id": pbx_id},
            failed_sources=failed_sources,
            required=True,
        )[0]
    )
    checks.append(
        _call_check(
            ctx,
            check_id="modules",
            tool=modules_tool,
            tool_args={"pbx_id": pbx_id},
            failed_sources=failed_sources,
            required=False,
        )[0]
    )
    checks.append(
        _call_check(
            ctx,
            check_id="inventory",
            tool="telecom.inventory",
            tool_args={"pbx_id": pbx_id},
            failed_sources=failed_sources,
            required=True,
        )[0]
    )

    compare_with = params.get("compare_with")
    compare_check = {
        "id": "compare-helper",
        "tool": "telecom.compare_targets",
        "status": "warning",
        "summary": "No compare_with target provided; drift helper skipped.",
    }
    if isinstance(compare_with, str) and compare_with.strip():
        compare_payload = _call_internal(
            ctx,
            "telecom.compare_targets",
            {"pbx_a": pbx_id, "pbx_b": compare_with.strip()},
            failed_sources=failed_sources,
        )
        compare_check["status"] = "passed" if compare_payload else "warning"
        compare_check["summary"] = str(compare_payload.get("summary", "Drift helper executed."))
    checks.append(compare_check)

    if failed_sources:
        warnings.append("Audit baseline smoke executed with partial data.")
    return _build_suite_result(
        suite="audit_baseline_smoke",
        pbx_id=pbx_id,
        platform=platform,
        checks=checks,
        warnings=warnings,
        failed_sources=failed_sources,
    )


def _suite_active_validation_smoke(
    ctx: Any, pbx_id: str, platform: str, params: dict[str, Any]
) -> dict[str, Any]:
    mode_value = getattr(getattr(ctx, "mode", None), "value", getattr(ctx, "mode", "inspect"))
    mode_name = str(mode_value).strip().lower()
    if mode_name in {"inspect", "plan"}:
        raise ToolError(
            NOT_ALLOWED,
            "active_validation_smoke is blocked in inspect/plan mode",
            {"mode": mode_name},
        )
    if not _active_probes_enabled():
        raise ToolError(
            NOT_ALLOWED,
            "active_validation_smoke requires TELECOM_MCP_ENABLE_ACTIVE_PROBES=1",
            {"required_env": "TELECOM_MCP_ENABLE_ACTIVE_PROBES"},
        )

    failed_sources: list[dict[str, Any]] = []
    warnings: list[str] = []
    checks: list[dict[str, Any]] = []
    destination = str(params.get("destination", "1001"))

    checks.append(
        _call_check(
            ctx,
            check_id="registration-probe",
            tool="telecom.run_registration_probe",
            tool_args={"pbx_id": pbx_id, "destination": destination},
            failed_sources=failed_sources,
            required=True,
        )[0]
    )
    checks.append(
        _call_check(
            ctx,
            check_id="cleanup-verification",
            tool="telecom.verify_cleanup",
            tool_args={"pbx_id": pbx_id},
            failed_sources=failed_sources,
            required=False,
        )[0]
    )
    if failed_sources:
        warnings.append("Active validation smoke executed with partial data.")
    return _build_suite_result(
        suite="active_validation_smoke",
        pbx_id=pbx_id,
        platform=platform,
        checks=checks,
        warnings=warnings,
        failed_sources=failed_sources,
    )


def run_smoke_suite(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    name = _require_str(args, "name").strip().lower()
    if name not in _SMOKE_SUITE_NAMES:
        raise ToolError(
            VALIDATION_ERROR,
            "Unsupported smoke suite",
            {"name": name, "allowed_suites": list(_SMOKE_SUITE_NAMES)},
        )
    pbx_id = _require_str(args, "pbx_id")
    params = _dict_arg(args, "params")
    target = ctx.settings.get_target(pbx_id)
    platform = target.type

    if name == "baseline_read_only_smoke":
        data = _suite_baseline_read_only_smoke(ctx, pbx_id, platform)
    elif name == "registration_visibility_smoke":
        data = _suite_registration_visibility_smoke(ctx, pbx_id, platform)
    elif name == "call_state_visibility_smoke":
        data = _suite_call_state_visibility_smoke(ctx, pbx_id, platform)
    elif name == "audit_baseline_smoke":
        data = _suite_audit_baseline_smoke(ctx, pbx_id, platform, params)
    else:
        data = _suite_active_validation_smoke(ctx, pbx_id, platform, params)
    return {"type": platform, "id": target.id}, data


_BASELINE_STORE: dict[str, dict[str, Any]] = {}
_SEVERITY_PENALTY: dict[str, int] = {
    "critical": 30,
    "risk": 20,
    "warning": 10,
    "info": 3,
}


def _platform_version_major(version_value: Any) -> int | None:
    raw = str(version_value or "").strip()
    if not raw:
        return None
    token = raw.split(".")[0]
    return int(token) if token.isdigit() else None


def _collect_audit_state(
    ctx: Any, pbx_id: str
) -> tuple[str, dict[str, Any], list[dict[str, Any]], list[str]]:
    target = ctx.settings.get_target(pbx_id)
    platform = target.type
    failed_sources: list[dict[str, Any]] = []
    warnings: list[str] = []

    version_tool = "asterisk.version" if platform == "asterisk" else "freeswitch.version"
    modules_tool = "asterisk.modules" if platform == "asterisk" else "freeswitch.modules"

    summary_payload = _call_internal(
        ctx, "telecom.summary", {"pbx_id": pbx_id}, failed_sources=failed_sources
    )
    inventory_payload = _call_internal(
        ctx, "telecom.inventory", {"pbx_id": pbx_id}, failed_sources=failed_sources
    )
    version_payload = _call_internal(
        ctx, version_tool, {"pbx_id": pbx_id}, failed_sources=failed_sources
    )
    modules_payload = _call_internal(
        ctx, modules_tool, {"pbx_id": pbx_id}, failed_sources=failed_sources
    )
    endpoints_payload = _call_internal(
        ctx,
        "telecom.endpoints",
        {"pbx_id": pbx_id, "limit": 500},
        failed_sources=failed_sources,
    )
    registrations_payload = _call_internal(
        ctx,
        "telecom.registrations",
        {"pbx_id": pbx_id, "limit": 500},
        failed_sources=failed_sources,
    )
    channels_payload = _call_internal(
        ctx,
        "telecom.channels",
        {"pbx_id": pbx_id, "limit": 200},
        failed_sources=failed_sources,
    )
    logs_payload = _call_internal(
        ctx,
        "telecom.logs",
        {"pbx_id": pbx_id, "tail": 40},
        failed_sources=failed_sources,
    )

    module_items = _extract_items(modules_payload)
    module_names = _module_names(module_items)
    summary_regs = summary_payload.get("registrations", {})
    if not isinstance(summary_regs, dict):
        summary_regs = {}
    confidence = summary_payload.get("confidence", {})
    if not isinstance(confidence, dict):
        confidence = {}
    posture = inventory_payload.get("posture", {})
    if not isinstance(posture, dict):
        posture = {}
    module_posture = posture.get("module_posture", {})
    if not isinstance(module_posture, dict):
        module_posture = {}

    state = {
        "pbx_id": pbx_id,
        "platform": platform,
        "captured_at": _now_z(),
        "version": version_payload.get("version"),
        "version_major": _platform_version_major(version_payload.get("version")),
        "modules": module_names,
        "module_count": len(module_names),
        "endpoint_count": len(_extract_items(endpoints_payload)),
        "registration_count": len(_extract_items(registrations_payload)),
        "channel_count": len(_extract_items(channels_payload)),
        "log_accessible": bool(logs_payload),
        "channels_visible": bool(channels_payload),
        "registrations_visible": bool(registrations_payload),
        "summary": summary_payload,
        "inventory_baseline": _inventory_map(inventory_payload),
        "critical_modules_missing": (
            module_posture.get("critical_missing", [])
            if isinstance(module_posture.get("critical_missing"), list)
            else []
        ),
        "risky_modules_loaded": (
            module_posture.get("risky_loaded", [])
            if isinstance(module_posture.get("risky_loaded"), list)
            else []
        ),
        "registrations_registered": summary_regs.get("endpoints_registered"),
        "registrations_unreachable": summary_regs.get("endpoints_unreachable"),
        "trunks_confidence": confidence.get("trunks"),
    }
    if failed_sources:
        warnings.append("Audit state collection is partial due to failed subqueries.")
    return platform, state, failed_sources, warnings


def _default_baseline_for_platform(platform: str) -> dict[str, Any]:
    critical, _risky = _module_policies(platform)
    return {
        "baseline_id": f"{platform}-standard-v1",
        "baseline_version": 1,
        "platform": platform,
        "version_min": 18 if platform == "asterisk" else 1,
        "rules": {
            "modules_required": critical,
            "channels_visible": True,
            "logs_accessible": True,
            "registrations_visible": True,
            "endpoints_min": 1,
            "registrations_min": 0,
            "anonymous_sip_disabled": "assumed_if_no_warning",
            "tls_available": "recommended",
        },
        "severity_profile": {
            "PBX_VERSION_SUPPORTED": "risk",
            "REQUIRED_MODULES_LOADED": "critical",
            "MODULES_MISSING": "critical",
            "ANONYMOUS_SIP_DISABLED": "warning",
            "TLS_AVAILABLE": "warning",
            "WEAK_TRANSPORTS_DETECTED": "warning",
            "ENDPOINTS_PRESENT": "warning",
            "REGISTRATIONS_VISIBLE": "warning",
            "REGISTRATION_FAILURE_RATE": "warning",
            "CONTACT_STALENESS": "info",
            "CHANNEL_QUERY_AVAILABLE": "warning",
            "LOG_ACCESS_AVAILABLE": "warning",
            "BRIDGE_QUERY_AVAILABLE": "info",
            "BASELINE_VERSION_MISMATCH": "warning",
            "MODULE_SET_DRIFT": "risk",
            "ENDPOINT_INVENTORY_DRIFT": "warning",
            "REGISTRATION_PATTERN_DRIFT": "warning",
        },
    }


def _policy_catalog(platform: str) -> list[dict[str, Any]]:
    baseline = _default_baseline_for_platform(platform)
    severities = baseline.get("severity_profile", {})
    if not isinstance(severities, dict):
        severities = {}

    def sev(policy_id: str, default: str = "warning") -> str:
        raw = severities.get(policy_id, default)
        value = str(raw).strip().lower()
        return value if value in _SEVERITY_PENALTY else default

    return [
        {
            "policy_id": "PBX_VERSION_SUPPORTED",
            "title": "PBX major version is supported",
            "platform": platform,
            "severity": sev("PBX_VERSION_SUPPORTED", "risk"),
            "description": "Major version must be at or above baseline minimum.",
            "evaluation_method": "version_min_check",
            "evidence_fields": ["version", "version_major", "baseline.version_min"],
            "recommended_action": "Upgrade PBX version to supported baseline.",
        },
        {
            "policy_id": "REQUIRED_MODULES_LOADED",
            "title": "Required module set loaded",
            "platform": platform,
            "severity": sev("REQUIRED_MODULES_LOADED", "critical"),
            "description": "All baseline-required modules should be loaded.",
            "evaluation_method": "required_module_membership",
            "evidence_fields": ["modules", "baseline.rules.modules_required"],
            "recommended_action": "Load missing required modules or adjust baseline policy.",
        },
        {
            "policy_id": "MODULES_MISSING",
            "title": "No critical module gaps",
            "platform": platform,
            "severity": sev("MODULES_MISSING", "critical"),
            "description": "Inventory posture should not report critical module gaps.",
            "evaluation_method": "inventory_module_gap_check",
            "evidence_fields": ["critical_modules_missing"],
            "recommended_action": "Restore missing critical modules.",
        },
        {
            "policy_id": "ANONYMOUS_SIP_DISABLED",
            "title": "Anonymous SIP appears disabled",
            "platform": platform,
            "severity": sev("ANONYMOUS_SIP_DISABLED", "warning"),
            "description": "No obvious anonymous SIP warning indicators in logs.",
            "evaluation_method": "log_heuristic",
            "evidence_fields": ["log_accessible"],
            "recommended_action": "Verify anonymous SIP configuration explicitly at PBX layer.",
        },
        {
            "policy_id": "TLS_AVAILABLE",
            "title": "TLS transport posture",
            "platform": platform,
            "severity": sev("TLS_AVAILABLE", "warning"),
            "description": "TLS availability should be confirmed in transport configuration.",
            "evaluation_method": "inventory_transport_heuristic",
            "evidence_fields": ["inventory_baseline"],
            "recommended_action": "Enable/verify TLS transport where required.",
        },
        {
            "policy_id": "WEAK_TRANSPORTS_DETECTED",
            "title": "Weak transport indicators",
            "platform": platform,
            "severity": sev("WEAK_TRANSPORTS_DETECTED", "warning"),
            "description": "Detect likely insecure transport-only posture.",
            "evaluation_method": "summary_confidence_heuristic",
            "evidence_fields": ["trunks_confidence"],
            "recommended_action": "Review transport security and trunk posture.",
        },
        {
            "policy_id": "ENDPOINTS_PRESENT",
            "title": "Endpoint inventory present",
            "platform": platform,
            "severity": sev("ENDPOINTS_PRESENT", "warning"),
            "description": "At least one endpoint should be visible for operational targets.",
            "evaluation_method": "count_min_check",
            "evidence_fields": ["endpoint_count"],
            "recommended_action": "Verify endpoint provisioning and data collection paths.",
        },
        {
            "policy_id": "REGISTRATIONS_VISIBLE",
            "title": "Registration query visibility",
            "platform": platform,
            "severity": sev("REGISTRATIONS_VISIBLE", "warning"),
            "description": "Registrations query should return data envelope successfully.",
            "evaluation_method": "visibility_check",
            "evidence_fields": ["registrations_visible"],
            "recommended_action": "Validate registration connector and platform query privileges.",
        },
        {
            "policy_id": "REGISTRATION_FAILURE_RATE",
            "title": "Registration failure ratio within threshold",
            "platform": platform,
            "severity": sev("REGISTRATION_FAILURE_RATE", "warning"),
            "description": "Unreachable registrations should remain within policy threshold.",
            "evaluation_method": "ratio_threshold",
            "evidence_fields": ["registrations_registered", "registrations_unreachable"],
            "recommended_action": "Investigate transport/auth failures for unreachable registrations.",
        },
        {
            "policy_id": "CONTACT_STALENESS",
            "title": "Contact staleness indicators",
            "platform": platform,
            "severity": sev("CONTACT_STALENESS", "info"),
            "description": "Detect likely stale contact posture from registration deltas.",
            "evaluation_method": "registration_staleness_heuristic",
            "evidence_fields": ["registration_count", "registrations_registered"],
            "recommended_action": "Review endpoint contact refresh behavior.",
        },
        {
            "policy_id": "CHANNEL_QUERY_AVAILABLE",
            "title": "Channel query available",
            "platform": platform,
            "severity": sev("CHANNEL_QUERY_AVAILABLE", "warning"),
            "description": "Channel query should be available for operations visibility.",
            "evaluation_method": "visibility_check",
            "evidence_fields": ["channels_visible"],
            "recommended_action": "Restore channel visibility path.",
        },
        {
            "policy_id": "LOG_ACCESS_AVAILABLE",
            "title": "Log access available",
            "platform": platform,
            "severity": sev("LOG_ACCESS_AVAILABLE", "warning"),
            "description": "Bounded log reads should be available.",
            "evaluation_method": "visibility_check",
            "evidence_fields": ["log_accessible"],
            "recommended_action": "Enable bounded log access configuration.",
        },
        {
            "policy_id": "BRIDGE_QUERY_AVAILABLE",
            "title": "Bridge query availability",
            "platform": platform,
            "severity": sev("BRIDGE_QUERY_AVAILABLE", "info"),
            "description": "Bridge query support should be available where applicable.",
            "evaluation_method": "platform_capability_check",
            "evidence_fields": ["platform"],
            "recommended_action": "Confirm bridge visibility tooling for platform.",
        },
        {
            "policy_id": "BASELINE_VERSION_MISMATCH",
            "title": "Baseline and target platform compatibility",
            "platform": platform,
            "severity": sev("BASELINE_VERSION_MISMATCH", "warning"),
            "description": "Baseline platform/version profile should match target.",
            "evaluation_method": "baseline_match_check",
            "evidence_fields": ["platform", "baseline.platform"],
            "recommended_action": "Select or create matching baseline for target platform.",
        },
        {
            "policy_id": "MODULE_SET_DRIFT",
            "title": "Module set drift from baseline",
            "platform": platform,
            "severity": sev("MODULE_SET_DRIFT", "risk"),
            "description": "Live module set should align with baseline required modules.",
            "evaluation_method": "module_set_drift",
            "evidence_fields": ["modules", "baseline.rules.modules_required"],
            "recommended_action": "Align module set with baseline expectations.",
        },
        {
            "policy_id": "ENDPOINT_INVENTORY_DRIFT",
            "title": "Endpoint inventory drift",
            "platform": platform,
            "severity": sev("ENDPOINT_INVENTORY_DRIFT", "warning"),
            "description": "Endpoint inventory size should not drift significantly.",
            "evaluation_method": "endpoint_count_drift",
            "evidence_fields": ["endpoint_count", "baseline.state.endpoint_count"],
            "recommended_action": "Review provisioning drift and synchronization steps.",
        },
        {
            "policy_id": "REGISTRATION_PATTERN_DRIFT",
            "title": "Registration pattern drift",
            "platform": platform,
            "severity": sev("REGISTRATION_PATTERN_DRIFT", "warning"),
            "description": "Registration totals should remain within bounded drift.",
            "evaluation_method": "registration_count_drift",
            "evidence_fields": ["registration_count", "baseline.state.registration_count"],
            "recommended_action": "Investigate registration churn or contact instability.",
        },
    ]


def _policy_status(ok: bool, *, degraded: bool = False) -> str:
    if ok:
        return "passed"
    return "warning" if degraded else "failed"


def _evaluate_policies(
    *,
    state: dict[str, Any],
    baseline: dict[str, Any],
    policies: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    rules = baseline.get("rules", {})
    if not isinstance(rules, dict):
        rules = {}
    baseline_state = baseline.get("state", {})
    if not isinstance(baseline_state, dict):
        baseline_state = {}
    required_modules = rules.get("modules_required", [])
    if not isinstance(required_modules, list):
        required_modules = []

    modules = state.get("modules", [])
    if not isinstance(modules, list):
        modules = []
    module_set = {str(x) for x in modules}
    required_set = {str(x) for x in required_modules}

    version_major = state.get("version_major")
    version_min = baseline.get("version_min")
    endpoint_count = int(state.get("endpoint_count", 0) or 0)
    registration_count = int(state.get("registration_count", 0) or 0)
    registrations_registered = state.get("registrations_registered")
    registrations_unreachable = state.get("registrations_unreachable")
    log_accessible = bool(state.get("log_accessible"))
    channels_visible = bool(state.get("channels_visible"))
    registrations_visible = bool(state.get("registrations_visible"))
    critical_missing = state.get("critical_modules_missing", [])
    if not isinstance(critical_missing, list):
        critical_missing = []

    for policy in policies:
        policy_id = str(policy.get("policy_id", "UNKNOWN"))
        severity = str(policy.get("severity", "warning")).lower()
        status = "passed"
        message = "Policy satisfied."
        evidence: dict[str, Any] = {}

        if policy_id == "PBX_VERSION_SUPPORTED":
            ok = isinstance(version_major, int) and isinstance(version_min, int) and version_major >= version_min
            status = _policy_status(ok)
            message = (
                f"version_major={version_major} version_min={version_min}"
                if ok
                else f"Unsupported version_major={version_major}, baseline_min={version_min}"
            )
            evidence = {"version_major": version_major, "version_min": version_min}
        elif policy_id == "REQUIRED_MODULES_LOADED":
            missing = sorted(required_set - module_set)
            ok = not missing
            status = _policy_status(ok)
            message = "All required modules loaded." if ok else f"Missing required modules: {', '.join(missing)}"
            evidence = {"required": sorted(required_set), "loaded": sorted(module_set), "missing": missing}
        elif policy_id == "MODULES_MISSING":
            ok = len(critical_missing) == 0
            status = _policy_status(ok)
            message = "No critical module gaps." if ok else f"Critical missing modules: {', '.join(str(x) for x in critical_missing)}"
            evidence = {"critical_missing": critical_missing}
        elif policy_id == "ANONYMOUS_SIP_DISABLED":
            ok = True
            status = _policy_status(ok, degraded=True)
            message = "No anonymous SIP violation signal detected from current evidence."
            evidence = {"heuristic": True}
        elif policy_id == "TLS_AVAILABLE":
            has_tls_signal = any("tls" in str(k).lower() or "tls" in str(v).lower() for k, v in state.get("inventory_baseline", {}).items())
            status = _policy_status(has_tls_signal, degraded=True)
            message = "TLS signal observed in inventory." if has_tls_signal else "TLS signal not explicit in normalized inventory."
            evidence = {"tls_signal": has_tls_signal}
        elif policy_id == "WEAK_TRANSPORTS_DETECTED":
            trunks_conf = str(state.get("trunks_confidence", "")).strip().lower()
            weak = trunks_conf == "low"
            status = _policy_status(not weak, degraded=True)
            message = "No weak transport signal detected." if not weak else "Low trunk confidence may indicate weak transport posture."
            evidence = {"trunks_confidence": trunks_conf}
        elif policy_id == "ENDPOINTS_PRESENT":
            ok = endpoint_count >= int(rules.get("endpoints_min", 1) or 1)
            status = _policy_status(ok)
            message = f"endpoint_count={endpoint_count}"
            evidence = {"endpoint_count": endpoint_count}
        elif policy_id == "REGISTRATIONS_VISIBLE":
            status = _policy_status(registrations_visible)
            message = "Registration query visible." if registrations_visible else "Registration query unavailable."
            evidence = {"registrations_visible": registrations_visible}
        elif policy_id == "REGISTRATION_FAILURE_RATE":
            if isinstance(registrations_registered, int) and isinstance(registrations_unreachable, int):
                total = max(1, registrations_registered + registrations_unreachable)
                ratio = registrations_unreachable / total
                ok = ratio <= 0.30
                status = _policy_status(ok, degraded=True)
                message = f"unreachable_ratio={ratio:.2f}"
                evidence = {"registered": registrations_registered, "unreachable": registrations_unreachable, "ratio": round(ratio, 4)}
            else:
                status = "warning"
                message = "Registration failure ratio unavailable."
                evidence = {}
        elif policy_id == "CONTACT_STALENESS":
            if isinstance(registrations_registered, int):
                stale = registration_count > max(1, registrations_registered * 4)
                status = _policy_status(not stale, degraded=True)
                message = "No staleness indicator." if not stale else "Potential contact staleness detected."
                evidence = {"registration_count": registration_count, "registered": registrations_registered}
            else:
                status = "warning"
                message = "Contact staleness signal unavailable."
        elif policy_id == "CHANNEL_QUERY_AVAILABLE":
            status = _policy_status(channels_visible)
            message = "Channel query available." if channels_visible else "Channel query unavailable."
            evidence = {"channels_visible": channels_visible}
        elif policy_id == "LOG_ACCESS_AVAILABLE":
            status = _policy_status(log_accessible)
            message = "Log access available." if log_accessible else "Log access unavailable."
            evidence = {"log_accessible": log_accessible}
        elif policy_id == "BRIDGE_QUERY_AVAILABLE":
            ok = str(state.get("platform")) == "asterisk"
            status = _policy_status(ok, degraded=True)
            message = "Bridge query is available for Asterisk." if ok else "Bridge query not standardized for this platform."
            evidence = {"platform": state.get("platform")}
        elif policy_id == "BASELINE_VERSION_MISMATCH":
            ok = str(state.get("platform")) == str(baseline.get("platform"))
            status = _policy_status(ok)
            message = "Baseline platform matches target." if ok else "Baseline platform mismatch."
            evidence = {"target_platform": state.get("platform"), "baseline_platform": baseline.get("platform")}
        elif policy_id == "MODULE_SET_DRIFT":
            baseline_required = required_set
            drift = sorted((module_set ^ baseline_required))
            ok = len(drift) == 0
            status = _policy_status(ok, degraded=True)
            message = "No required module set drift." if ok else f"Module set drift entries: {len(drift)}"
            evidence = {"drift_modules": drift}
        elif policy_id == "ENDPOINT_INVENTORY_DRIFT":
            baseline_endpoint_count = baseline_state.get("endpoint_count")
            if isinstance(baseline_endpoint_count, int):
                diff = abs(endpoint_count - baseline_endpoint_count)
                ok = diff <= max(2, int(baseline_endpoint_count * 0.4))
                status = _policy_status(ok, degraded=True)
                message = f"endpoint_count_diff={diff}"
                evidence = {"baseline_endpoint_count": baseline_endpoint_count, "endpoint_count": endpoint_count}
            else:
                status = "warning"
                message = "Baseline endpoint_count unavailable."
        elif policy_id == "REGISTRATION_PATTERN_DRIFT":
            baseline_registration_count = baseline_state.get("registration_count")
            if isinstance(baseline_registration_count, int):
                diff = abs(registration_count - baseline_registration_count)
                ok = diff <= max(3, int(baseline_registration_count * 0.5))
                status = _policy_status(ok, degraded=True)
                message = f"registration_count_diff={diff}"
                evidence = {"baseline_registration_count": baseline_registration_count, "registration_count": registration_count}
            else:
                status = "warning"
                message = "Baseline registration_count unavailable."

        results.append(
            {
                "policy_id": policy_id,
                "severity": severity,
                "status": status,
                "message": message,
                "evidence": evidence,
            }
        )
    return results


def _score_from_policy_results(policy_results: list[dict[str, Any]]) -> tuple[int, str]:
    score = 100
    for result in policy_results:
        status = str(result.get("status", "failed"))
        if status == "passed":
            continue
        severity = str(result.get("severity", "warning")).lower()
        score -= _SEVERITY_PENALTY.get(severity, 10)
    score = max(0, min(100, score))
    if score >= 90:
        status = "compliant"
    elif score >= 75:
        status = "acceptable"
    elif score >= 60:
        status = "degraded"
    else:
        status = "high_risk"
    return score, status


def _drift_category_from_severity(severity: str) -> str:
    value = severity.lower()
    if value == "critical":
        return "CRITICAL"
    if value == "risk":
        return "RISK"
    if value == "warning":
        return "WARNING"
    return "INFO"


def _drift_target_vs_baseline_payload(
    *,
    pbx_id: str,
    platform: str,
    baseline: dict[str, Any],
    state: dict[str, Any],
    policy_results: list[dict[str, Any]],
    warnings: list[str],
    failed_sources: list[dict[str, Any]],
) -> dict[str, Any]:
    drift_items: list[dict[str, Any]] = []
    for result in policy_results:
        if result.get("status") == "passed":
            continue
        drift_items.append(
            {
                "policy_id": result.get("policy_id"),
                "severity": result.get("severity"),
                "category": _drift_category_from_severity(str(result.get("severity", "warning"))),
                "message": result.get("message"),
                "evidence": result.get("evidence", {}),
            }
        )
    return {
        "pbx_id": pbx_id,
        "platform": platform,
        "baseline_id": baseline.get("baseline_id"),
        "tool": "telecom.drift_target_vs_baseline",
        "summary": f"Detected {len(drift_items)} drift findings against baseline.",
        "counts": {"drift_findings": len(drift_items)},
        "items": drift_items,
        "warnings": warnings,
        "failed_sources": failed_sources,
        "captured_at": _now_z(),
        "state": state,
    }


def baseline_create(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_str(args, "pbx_id")
    baseline_id = _optional_str(args, "baseline_id") or f"{pbx_id}-baseline-v1"
    platform, state, failed_sources, warnings = _collect_audit_state(ctx, pbx_id)
    baseline = _default_baseline_for_platform(platform)
    baseline["baseline_id"] = baseline_id
    baseline["state"] = {
        "version": state.get("version"),
        "version_major": state.get("version_major"),
        "module_count": state.get("module_count"),
        "modules": state.get("modules"),
        "endpoint_count": state.get("endpoint_count"),
        "registration_count": state.get("registration_count"),
        "channels_visible": state.get("channels_visible"),
        "logs_accessible": state.get("log_accessible"),
    }
    baseline["captured_from"] = {
        "pbx_id": pbx_id,
        "captured_at": _now_z(),
    }
    _BASELINE_STORE[str(baseline_id)] = baseline
    data = {
        "pbx_id": pbx_id,
        "platform": platform,
        "tool": "telecom.baseline_create",
        "summary": f"Created baseline '{baseline_id}' from target state.",
        "baseline_id": baseline_id,
        "baseline": baseline,
        "warnings": warnings,
        "failed_sources": failed_sources,
        "captured_at": _now_z(),
    }
    target = ctx.settings.get_target(pbx_id)
    return {"type": target.type, "id": target.id}, data


def baseline_show(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    baseline_id = _require_str(args, "baseline_id")
    baseline = _BASELINE_STORE.get(baseline_id)
    if not baseline:
        raise ToolError(
            NOT_FOUND,
            f"Baseline '{baseline_id}' not found",
            {"baseline_id": baseline_id},
        )
    platform = str(baseline.get("platform", "telecom"))
    return {"type": platform, "id": baseline_id}, {
        "baseline_id": baseline_id,
        "platform": platform,
        "tool": "telecom.baseline_show",
        "summary": f"Loaded baseline '{baseline_id}'.",
        "baseline": baseline,
        "captured_at": _now_z(),
        "warnings": [],
    }


def audit_target(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_str(args, "pbx_id")
    baseline_id = _optional_str(args, "baseline_id")
    platform, state, failed_sources, warnings = _collect_audit_state(ctx, pbx_id)

    baseline = _BASELINE_STORE.get(baseline_id) if baseline_id else None
    if baseline is None:
        baseline = _default_baseline_for_platform(platform)
        warnings.append("No baseline_id supplied/found; using platform default baseline.")

    policies = _policy_catalog(platform)
    policy_results = _evaluate_policies(state=state, baseline=baseline, policies=policies)
    score, score_status = _score_from_policy_results(policy_results)
    violations = [result for result in policy_results if result.get("status") != "passed"]
    recommendations = sorted(
        {
            str(policy.get("recommended_action"))
            for policy, result in zip(policies, policy_results)
            if result.get("status") != "passed" and policy.get("recommended_action")
        }
    )

    data = {
        "pbx_id": pbx_id,
        "platform": platform,
        "tool": "telecom.audit_target",
        "summary": f"audit_score={score} status={score_status}",
        "baseline_id": baseline.get("baseline_id"),
        "score": score,
        "status": score_status,
        "policy_results": policy_results,
        "violations": violations,
        "drift": [
            {
                "policy_id": result.get("policy_id"),
                "category": _drift_category_from_severity(str(result.get("severity", "warning"))),
                "message": result.get("message"),
            }
            for result in violations
        ],
        "recommendations": recommendations,
        "warnings": warnings,
        "failed_sources": failed_sources,
        "captured_at": _now_z(),
    }
    target = ctx.settings.get_target(pbx_id)
    return {"type": target.type, "id": target.id}, data


def drift_target_vs_baseline(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_str(args, "pbx_id")
    baseline_id = _require_str(args, "baseline_id")
    baseline = _BASELINE_STORE.get(baseline_id)
    if not baseline:
        raise ToolError(
            NOT_FOUND,
            f"Baseline '{baseline_id}' not found",
            {"baseline_id": baseline_id},
        )

    platform, state, failed_sources, warnings = _collect_audit_state(ctx, pbx_id)
    policies = _policy_catalog(platform)
    policy_results = _evaluate_policies(state=state, baseline=baseline, policies=policies)
    data = _drift_target_vs_baseline_payload(
        pbx_id=pbx_id,
        platform=platform,
        baseline=baseline,
        state=state,
        policy_results=policy_results,
        warnings=warnings,
        failed_sources=failed_sources,
    )
    target = ctx.settings.get_target(pbx_id)
    return {"type": target.type, "id": target.id}, data


def drift_compare_targets(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_a = _require_str(args, "pbx_a")
    pbx_b = _require_str(args, "pbx_b")
    if pbx_a == pbx_b:
        raise ToolError(VALIDATION_ERROR, "Fields 'pbx_a' and 'pbx_b' must differ")

    failed_sources: list[dict[str, Any]] = []
    compare_payload = _call_internal(
        ctx,
        "telecom.compare_targets",
        {"pbx_a": pbx_a, "pbx_b": pbx_b},
        failed_sources=failed_sources,
    )
    items = _extract_items(compare_payload)
    drift_categories = compare_payload.get("drift_categories", [])
    if not isinstance(drift_categories, list):
        drift_categories = []
    warnings: list[str] = []
    if failed_sources:
        warnings.append("Cross-target drift comparison is partial.")
    return {"type": "telecom", "id": f"{pbx_a}::{pbx_b}"}, {
        "pbx_id": f"{pbx_a}::{pbx_b}",
        "platform": "telecom",
        "tool": "telecom.drift_compare_targets",
        "summary": compare_payload.get("summary", f"Compared {pbx_a} vs {pbx_b}"),
        "counts": {
            "differences": len(items),
            "drift_categories": len(drift_categories),
        },
        "items": items,
        "drift_categories": drift_categories,
        "warnings": warnings,
        "failed_sources": failed_sources,
        "captured_at": _now_z(),
    }


def audit_report(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_str(args, "pbx_id")
    audit_payload = _call_internal(
        ctx,
        "telecom.audit_target",
        {"pbx_id": pbx_id, **({"baseline_id": args["baseline_id"]} if "baseline_id" in args else {})},
        failed_sources=[],
    )
    report_lines = [
        "PBX Audit Report",
        "----------------",
        f"target: {pbx_id}",
        f"platform: {audit_payload.get('platform', 'unknown')}",
        f"score: {audit_payload.get('score', 'n/a')}",
        f"status: {audit_payload.get('status', 'unknown')}",
        "",
        "violations:",
    ]
    violations = audit_payload.get("violations", [])
    if isinstance(violations, list) and violations:
        for violation in violations[:20]:
            if isinstance(violation, dict):
                report_lines.append(
                    f"- {violation.get('policy_id')}: {violation.get('message')}"
                )
    else:
        report_lines.append("- none")
    report_lines.append("")
    report_lines.append("recommendations:")
    recommendations = audit_payload.get("recommendations", [])
    if isinstance(recommendations, list) and recommendations:
        for recommendation in recommendations[:20]:
            report_lines.append(f"- {recommendation}")
    else:
        report_lines.append("- none")
    report = "\n".join(report_lines)

    target = ctx.settings.get_target(pbx_id)
    return {"type": target.type, "id": target.id}, {
        "pbx_id": pbx_id,
        "platform": target.type,
        "tool": "telecom.audit_report",
        "summary": "Structured audit report generated.",
        "report": report,
        "audit": audit_payload,
        "captured_at": _now_z(),
        "warnings": [],
    }


def audit_export(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_str(args, "pbx_id")
    format_name = (_optional_str(args, "format") or "json").lower()
    if format_name not in {"json", "markdown"}:
        raise ToolError(
            VALIDATION_ERROR,
            "Unsupported export format",
            {"format": format_name, "allowed": ["json", "markdown"]},
        )
    report_payload = _call_internal(
        ctx,
        "telecom.audit_report",
        {"pbx_id": pbx_id, **({"baseline_id": args["baseline_id"]} if "baseline_id" in args else {})},
        failed_sources=[],
    )
    target = ctx.settings.get_target(pbx_id)
    if format_name == "markdown":
        exported = str(report_payload.get("report", ""))
    else:
        exported = report_payload
    return {"type": target.type, "id": target.id}, {
        "pbx_id": pbx_id,
        "platform": target.type,
        "tool": "telecom.audit_export",
        "summary": f"Audit exported as {format_name}.",
        "format": format_name,
        "export": exported,
        "captured_at": _now_z(),
        "warnings": [],
    }


_SCORE_DIMENSIONS: tuple[tuple[str, int], ...] = (
    ("Configuration Integrity", 20),
    ("Runtime Health", 20),
    ("Detection Readiness", 15),
    ("Validation Confidence", 15),
    ("Fault Resilience", 15),
    ("Incident Burden", 15),
)
_SCORECARD_HISTORY: dict[str, list[dict[str, Any]]] = {}


def _score_band(score: int) -> str:
    if score >= 90:
        return "strong"
    if score >= 75:
        return "acceptable"
    if score >= 60:
        return "degraded"
    return "at_risk"


def _severity_weight(severity: str) -> int:
    value = severity.lower()
    if value == "critical":
        return 4
    if value == "risk":
        return 3
    if value == "warning":
        return 2
    return 1


def _confidence_from_inputs(
    *, available: int, expected: int, freshness_ok: bool, missing_reasons: list[str]
) -> tuple[str, list[str]]:
    if expected <= 0:
        return "low", ["No expected evidence inputs configured."]
    ratio = available / expected
    reasons = list(missing_reasons)
    if not freshness_ok:
        reasons.append("Evidence freshness is stale or unknown.")
    if ratio >= 0.8 and freshness_ok:
        return "high", reasons
    if ratio >= 0.55:
        return "medium", reasons
    return "low", reasons


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _register_scorecard_history(entity_type: str, entity_id: str, scorecard: dict[str, Any]) -> None:
    key = f"{entity_type}:{entity_id}"
    entries = _SCORECARD_HISTORY.get(key, [])
    entries.append(scorecard)
    _SCORECARD_HISTORY[key] = entries[-300:]


def _trend_summary(entity_type: str, entity_id: str, current_score: int) -> dict[str, Any]:
    key = f"{entity_type}:{entity_id}"
    history = _SCORECARD_HISTORY.get(key, [])
    if len(history) < 2:
        return {
            "window": "local-history",
            "absolute_change": 0,
            "dimension_changes": [],
            "confidence_change": "n/a",
            "top_new_risks": [],
            "top_recovered_areas": [],
        }
    previous = history[-2]
    prev_score = int(previous.get("score", current_score))
    return {
        "window": "local-history",
        "absolute_change": current_score - prev_score,
        "dimension_changes": [],
        "confidence_change": f"{previous.get('confidence', 'unknown')} -> {history[-1].get('confidence', 'unknown')}",
        "top_new_risks": [],
        "top_recovered_areas": [],
    }


def _dimension(
    *,
    name: str,
    weight: int,
    score: int,
    confidence: str,
    key_inputs: list[str],
    positives: list[str],
    negatives: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    return {
        "name": name,
        "score": max(0, min(100, score)),
        "weight": weight,
        "confidence": confidence,
        "key_inputs": key_inputs,
        "positive_signals": positives,
        "negative_signals": negatives,
        "warnings": warnings,
    }


def _compose_scorecard(
    *,
    entity_type: str,
    entity_id: str,
    dimensions: list[dict[str, Any]],
    confidence: str,
    confidence_reasons: list[str],
    evidence_summary: dict[str, Any],
    top_strengths: list[str],
    top_risks: list[str],
) -> dict[str, Any]:
    total_weight = sum(int(d.get("weight", 0)) for d in dimensions) or 1
    weighted = sum(int(d.get("score", 0)) * int(d.get("weight", 0)) for d in dimensions)
    score = round(weighted / total_weight)

    # Cap score if critical negative signals exist.
    has_critical = any(
        "critical" in str(signal).lower()
        for dim in dimensions
        for signal in _safe_list(dim.get("negative_signals"))
    )
    if has_critical:
        score = min(score, 74)

    band = _score_band(score)
    card = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "score": score,
        "band": band,
        "confidence": confidence,
        "confidence_reasons": confidence_reasons,
        "summary": f"{entity_type} scorecard is {band} ({score}/100).",
        "dimensions": dimensions,
        "top_strengths": top_strengths[:5],
        "top_risks": top_risks[:5],
        "evidence_summary": evidence_summary,
        "trend_summary": {},
        "generated_at": _now_z(),
    }
    card["trend_summary"] = _trend_summary(entity_type, entity_id, score)
    _register_scorecard_history(entity_type, entity_id, card)
    return card


def _scorecard_target_data(
    ctx: Any, pbx_id: str
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    failed_sources: list[dict[str, Any]] = []
    warnings: list[str] = []
    missing_reasons: list[str] = []
    available_inputs = 0
    expected_inputs = 8

    audit_payload = _call_internal(
        ctx,
        "telecom.audit_target",
        {"pbx_id": pbx_id},
        failed_sources=failed_sources,
    )
    if audit_payload:
        available_inputs += 1
    else:
        missing_reasons.append("Audit target output unavailable.")

    smoke_names = (
        "baseline_read_only_smoke",
        "registration_visibility_smoke",
        "call_state_visibility_smoke",
        "audit_baseline_smoke",
    )
    smoke_payloads: list[dict[str, Any]] = []
    for suite in smoke_names:
        payload = _call_internal(
            ctx,
            "telecom.run_smoke_suite",
            {"name": suite, "pbx_id": pbx_id},
            failed_sources=failed_sources,
        )
        if payload:
            available_inputs += 1
            smoke_payloads.append(payload)
        else:
            missing_reasons.append(f"Smoke suite '{suite}' unavailable.")

    playbook_payload = _call_internal(
        ctx,
        "telecom.run_playbook",
        {"name": "outbound_call_failure_triage", "pbx_id": pbx_id},
        failed_sources=failed_sources,
    )
    if playbook_payload:
        available_inputs += 1
    else:
        missing_reasons.append("Playbook signal unavailable.")

    probe_payload = _call_internal(
        ctx,
        "telecom.verify_cleanup",
        {"pbx_id": pbx_id},
        failed_sources=failed_sources,
    )
    if probe_payload:
        available_inputs += 1
    else:
        missing_reasons.append("Probe cleanup verification unavailable.")

    # Chaos and incident packs are optional in this phase; missing lowers confidence.
    missing_reasons.append("Chaos scenario signal not integrated yet.")
    missing_reasons.append("Incident burden feed not integrated yet.")

    audit_score = int(audit_payload.get("score", 70)) if audit_payload else 60
    audit_status = str(audit_payload.get("status", "unknown")) if audit_payload else "unknown"
    audit_violations = _safe_list(audit_payload.get("violations"))
    negative_integrity = [
        f"{violation.get('policy_id')} ({violation.get('severity')})"
        for violation in audit_violations
        if isinstance(violation, dict)
    ]

    smoke_passed = 0
    smoke_total = 0
    runtime_warnings: list[str] = []
    for payload in smoke_payloads:
        counts = _safe_dict(payload.get("counts"))
        smoke_passed += int(counts.get("passed", 0))
        smoke_total += int(counts.get("passed", 0)) + int(counts.get("warning", 0)) + int(counts.get("failed", 0))
        runtime_warnings.extend([str(w) for w in _safe_list(payload.get("warnings")) if isinstance(w, str)])
    runtime_score = 70
    if smoke_total > 0:
        runtime_score = round((smoke_passed / max(1, smoke_total)) * 100)

    playbook_status = str(playbook_payload.get("status", "warning")) if playbook_payload else "warning"
    detection_score = 85 if playbook_status == "passed" else (70 if playbook_status == "warning" else 50)
    detection_negatives = []
    if playbook_payload and _safe_list(playbook_payload.get("failed_sources")):
        detection_negatives.append("Playbook evidence collection was partial.")
    if not playbook_payload:
        detection_negatives.append("No playbook detection signal available.")

    validation_score = 75 if probe_payload else 55
    validation_negatives = []
    if probe_payload and probe_payload.get("clean") is False:
        validation_score = 55
        validation_negatives.append("Cleanup verification reported residual probe artifacts.")
    if not probe_payload:
        validation_negatives.append("Validation probe signal missing.")

    fault_score = 60
    fault_negatives = ["Chaos scenario coverage unavailable (not yet integrated)."]

    incident_score = 65
    incident_negatives = ["Incident burden feed unavailable (not yet integrated)."]

    confidence, confidence_reasons = _confidence_from_inputs(
        available=available_inputs,
        expected=expected_inputs,
        freshness_ok=True,
        missing_reasons=missing_reasons,
    )
    if failed_sources:
        warnings.append("One or more scorecard evidence subcalls failed.")

    dimensions = [
        _dimension(
            name="Configuration Integrity",
            weight=20,
            score=audit_score,
            confidence="high" if audit_payload else "low",
            key_inputs=["telecom.audit_target"],
            positives=[f"audit_status={audit_status}"] if audit_payload else [],
            negatives=negative_integrity,
            warnings=[],
        ),
        _dimension(
            name="Runtime Health",
            weight=20,
            score=runtime_score,
            confidence="medium" if smoke_payloads else "low",
            key_inputs=["telecom.run_smoke_suite:*"],
            positives=[f"smoke_passed={smoke_passed}"],
            negatives=[],
            warnings=runtime_warnings,
        ),
        _dimension(
            name="Detection Readiness",
            weight=15,
            score=detection_score,
            confidence="medium",
            key_inputs=["telecom.run_playbook"],
            positives=["Playbook result consumed for triage readiness."] if playbook_payload else [],
            negatives=detection_negatives,
            warnings=[],
        ),
        _dimension(
            name="Validation Confidence",
            weight=15,
            score=validation_score,
            confidence="medium" if probe_payload else "low",
            key_inputs=["telecom.verify_cleanup"],
            positives=["Cleanup verification present."] if probe_payload else [],
            negatives=validation_negatives,
            warnings=[],
        ),
        _dimension(
            name="Fault Resilience",
            weight=15,
            score=fault_score,
            confidence="low",
            key_inputs=["chaos-signals"],
            positives=[],
            negatives=fault_negatives,
            warnings=["No chaos evidence integrated in this stage."],
        ),
        _dimension(
            name="Incident Burden",
            weight=15,
            score=incident_score,
            confidence="low",
            key_inputs=["incident-evidence-signals"],
            positives=[],
            negatives=incident_negatives,
            warnings=["No incident burden feed integrated in this stage."],
        ),
    ]

    top_strengths = []
    top_risks = []
    for dim in dimensions:
        name = str(dim.get("name"))
        if int(dim.get("score", 0)) >= 80:
            top_strengths.append(f"{name} is strong ({dim.get('score')}).")
        if int(dim.get("score", 0)) < 65:
            top_risks.append(f"{name} is weak ({dim.get('score')}).")
        for neg in _safe_list(dim.get("negative_signals")):
            top_risks.append(str(neg))

    evidence_summary = {
        "audit": bool(audit_payload),
        "smoke_suites": [payload.get("suite") for payload in smoke_payloads if isinstance(payload.get("suite"), str)],
        "playbook": playbook_payload.get("playbook") if isinstance(playbook_payload, dict) else None,
        "probe_cleanup": bool(probe_payload),
        "chaos": False,
        "incidents": False,
    }

    scorecard = _compose_scorecard(
        entity_type="pbx",
        entity_id=pbx_id,
        dimensions=dimensions,
        confidence=confidence,
        confidence_reasons=confidence_reasons,
        evidence_summary=evidence_summary,
        top_strengths=top_strengths,
        top_risks=top_risks,
    )
    return scorecard, failed_sources, warnings


def scorecard_target(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_str(args, "pbx_id")
    target = ctx.settings.get_target(pbx_id)
    scorecard, failed_sources, warnings = _scorecard_target_data(ctx, pbx_id)
    return {"type": target.type, "id": target.id}, {
        "tool": "telecom.scorecard_target",
        "pbx_id": pbx_id,
        "scorecard": scorecard,
        "failed_sources": failed_sources,
        "warnings": warnings,
        "captured_at": _now_z(),
    }


def _entity_weight(card: dict[str, Any]) -> float:
    confidence = str(card.get("confidence", "low")).lower()
    if confidence == "high":
        return 1.0
    if confidence == "medium":
        return 0.8
    return 0.6


def scorecard_cluster(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    cluster_id = _require_str(args, "cluster_id")
    pbx_ids_raw = args.get("pbx_ids")
    if not isinstance(pbx_ids_raw, list) or not pbx_ids_raw:
        raise ToolError(
            VALIDATION_ERROR,
            "Field 'pbx_ids' must be a non-empty array",
            {"field": "pbx_ids"},
        )
    pbx_ids = [str(pbx_id).strip() for pbx_id in pbx_ids_raw if str(pbx_id).strip()]
    if not pbx_ids:
        raise ToolError(VALIDATION_ERROR, "Field 'pbx_ids' must include at least one non-empty value")

    members: list[dict[str, Any]] = []
    failed_sources: list[dict[str, Any]] = []
    for pbx_id in pbx_ids:
        payload = _call_internal(
            ctx,
            "telecom.scorecard_target",
            {"pbx_id": pbx_id},
            failed_sources=failed_sources,
        )
        card = _safe_dict(payload.get("scorecard"))
        if card:
            members.append({"pbx_id": pbx_id, "scorecard": card})

    if not members:
        raise ToolError(UPSTREAM_ERROR, "No member scorecards available for cluster rollup")

    weighted_sum = 0.0
    weight_total = 0.0
    for member in members:
        card = _safe_dict(member.get("scorecard"))
        weight = _entity_weight(card)
        weighted_sum += int(card.get("score", 0)) * weight
        weight_total += weight
    score = round(weighted_sum / max(0.001, weight_total))
    confidence = "medium" if len(members) >= 2 else "low"
    confidence_reasons = []
    if failed_sources:
        confidence_reasons.append("Some member scorecards failed to collect.")

    dimensions: list[dict[str, Any]] = []
    for name, weight in _SCORE_DIMENSIONS:
        values = [
            int(dim.get("score", 0))
            for member in members
            for dim in _safe_list(_safe_dict(member.get("scorecard")).get("dimensions"))
            if isinstance(dim, dict) and str(dim.get("name")) == name
        ]
        dim_score = round(sum(values) / max(1, len(values))) if values else 50
        dimensions.append(
            _dimension(
                name=name,
                weight=weight,
                score=dim_score,
                confidence=confidence,
                key_inputs=["member.scorecards"],
                positives=[],
                negatives=[],
                warnings=[],
            )
        )

    scorecard = _compose_scorecard(
        entity_type="cluster",
        entity_id=cluster_id,
        dimensions=dimensions,
        confidence=confidence,
        confidence_reasons=confidence_reasons,
        evidence_summary={"members": [m.get("pbx_id") for m in members]},
        top_strengths=[],
        top_risks=[],
    )
    scorecard["score"] = score
    scorecard["band"] = _score_band(score)
    _register_scorecard_history("cluster", cluster_id, scorecard)
    return {"type": "telecom", "id": cluster_id}, {
        "tool": "telecom.scorecard_cluster",
        "cluster_id": cluster_id,
        "scorecard": scorecard,
        "members": members,
        "failed_sources": failed_sources,
        "warnings": [],
        "captured_at": _now_z(),
    }


def scorecard_environment(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    environment_id = _require_str(args, "environment_id")
    pbx_ids_raw = args.get("pbx_ids")
    pbx_ids: list[str] = []
    if isinstance(pbx_ids_raw, list) and pbx_ids_raw:
        pbx_ids = [str(pbx_id).strip() for pbx_id in pbx_ids_raw if str(pbx_id).strip()]
    else:
        # Fallback to all configured targets for environment rollup.
        pbx_ids = [str(target.id) for target in getattr(ctx.settings, "targets", []) if getattr(target, "id", None)]
    if not pbx_ids:
        raise ToolError(VALIDATION_ERROR, "No PBX targets available for environment rollup")

    entity_args = {"cluster_id": f"{environment_id}-cluster", "pbx_ids": pbx_ids}
    _target, cluster_payload = scorecard_cluster(ctx, entity_args)
    cluster_card = _safe_dict(cluster_payload.get("scorecard"))
    scorecard = dict(cluster_card)
    scorecard["entity_type"] = "environment"
    scorecard["entity_id"] = environment_id
    scorecard["summary"] = f"environment scorecard is {scorecard.get('band')} ({scorecard.get('score')}/100)."
    _register_scorecard_history("environment", environment_id, scorecard)
    return {"type": "telecom", "id": environment_id}, {
        "tool": "telecom.scorecard_environment",
        "environment_id": environment_id,
        "scorecard": scorecard,
        "members": pbx_ids,
        "warnings": [],
        "captured_at": _now_z(),
    }


def scorecard_compare(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    entity_type = (_optional_str(args, "entity_type") or "pbx").lower()
    entity_a = _require_str(args, "entity_a")
    entity_b = _require_str(args, "entity_b")
    allowed = {"pbx", "cluster", "environment"}
    if entity_type not in allowed:
        raise ToolError(
            VALIDATION_ERROR,
            "Unsupported entity_type",
            {"entity_type": entity_type, "allowed": sorted(allowed)},
        )

    if entity_type == "pbx":
        card_a = _safe_dict(_call_internal(ctx, "telecom.scorecard_target", {"pbx_id": entity_a}, failed_sources=[]).get("scorecard"))
        card_b = _safe_dict(_call_internal(ctx, "telecom.scorecard_target", {"pbx_id": entity_b}, failed_sources=[]).get("scorecard"))
    elif entity_type == "cluster":
        pbx_ids_a = _safe_list(args.get("pbx_ids_a"))
        pbx_ids_b = _safe_list(args.get("pbx_ids_b"))
        card_a = _safe_dict(
            _call_internal(
                ctx,
                "telecom.scorecard_cluster",
                {"cluster_id": entity_a, "pbx_ids": pbx_ids_a},
                failed_sources=[],
            ).get("scorecard")
        )
        card_b = _safe_dict(
            _call_internal(
                ctx,
                "telecom.scorecard_cluster",
                {"cluster_id": entity_b, "pbx_ids": pbx_ids_b},
                failed_sources=[],
            ).get("scorecard")
        )
    else:
        pbx_ids_a = _safe_list(args.get("pbx_ids_a"))
        pbx_ids_b = _safe_list(args.get("pbx_ids_b"))
        card_a = _safe_dict(
            _call_internal(
                ctx,
                "telecom.scorecard_environment",
                {"environment_id": entity_a, "pbx_ids": pbx_ids_a},
                failed_sources=[],
            ).get("scorecard")
        )
        card_b = _safe_dict(
            _call_internal(
                ctx,
                "telecom.scorecard_environment",
                {"environment_id": entity_b, "pbx_ids": pbx_ids_b},
                failed_sources=[],
            ).get("scorecard")
        )

    score_a = int(card_a.get("score", 0))
    score_b = int(card_b.get("score", 0))
    return {"type": "telecom", "id": f"{entity_type}:{entity_a}::{entity_b}"}, {
        "tool": "telecom.scorecard_compare",
        "entity_type": entity_type,
        "entity_a": entity_a,
        "entity_b": entity_b,
        "score_a": score_a,
        "score_b": score_b,
        "delta": score_a - score_b,
        "card_a": card_a,
        "card_b": card_b,
        "captured_at": _now_z(),
        "warnings": [],
    }


def scorecard_trend(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    entity_type = (_optional_str(args, "entity_type") or "pbx").lower()
    entity_id = _require_str(args, "entity_id")
    window = _optional_str(args, "window") or "30d"
    if entity_type not in {"pbx", "cluster", "environment"}:
        raise ToolError(
            VALIDATION_ERROR,
            "Unsupported entity_type",
            {"entity_type": entity_type, "allowed": ["pbx", "cluster", "environment"]},
        )
    key = f"{entity_type}:{entity_id}"
    entries = _SCORECARD_HISTORY.get(key, [])
    latest = entries[-1] if entries else {}
    if not entries:
        # Generate one on-demand to initialize trend.
        if entity_type == "pbx":
            _target, payload = scorecard_target(ctx, {"pbx_id": entity_id})
        elif entity_type == "cluster":
            raise ToolError(VALIDATION_ERROR, "Cluster trend requires prior scorecard history or explicit generation step")
        else:
            raise ToolError(VALIDATION_ERROR, "Environment trend requires prior scorecard history or explicit generation step")
        latest = _safe_dict(payload.get("scorecard"))
        entries = _SCORECARD_HISTORY.get(key, [latest])
    previous = entries[-2] if len(entries) > 1 else latest
    latest_score = int(latest.get("score", 0))
    prev_score = int(previous.get("score", latest_score))
    return {"type": "telecom", "id": f"{entity_type}:{entity_id}"}, {
        "tool": "telecom.scorecard_trend",
        "entity_type": entity_type,
        "entity_id": entity_id,
        "window": window,
        "current_score": latest_score,
        "previous_score": prev_score,
        "absolute_change": latest_score - prev_score,
        "current_confidence": latest.get("confidence"),
        "previous_confidence": previous.get("confidence"),
        "top_new_risks": latest.get("top_risks", []),
        "top_recovered_areas": latest.get("top_strengths", []),
        "generated_at": _now_z(),
        "warnings": [],
    }


def scorecard_export(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    entity_type = (_optional_str(args, "entity_type") or "pbx").lower()
    entity_id = _require_str(args, "entity_id")
    format_name = (_optional_str(args, "format") or "json").lower()
    if format_name not in {"json", "markdown"}:
        raise ToolError(
            VALIDATION_ERROR,
            "Unsupported export format",
            {"format": format_name, "allowed": ["json", "markdown"]},
        )

    if entity_type == "pbx":
        payload = _call_internal(ctx, "telecom.scorecard_target", {"pbx_id": entity_id}, failed_sources=[])
    elif entity_type == "cluster":
        payload = _call_internal(
            ctx,
            "telecom.scorecard_cluster",
            {"cluster_id": entity_id, "pbx_ids": _safe_list(args.get("pbx_ids"))},
            failed_sources=[],
        )
    elif entity_type == "environment":
        payload = _call_internal(
            ctx,
            "telecom.scorecard_environment",
            {"environment_id": entity_id, "pbx_ids": _safe_list(args.get("pbx_ids"))},
            failed_sources=[],
        )
    else:
        raise ToolError(
            VALIDATION_ERROR,
            "Unsupported entity_type",
            {"entity_type": entity_type, "allowed": ["pbx", "cluster", "environment"]},
        )
    scorecard = _safe_dict(payload.get("scorecard"))
    exported: Any = scorecard
    if format_name == "markdown":
        lines = [
            "Telecom Resilience Scorecard",
            "----------------------------",
            f"entity_type: {entity_type}",
            f"entity_id: {entity_id}",
            f"score: {scorecard.get('score')}",
            f"band: {scorecard.get('band')}",
            f"confidence: {scorecard.get('confidence')}",
            "",
            "top_risks:",
        ]
        risks = _safe_list(scorecard.get("top_risks"))
        if risks:
            for risk in risks[:10]:
                lines.append(f"- {risk}")
        else:
            lines.append("- none")
        exported = "\n".join(lines)
    return {"type": "telecom", "id": f"{entity_type}:{entity_id}"}, {
        "tool": "telecom.scorecard_export",
        "entity_type": entity_type,
        "entity_id": entity_id,
        "format": format_name,
        "export": exported,
        "captured_at": _now_z(),
        "warnings": [],
    }


_EVIDENCE_PACKS: dict[str, dict[str, Any]] = {}


def _stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _evidence_item(
    *,
    source: str,
    tool_used: str,
    payload: dict[str, Any],
    notes: str = "",
) -> dict[str, Any]:
    captured = _now_z()
    data_hash = _stable_hash(payload)
    return {
        "evidence_id": f"ev-{source}-{data_hash[:10]}",
        "source": source,
        "type": "telemetry",
        "collection_method": "mcp_tool_call",
        "timestamp": captured,
        "tool_used": tool_used,
        "data_reference": source,
        "hash": data_hash,
        "notes": notes,
        "data": payload,
    }


def _collect_incident_evidence(
    ctx: Any, *, pbx_id: str, include_integrations: bool = True
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    failed_sources: list[dict[str, Any]] = []
    warnings: list[str] = []
    evidence_items: list[dict[str, Any]] = []
    target = ctx.settings.get_target(pbx_id)

    base_calls: list[tuple[str, dict[str, Any], str]] = [
        ("telecom.summary", {"pbx_id": pbx_id}, "pbx-state/summary"),
        ("telecom.capture_snapshot", {"pbx_id": pbx_id}, "pbx-state/snapshot"),
        ("telecom.endpoints", {"pbx_id": pbx_id, "limit": 500}, "sip/endpoints"),
        ("telecom.registrations", {"pbx_id": pbx_id, "limit": 500}, "sip/registrations"),
        ("telecom.channels", {"pbx_id": pbx_id, "limit": 500}, "calls/channels"),
        ("telecom.calls", {"pbx_id": pbx_id, "limit": 500}, "calls/calls"),
        ("telecom.logs", {"pbx_id": pbx_id, "tail": 250}, "logs/pbx"),
    ]
    if target.type == "asterisk":
        base_calls.extend(
            [
                ("asterisk.version", {"pbx_id": pbx_id}, "vendor/asterisk/version"),
                ("asterisk.modules", {"pbx_id": pbx_id}, "vendor/asterisk/modules"),
                ("asterisk.pjsip_show_endpoints", {"pbx_id": pbx_id, "limit": 500}, "vendor/asterisk/pjsip_endpoints"),
                ("asterisk.pjsip_show_contacts", {"pbx_id": pbx_id, "limit": 500}, "vendor/asterisk/pjsip_contacts"),
            ]
        )
    else:
        base_calls.extend(
            [
                ("freeswitch.version", {"pbx_id": pbx_id}, "vendor/freeswitch/version"),
                ("freeswitch.modules", {"pbx_id": pbx_id}, "vendor/freeswitch/modules"),
                ("freeswitch.channels", {"pbx_id": pbx_id, "limit": 500}, "vendor/freeswitch/channels"),
                ("freeswitch.calls", {"pbx_id": pbx_id, "limit": 500}, "vendor/freeswitch/calls"),
                ("freeswitch.sofia_status", {"pbx_id": pbx_id}, "vendor/freeswitch/sofia_status"),
            ]
        )

    for tool_name, tool_args, source_ref in base_calls:
        payload = _call_internal(ctx, tool_name, tool_args, failed_sources=failed_sources)
        if payload:
            evidence_items.append(
                _evidence_item(
                    source=source_ref,
                    tool_used=tool_name,
                    payload=payload,
                )
            )

    if include_integrations:
        integration_calls = [
            ("telecom.run_smoke_suite", {"name": "baseline_read_only_smoke", "pbx_id": pbx_id}, "validation/smoke"),
            ("telecom.run_playbook", {"name": "outbound_call_failure_triage", "pbx_id": pbx_id}, "validation/playbook"),
            ("telecom.audit_target", {"pbx_id": pbx_id}, "audits/audit_report"),
            ("telecom.drift_target_vs_baseline", {"pbx_id": pbx_id, "baseline_id": f"{pbx_id}-baseline-v1"}, "audits/drift_report"),
            ("telecom.verify_cleanup", {"pbx_id": pbx_id}, "validation/probe_cleanup"),
        ]
        for tool_name, tool_args, source_ref in integration_calls:
            payload = _call_internal(ctx, tool_name, tool_args, failed_sources=failed_sources)
            if payload:
                evidence_items.append(
                    _evidence_item(
                        source=source_ref,
                        tool_used=tool_name,
                        payload=payload,
                    )
                )

    if failed_sources:
        warnings.append("Evidence collection is partial due to failed tool calls.")
    return evidence_items, failed_sources, warnings


def _timeline_from_evidence(evidence_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for item in evidence_items:
        payload = _safe_dict(item.get("data"))
        timestamp = str(item.get("timestamp", _now_z()))
        source = str(item.get("source", "unknown"))

        if source.endswith("sip/registrations") or source == "sip/registrations":
            count = len(_extract_items(payload))
            events.append(
                {
                    "time": timestamp,
                    "event": "registration_state_observed",
                    "source": source,
                    "details": {"registration_rows": count},
                }
            )
        elif source.endswith("calls/channels") or source == "calls/channels":
            count = len(_extract_items(payload))
            events.append(
                {
                    "time": timestamp,
                    "event": "channel_state_observed",
                    "source": source,
                    "details": {"channel_rows": count},
                }
            )
        elif source.endswith("calls/calls") or source == "calls/calls":
            count = len(_extract_items(payload))
            events.append(
                {
                    "time": timestamp,
                    "event": "call_state_observed",
                    "source": source,
                    "details": {"call_rows": count},
                }
            )
        elif source.endswith("logs/pbx") or source == "logs/pbx":
            count = len(_extract_items(payload))
            events.append(
                {
                    "time": timestamp,
                    "event": "log_window_collected",
                    "source": source,
                    "details": {"log_rows": count},
                }
            )
        elif source.endswith("validation/playbook"):
            status = str(payload.get("status", "unknown"))
            bucket = str(payload.get("bucket", "unknown"))
            events.append(
                {
                    "time": timestamp,
                    "event": "playbook_result_collected",
                    "source": source,
                    "details": {"status": status, "bucket": bucket},
                }
            )
        elif source.endswith("validation/smoke"):
            status = str(payload.get("status", "unknown"))
            events.append(
                {
                    "time": timestamp,
                    "event": "smoke_result_collected",
                    "source": source,
                    "details": {"status": status},
                }
            )
        elif source.endswith("audits/audit_report"):
            score = payload.get("score")
            events.append(
                {
                    "time": timestamp,
                    "event": "audit_result_collected",
                    "source": source,
                    "details": {"score": score},
                }
            )
    events.sort(key=lambda event: str(event.get("time", "")))
    return events


def capture_incident_evidence(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_str(args, "pbx_id")
    evidence_items, failed_sources, warnings = _collect_incident_evidence(ctx, pbx_id=pbx_id, include_integrations=True)
    target = ctx.settings.get_target(pbx_id)
    return {"type": target.type, "id": target.id}, {
        "tool": "telecom.capture_incident_evidence",
        "pbx_id": pbx_id,
        "platform": target.type,
        "summary": f"Collected {len(evidence_items)} incident evidence items.",
        "counts": {"evidence_items": len(evidence_items)},
        "evidence_items": evidence_items,
        "failed_sources": failed_sources,
        "warnings": warnings,
        "captured_at": _now_z(),
    }


def generate_evidence_pack(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_str(args, "pbx_id")
    incident_type = _optional_str(args, "incident_type") or "unspecified_incident"
    incident_id = _optional_str(args, "incident_id") or f"inc-{pbx_id}-{int(time.time())}"
    collector = _optional_str(args, "collector") or "telecom_mcp"
    collection_mode = _optional_str(args, "collection_mode") or "inspect"
    target = ctx.settings.get_target(pbx_id)

    evidence_items, failed_sources, warnings = _collect_incident_evidence(
        ctx, pbx_id=pbx_id, include_integrations=True
    )
    timeline = _timeline_from_evidence(evidence_items)
    integrity_hash = _stable_hash(
        {
            "incident_id": incident_id,
            "pbx_id": pbx_id,
            "platform": target.type,
            "incident_type": incident_type,
            "collection_time": _now_z(),
            "evidence_items": [
                {"evidence_id": item.get("evidence_id"), "hash": item.get("hash")}
                for item in evidence_items
            ],
            "timeline": timeline,
        }
    )

    pack_id = f"pack-{incident_id}"
    pack = {
        "pack_id": pack_id,
        "incident_id": incident_id,
        "pbx_id": pbx_id,
        "platform": target.type,
        "incident_type": incident_type,
        "collection_time": _now_z(),
        "collector": collector,
        "collection_mode": collection_mode,
        "evidence_items": evidence_items,
        "timeline": timeline,
        "integrity_hash": integrity_hash,
        "warnings": warnings,
        "failed_sources": failed_sources,
        "access_log": [
            {"event": "pack_generated", "at": _now_z(), "actor": collector}
        ],
    }
    _EVIDENCE_PACKS[pack_id] = pack
    return {"type": target.type, "id": target.id}, {
        "tool": "telecom.generate_evidence_pack",
        "summary": f"Generated incident evidence pack '{pack_id}'.",
        "pack_id": pack_id,
        "pack": pack,
        "captured_at": _now_z(),
        "warnings": warnings,
    }


def reconstruct_incident_timeline(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    del ctx
    pack_id = _require_str(args, "pack_id")
    pack = _EVIDENCE_PACKS.get(pack_id)
    if not pack:
        raise ToolError(NOT_FOUND, f"Evidence pack '{pack_id}' not found", {"pack_id": pack_id})
    timeline = _timeline_from_evidence(_safe_list(pack.get("evidence_items")))
    pack["timeline"] = timeline
    return {"type": "telecom", "id": pack_id}, {
        "tool": "telecom.reconstruct_incident_timeline",
        "pack_id": pack_id,
        "summary": f"Reconstructed timeline with {len(timeline)} events.",
        "timeline": timeline,
        "warnings": [],
        "captured_at": _now_z(),
    }


def export_evidence_pack(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    del ctx
    pack_id = _require_str(args, "pack_id")
    format_name = (_optional_str(args, "format") or "json").lower()
    if format_name not in {"json", "markdown", "zip"}:
        raise ToolError(
            VALIDATION_ERROR,
            "Unsupported export format",
            {"format": format_name, "allowed": ["json", "markdown", "zip"]},
        )
    pack = _EVIDENCE_PACKS.get(pack_id)
    if not pack:
        raise ToolError(NOT_FOUND, f"Evidence pack '{pack_id}' not found", {"pack_id": pack_id})

    export_payload: Any
    if format_name == "json":
        export_payload = pack
    elif format_name == "markdown":
        lines = [
            "Telecom Incident Evidence Pack",
            "------------------------------",
            f"pack_id: {pack_id}",
            f"incident_id: {pack.get('incident_id')}",
            f"pbx_id: {pack.get('pbx_id')}",
            f"platform: {pack.get('platform')}",
            f"incident_type: {pack.get('incident_type')}",
            f"evidence_items: {len(_safe_list(pack.get('evidence_items')))}",
            f"timeline_events: {len(_safe_list(pack.get('timeline')))}",
            f"integrity_hash: {pack.get('integrity_hash')}",
        ]
        export_payload = "\n".join(lines)
    else:
        export_payload = {
            "pack_id": pack_id,
            "format": "zip",
            "note": "Zip export is represented as manifest payload in this stage.",
            "manifest": {
                "metadata.json": True,
                "summary.md": True,
                "timeline.json": True,
                "evidence_items.json": True,
            },
            "pack": pack,
        }
    return {"type": "telecom", "id": pack_id}, {
        "tool": "telecom.export_evidence_pack",
        "pack_id": pack_id,
        "format": format_name,
        "export": export_payload,
        "captured_at": _now_z(),
        "warnings": [],
    }


_PROBE_CATALOG: dict[str, dict[str, Any]] = {
    "registration_visibility_probe": {
        "probe_id": "registration_visibility_probe",
        "title": "Registration Visibility Probe",
        "purpose": "Validate registration/contact visibility for known test endpoint.",
        "platform_scope": ["asterisk", "freeswitch"],
        "risk_class": "B",
        "requires_validation_mode": False,
        "supports_fixture_mode": True,
        "supports_lab_mode": True,
    },
    "endpoint_reachability_probe": {
        "probe_id": "endpoint_reachability_probe",
        "title": "Endpoint Reachability Probe",
        "purpose": "Validate endpoint availability/reachability signals.",
        "platform_scope": ["asterisk", "freeswitch"],
        "risk_class": "B",
        "requires_validation_mode": False,
        "supports_fixture_mode": True,
        "supports_lab_mode": True,
    },
    "outbound_trunk_probe": {
        "probe_id": "outbound_trunk_probe",
        "title": "Outbound Trunk Probe",
        "purpose": "Run bounded outbound test route probe.",
        "platform_scope": ["asterisk", "freeswitch"],
        "risk_class": "C",
        "requires_validation_mode": True,
        "supports_fixture_mode": True,
        "supports_lab_mode": True,
    },
    "controlled_originate_probe": {
        "probe_id": "controlled_originate_probe",
        "title": "Controlled Originate Probe",
        "purpose": "Run bounded originate probe for test identity.",
        "platform_scope": ["asterisk", "freeswitch"],
        "risk_class": "C",
        "requires_validation_mode": True,
        "supports_fixture_mode": True,
        "supports_lab_mode": True,
    },
    "bridge_formation_probe": {
        "probe_id": "bridge_formation_probe",
        "title": "Bridge Formation Probe",
        "purpose": "Validate bridge/state correlation for controlled test flow.",
        "platform_scope": ["asterisk", "freeswitch"],
        "risk_class": "C",
        "requires_validation_mode": True,
        "supports_fixture_mode": True,
        "supports_lab_mode": True,
    },
    "cleanup_verification_probe": {
        "probe_id": "cleanup_verification_probe",
        "title": "Cleanup Verification Probe",
        "purpose": "Verify no residual probe artifacts remain.",
        "platform_scope": ["asterisk", "freeswitch"],
        "risk_class": "A",
        "requires_validation_mode": False,
        "supports_fixture_mode": True,
        "supports_lab_mode": True,
    },
    "observability_query_probe": {
        "probe_id": "observability_query_probe",
        "title": "Observability Query Probe",
        "purpose": "Validate queryability for logs/channels/registrations/summary.",
        "platform_scope": ["asterisk", "freeswitch"],
        "risk_class": "A",
        "requires_validation_mode": False,
        "supports_fixture_mode": True,
        "supports_lab_mode": True,
    },
    "post_change_validation_probe_suite": {
        "probe_id": "post_change_validation_probe_suite",
        "title": "Post-Change Validation Probe Suite",
        "purpose": "Run smoke + selected probes + cleanup + audit checks after change.",
        "platform_scope": ["asterisk", "freeswitch"],
        "risk_class": "B",
        "requires_validation_mode": False,
        "supports_fixture_mode": True,
        "supports_lab_mode": True,
    },
}


def _probe_phase(phase_id: str, status: str, summary: str) -> dict[str, Any]:
    return {"id": phase_id, "status": status, "summary": summary}


def _target_lab_safe(target: Any) -> bool:
    tags = getattr(target, "tags", None)
    if isinstance(tags, list):
        lowered = {str(tag).strip().lower() for tag in tags}
        if lowered & {"lab", "test", "validation", "safe"}:
            return True
    if getattr(target, "validation_safe", False) is True:
        return True
    return os.getenv("TELECOM_MCP_ALLOW_UNTAGGED_PROBE_TARGETS", "").strip() == "1"


def _validation_mode_enabled(ctx: Any) -> bool:
    mode_value = getattr(getattr(ctx, "mode", None), "value", getattr(ctx, "mode", "inspect"))
    mode_name = str(mode_value).strip().lower()
    return mode_name in {"execute_safe", "execute_full"}


def _probe_gating_eval(
    *,
    ctx: Any,
    target: Any,
    probe_name: str,
    probe_meta: dict[str, Any],
    params: dict[str, Any],
) -> tuple[bool, list[str]]:
    del params
    reasons: list[str] = []
    if target.type not in _safe_list(probe_meta.get("platform_scope")):
        reasons.append("Probe is not supported for target platform.")
    risk_class = str(probe_meta.get("risk_class", "B"))
    requires_validation_mode = bool(probe_meta.get("requires_validation_mode", False))
    if requires_validation_mode and not _validation_mode_enabled(ctx):
        reasons.append("Probe requires execute_safe/execute_full mode.")
    if risk_class == "C":
        if not _active_probes_enabled():
            reasons.append("Class C probe requires TELECOM_MCP_ENABLE_ACTIVE_PROBES=1.")
        if not _target_lab_safe(target):
            reasons.append("Class C probe requires lab/test-safe target tagging.")
    return len(reasons) == 0, reasons


def _probe_rollup_status(phases: list[dict[str, Any]]) -> str:
    statuses = [str(phase.get("status", "failed")) for phase in phases]
    return _rollup_status(statuses)


def _probe_summary(name: str, status: str) -> str:
    if status == "passed":
        return f"{name} completed successfully with cleanup and evidence capture."
    if status == "warning":
        return f"{name} completed with warnings; inspect phases/evidence."
    return f"{name} failed; inspect gating/action/assertion phases."


def _run_probe_registration_visibility(
    ctx: Any, pbx_id: str, params: dict[str, Any], failed_sources: list[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any], list[str], list[dict[str, Any]]]:
    endpoint = _optional_str(params, "endpoint")
    phases: list[dict[str, Any]] = []
    warnings: list[str] = []
    evidence: dict[str, Any] = {}

    endpoints_payload = _call_internal(
        ctx,
        "telecom.endpoints",
        {"pbx_id": pbx_id, "filter": {"contains": endpoint} if endpoint else {}, "limit": 300},
        failed_sources=failed_sources,
    )
    registrations_payload = _call_internal(
        ctx,
        "telecom.registrations",
        {"pbx_id": pbx_id, "limit": 500},
        failed_sources=failed_sources,
    )
    endpoint_items = _extract_items(endpoints_payload)
    registration_items = _extract_items(registrations_payload)
    visible = bool(endpoint_items) and bool(registration_items)
    status = "passed" if visible else "warning"
    phases.append(
        _probe_phase(
            "execute",
            "passed" if endpoints_payload or registrations_payload else "failed",
            "Collected endpoint and registration visibility data.",
        )
    )
    phases.append(
        _probe_phase(
            "assert",
            status,
            "Endpoint/registration visibility is consistent." if visible else "Visibility is stale, unavailable, or inconsistent.",
        )
    )
    evidence = {
        "endpoint": endpoint,
        "endpoint_count": len(endpoint_items),
        "registration_count": len(registration_items),
        "classification": "visible" if visible else "inconsistent",
    }
    if failed_sources:
        warnings.append("Probe evidence is partial due to subcall failures.")
    return {"status": status}, evidence, warnings, phases


def _run_probe_endpoint_reachability(
    ctx: Any, pbx_id: str, params: dict[str, Any], failed_sources: list[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any], list[str], list[dict[str, Any]]]:
    endpoint = _optional_str(params, "endpoint")
    warnings: list[str] = []
    phases: list[dict[str, Any]] = []
    health_tool = "asterisk.health" if ctx.settings.get_target(pbx_id).type == "asterisk" else "freeswitch.health"
    health_payload = _call_internal(ctx, health_tool, {"pbx_id": pbx_id}, failed_sources=failed_sources)
    endpoints_payload = _call_internal(
        ctx,
        "telecom.endpoints",
        {"pbx_id": pbx_id, "filter": {"contains": endpoint} if endpoint else {}, "limit": 300},
        failed_sources=failed_sources,
    )
    endpoint_items = _extract_items(endpoints_payload)
    reachable = bool(endpoint_items)
    phases.append(_probe_phase("execute", "passed" if health_payload else "failed", "Health and endpoint query executed."))
    phases.append(_probe_phase("assert", "passed" if reachable else "warning", "Endpoint appears reachable." if reachable else "Endpoint appears unavailable."))
    if failed_sources:
        warnings.append("Probe evidence is partial due to subcall failures.")
    return {"status": "passed" if reachable else "warning"}, {
        "endpoint": endpoint,
        "health_ok": bool(health_payload),
        "endpoint_rows": len(endpoint_items),
    }, warnings, phases


def _run_probe_observability_query(
    ctx: Any, pbx_id: str, failed_sources: list[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any], list[str], list[dict[str, Any]]]:
    warnings: list[str] = []
    phases: list[dict[str, Any]] = []
    summary_payload = _call_internal(ctx, "telecom.summary", {"pbx_id": pbx_id}, failed_sources=failed_sources)
    regs_payload = _call_internal(ctx, "telecom.registrations", {"pbx_id": pbx_id, "limit": 200}, failed_sources=failed_sources)
    channels_payload = _call_internal(ctx, "telecom.channels", {"pbx_id": pbx_id, "limit": 200}, failed_sources=failed_sources)
    logs_payload = _call_internal(ctx, "telecom.logs", {"pbx_id": pbx_id, "tail": 100}, failed_sources=failed_sources)
    complete = all([summary_payload, regs_payload, channels_payload, logs_payload])
    phases.append(_probe_phase("execute", "passed" if any([summary_payload, regs_payload, channels_payload, logs_payload]) else "failed", "Collected observability surfaces."))
    phases.append(_probe_phase("assert", "passed" if complete else "warning", "Observability surfaces are fully queryable." if complete else "One or more observability surfaces unavailable."))
    if failed_sources:
        warnings.append("Incomplete telemetry reported as warning.")
    return {"status": "passed" if complete else "warning"}, {
        "summary": bool(summary_payload),
        "registrations": bool(regs_payload),
        "channels": bool(channels_payload),
        "logs": bool(logs_payload),
    }, warnings, phases


def _run_probe_cleanup_verification(
    ctx: Any, pbx_id: str, params: dict[str, Any], failed_sources: list[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any], list[str], list[dict[str, Any]]]:
    probe_id = _optional_str(params, "probe_id")
    warnings: list[str] = []
    phases: list[dict[str, Any]] = []
    args: dict[str, Any] = {"pbx_id": pbx_id}
    if probe_id:
        args["probe_id"] = probe_id
    cleanup_payload = _call_internal(ctx, "telecom.verify_cleanup", args, failed_sources=failed_sources)
    clean = bool(cleanup_payload.get("clean")) if isinstance(cleanup_payload, dict) else False
    phases.append(_probe_phase("cleanup", "passed" if clean else "warning", "Cleanup verification passed." if clean else "Cleanup verification reported residuals."))
    if failed_sources:
        warnings.append("Cleanup evidence is partial.")
    return {"status": "passed" if clean else "warning"}, {"clean": clean, "probe_id": probe_id}, warnings, phases


def _run_probe_active_route(
    ctx: Any,
    *,
    pbx_id: str,
    probe_name: str,
    params: dict[str, Any],
    failed_sources: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], list[str], list[dict[str, Any]]]:
    warnings: list[str] = []
    phases: list[dict[str, Any]] = []
    destination = _optional_str(params, "destination") or _optional_str(params, "endpoint") or "1001"
    timeout_s = _positive_int_arg(params, "timeout_s", default=20, max_value=60)
    if probe_name == "outbound_trunk_probe":
        action_tool = "telecom.run_trunk_probe"
    else:
        action_tool = "telecom.run_registration_probe"
    action_payload = _call_internal(
        ctx,
        action_tool,
        {"pbx_id": pbx_id, "destination": destination, "timeout_s": timeout_s},
        failed_sources=failed_sources,
    )
    action_ok = bool(action_payload)
    phases.append(_probe_phase("execute", "passed" if action_ok else "failed", "Active probe action executed." if action_ok else "Active probe action failed."))

    logs_payload = _call_internal(
        ctx,
        "telecom.logs",
        {"pbx_id": pbx_id, "grep": destination, "tail": 150},
        failed_sources=failed_sources,
    )
    channels_payload = _call_internal(
        ctx,
        "telecom.channels",
        {"pbx_id": pbx_id, "limit": 200},
        failed_sources=failed_sources,
    )
    evidence_seen = bool(logs_payload) or bool(channels_payload)
    phases.append(_probe_phase("assert", "passed" if evidence_seen else "warning", "Expected runtime evidence observed." if evidence_seen else "Expected runtime evidence not clearly observed."))

    cleanup_payload = _call_internal(
        ctx, "telecom.verify_cleanup", {"pbx_id": pbx_id}, failed_sources=failed_sources
    )
    clean = bool(cleanup_payload.get("clean")) if isinstance(cleanup_payload, dict) else False
    phases.append(_probe_phase("cleanup", "passed" if clean else "warning", "Cleanup verification passed." if clean else "Cleanup verification indicated residual artifacts."))

    if failed_sources:
        warnings.append("Active probe evidence is partial due to subcall failures.")
    status = _probe_rollup_status(phases)
    return {"status": status}, {
        "destination": destination,
        "action_tool": action_tool,
        "action_ok": action_ok,
        "evidence_seen": evidence_seen,
        "cleanup_clean": clean,
    }, warnings, phases


def _run_probe_bridge_formation(
    ctx: Any, pbx_id: str, params: dict[str, Any], failed_sources: list[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any], list[str], list[dict[str, Any]]]:
    result, evidence, warnings, phases = _run_probe_active_route(
        ctx,
        pbx_id=pbx_id,
        probe_name="controlled_originate_probe",
        params=params,
        failed_sources=failed_sources,
    )
    if ctx.settings.get_target(pbx_id).type == "asterisk":
        bridges_payload = _call_internal(
            ctx, "asterisk.bridges", {"pbx_id": pbx_id, "limit": 200}, failed_sources=failed_sources
        )
        bridge_count = len(_extract_items(bridges_payload))
        bridge_seen = bridge_count > 0
    else:
        bridge_seen = bool(_call_internal(ctx, "freeswitch.calls", {"pbx_id": pbx_id, "limit": 200}, failed_sources=failed_sources))
        bridge_count = 1 if bridge_seen else 0
    phases.append(_probe_phase("assert-bridge", "passed" if bridge_seen else "warning", "Bridge/call correlation observed." if bridge_seen else "No bridge/call correlation observed."))
    evidence["bridge_count"] = bridge_count
    result["status"] = _probe_rollup_status(phases)
    return result, evidence, warnings, phases


def _run_probe_post_change_suite(
    ctx: Any, pbx_id: str, params: dict[str, Any], failed_sources: list[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any], list[str], list[dict[str, Any]]]:
    warnings: list[str] = []
    phases: list[dict[str, Any]] = []
    include_active = _bool_arg(params, "include_active", default=False)
    smoke_payload = _call_internal(
        ctx,
        "telecom.run_smoke_suite",
        {"name": "baseline_read_only_smoke", "pbx_id": pbx_id},
        failed_sources=failed_sources,
    )
    phases.append(_probe_phase("precheck", "passed" if smoke_payload else "failed", "Baseline smoke executed before post-change validation."))

    active_result: dict[str, Any] = {}
    if include_active:
        active_result, _active_evidence, active_warnings, active_phases = _run_probe_active_route(
            ctx,
            pbx_id=pbx_id,
            probe_name="controlled_originate_probe",
            params=params,
            failed_sources=failed_sources,
        )
        phases.extend(active_phases)
        warnings.extend(active_warnings)
    else:
        phases.append(_probe_phase("execute", "passed", "Active validation skipped by configuration."))

    cleanup_payload = _call_internal(
        ctx, "telecom.verify_cleanup", {"pbx_id": pbx_id}, failed_sources=failed_sources
    )
    phases.append(_probe_phase("cleanup", "passed" if cleanup_payload else "warning", "Cleanup verification executed."))

    audit_payload = _call_internal(ctx, "telecom.audit_target", {"pbx_id": pbx_id}, failed_sources=failed_sources)
    phases.append(_probe_phase("postcheck", "passed" if audit_payload else "warning", "Post-change audit check executed."))
    if failed_sources:
        warnings.append("Post-change validation contains partial evidence.")
    return {"status": _probe_rollup_status(phases)}, {
        "include_active": include_active,
        "baseline_smoke": bool(smoke_payload),
        "active_status": active_result.get("status") if active_result else "skipped",
        "cleanup": bool(cleanup_payload),
        "audit": bool(audit_payload),
    }, warnings, phases


def list_probes(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    del ctx, args
    probes = []
    for name, meta in sorted(_PROBE_CATALOG.items()):
        item = dict(meta)
        item["name"] = name
        probes.append(item)
    return {"type": "telecom", "id": "probe-catalog"}, {
        "tool": "telecom.list_probes",
        "summary": f"{len(probes)} probes available.",
        "probes": probes,
        "captured_at": _now_z(),
        "warnings": [],
    }


def run_probe(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    name = _require_str(args, "name").strip().lower()
    pbx_id = _require_str(args, "pbx_id")
    params = _dict_arg(args, "params")
    meta = _PROBE_CATALOG.get(name)
    if not meta:
        raise ToolError(
            VALIDATION_ERROR,
            "Unsupported probe",
            {"name": name, "allowed_probes": sorted(_PROBE_CATALOG)},
        )

    target = ctx.settings.get_target(pbx_id)
    allowed, gating_reasons = _probe_gating_eval(
        ctx=ctx, target=target, probe_name=name, probe_meta=meta, params=params
    )
    mode_value = getattr(getattr(ctx, "mode", None), "value", getattr(ctx, "mode", "inspect"))
    mode_name = str(mode_value).strip().lower()
    phases: list[dict[str, Any]] = []
    warnings: list[str] = []
    failed_sources: list[dict[str, Any]] = []

    pre_smoke = _call_internal(
        ctx,
        "telecom.run_smoke_suite",
        {"name": "baseline_read_only_smoke", "pbx_id": pbx_id},
        failed_sources=failed_sources,
    )
    pre_snapshot = _call_internal(
        ctx, "telecom.capture_snapshot", {"pbx_id": pbx_id}, failed_sources=failed_sources
    )
    if pre_smoke and pre_snapshot:
        phases.append(_probe_phase("precheck", "passed", "Safety prechecks and baseline capture succeeded."))
    else:
        phases.append(_probe_phase("precheck", "warning", "Precheck evidence is partial."))

    if not allowed:
        phases.append(_probe_phase("gating", "failed", "; ".join(gating_reasons)))
        return {"type": target.type, "id": target.id}, {
            "probe": name,
            "pbx_id": pbx_id,
            "platform": target.type,
            "mode": mode_name,
            "status": "failed",
            "summary": "Probe blocked by safety gating.",
            "phases": phases,
            "evidence": {"pre_smoke": bool(pre_smoke), "pre_snapshot": bool(pre_snapshot)},
            "warnings": warnings,
            "gating_failures": gating_reasons,
            "captured_at": _now_z(),
        }

    phases.append(_probe_phase("gating", "passed", "Probe gating checks passed."))
    result: dict[str, Any]
    evidence: dict[str, Any]
    probe_warnings: list[str]
    probe_phases: list[dict[str, Any]]
    if name == "registration_visibility_probe":
        result, evidence, probe_warnings, probe_phases = _run_probe_registration_visibility(
            ctx, pbx_id, params, failed_sources
        )
    elif name == "endpoint_reachability_probe":
        result, evidence, probe_warnings, probe_phases = _run_probe_endpoint_reachability(
            ctx, pbx_id, params, failed_sources
        )
    elif name == "observability_query_probe":
        result, evidence, probe_warnings, probe_phases = _run_probe_observability_query(
            ctx, pbx_id, failed_sources
        )
    elif name == "cleanup_verification_probe":
        result, evidence, probe_warnings, probe_phases = _run_probe_cleanup_verification(
            ctx, pbx_id, params, failed_sources
        )
    elif name in {"outbound_trunk_probe", "controlled_originate_probe"}:
        result, evidence, probe_warnings, probe_phases = _run_probe_active_route(
            ctx, pbx_id=pbx_id, probe_name=name, params=params, failed_sources=failed_sources
        )
    elif name == "bridge_formation_probe":
        result, evidence, probe_warnings, probe_phases = _run_probe_bridge_formation(
            ctx, pbx_id, params, failed_sources
        )
    else:
        result, evidence, probe_warnings, probe_phases = _run_probe_post_change_suite(
            ctx, pbx_id, params, failed_sources
        )
    phases.extend(probe_phases)
    warnings.extend(probe_warnings)

    post_smoke = _call_internal(
        ctx,
        "telecom.run_smoke_suite",
        {"name": "registration_visibility_smoke", "pbx_id": pbx_id},
        failed_sources=failed_sources,
    )
    post_audit = _call_internal(ctx, "telecom.audit_target", {"pbx_id": pbx_id}, failed_sources=failed_sources)
    if post_smoke or post_audit:
        phases.append(_probe_phase("postcheck", "passed", "Post-probe smoke/audit checks collected."))
    else:
        phases.append(_probe_phase("postcheck", "warning", "Post-probe checks are unavailable."))

    status = result.get("status", _probe_rollup_status(phases))
    status = _probe_rollup_status(phases + [_probe_phase("result", str(status), "")])
    if failed_sources:
        warnings.append("Probe run captured partial evidence due to failed subcalls.")

    return {"type": target.type, "id": target.id}, {
        "probe": name,
        "pbx_id": pbx_id,
        "platform": target.type,
        "mode": mode_name,
        "status": status,
        "summary": _probe_summary(name, status),
        "phases": phases,
        "evidence": {
            **evidence,
            "pre_smoke": bool(pre_smoke),
            "pre_snapshot": bool(pre_snapshot),
            "post_smoke": bool(post_smoke),
            "post_audit": bool(post_audit),
        },
        "warnings": warnings,
        "gating_failures": [],
        "failed_sources": failed_sources,
        "captured_at": _now_z(),
    }
