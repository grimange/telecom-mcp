"""Cross-platform telecom tools."""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
import time
from typing import Any

from ..errors import NOT_ALLOWED, UPSTREAM_ERROR, VALIDATION_ERROR, ToolError

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
