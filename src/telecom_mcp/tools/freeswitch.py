"""FreeSWITCH tool implementations."""

from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path
import re
import time
from typing import Any

from ..authz import Mode
from ..connectors.freeswitch_esl import FreeSWITCHESLConnector
from ..execution import active_operation_controller
from ..errors import (
    AUTH_FAILED,
    CONNECTION_FAILED,
    NOT_ALLOWED,
    NOT_FOUND,
    TIMEOUT,
    UPSTREAM_ERROR,
    VALIDATION_ERROR,
    ToolError,
)
from ..freeswitch_events import max_event_buffer_capacity, max_recent_events_return_limit
from ..normalize import freeswitch as norm
from ..safety import require_active_target_lab_safe, validate_probe_destination

_LOG_LEVELS = {"debug", "info", "notice", "warning", "error", "critical"}
_API_SAFE_EXACT = {
    "status",
    "version",
    "show channels",
    "show calls",
    "sofia status",
}
_API_SAFE_PATTERNS = (
    re.compile(r"^sofia status profile [A-Za-z0-9_.-]+$"),
    re.compile(r"^sofia status profile [A-Za-z0-9_.-]+ reg$"),
    re.compile(r"^sofia status gateway [A-Za-z0-9_.-]+$"),
    re.compile(r"^uuid_dump [A-Za-z0-9_.-]+$"),
)
def _require_pbx_id(args: dict[str, Any]) -> str:
    pbx_id = args.get("pbx_id")
    if not isinstance(pbx_id, str) or not pbx_id:
        raise ToolError(VALIDATION_ERROR, "Field 'pbx_id' must be a non-empty string")
    return pbx_id


def _connector(ctx: Any, pbx_id: str) -> tuple[Any, FreeSWITCHESLConnector]:
    target = ctx.settings.get_target(pbx_id)
    if target.type != "freeswitch":
        raise ToolError(NOT_FOUND, f"Target is not a FreeSWITCH system: {pbx_id}")
    if not target.esl:
        raise ToolError(
            NOT_FOUND, f"FreeSWITCH target missing ESL configuration: {pbx_id}"
        )
    return target, FreeSWITCHESLConnector(
        target.esl, timeout_s=ctx.remaining_timeout_s()
    )


def _require_str(args: dict[str, Any], key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value:
        raise ToolError(VALIDATION_ERROR, f"Field '{key}' must be a non-empty string")
    return value


def _positive_int_arg(
    args: dict[str, Any], key: str, *, default: int, max_value: int
) -> int:
    value = args.get(key, default)
    if not isinstance(value, int) or value < 1:
        raise ToolError(VALIDATION_ERROR, f"Field '{key}' must be a positive integer")
    return min(value, max_value)


def _bool_arg(args: dict[str, Any], key: str, *, default: bool = False) -> bool:
    value = args.get(key, default)
    if isinstance(value, bool):
        return value
    raise ToolError(VALIDATION_ERROR, f"Field '{key}' must be a boolean")


def _observed_at() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_log_lines(
    *,
    path: str,
    grep: str | None,
    tail: int,
    level: str | None,
) -> tuple[list[dict[str, Any]], bool]:
    log_path = Path(path)
    if not log_path.is_file():
        raise ToolError(
            NOT_FOUND,
            "Configured log file not found",
            {"path": str(log_path)},
        )
    raw_lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    matched: list[str] = []
    for line in raw_lines:
        if grep and grep not in line:
            continue
        if level and level not in line.lower():
            continue
        matched.append(line)
    truncated = len(matched) > tail
    tail_lines = matched[-tail:]
    items = [{"line_no": index + 1, "message": text} for index, text in enumerate(tail_lines)]
    return items, truncated


def _validate_esl_mutation_response(raw: str, *, command: str) -> None:
    lowered = raw.lower()
    if "-err" in lowered:
        if "permission denied" in lowered or "not allowed" in lowered:
            raise ToolError(
                NOT_ALLOWED,
                "FreeSWITCH command not allowed",
                {"command": command, "output_sample": raw[:200]},
            )
        raise ToolError(
            UPSTREAM_ERROR,
            "FreeSWITCH command reported an error",
            {"command": command, "output_sample": raw[:200]},
        )


def _validate_esl_read_response(raw: str, *, command: str) -> None:
    cleaned = raw.strip()
    if not cleaned:
        raise ToolError(
            UPSTREAM_ERROR,
            "FreeSWITCH read command returned an empty payload",
            {"command": command},
        )
    lowered_clean = cleaned.lower()
    if lowered_clean == "+ok accepted":
        raise ToolError(
            UPSTREAM_ERROR,
            "FreeSWITCH read command returned an auth control payload",
            {"command": command, "output_sample": raw[:200]},
        )
    if "content-type:" in lowered_clean:
        raise ToolError(
            UPSTREAM_ERROR,
            "FreeSWITCH read command returned an unparsed ESL envelope",
            {"command": command, "output_sample": raw[:200]},
        )
    if lowered_clean.splitlines()[0:1] == ["accepted"]:
        raise ToolError(
            UPSTREAM_ERROR,
            "FreeSWITCH read command returned an auth control payload",
            {"command": command, "output_sample": raw[:200]},
        )

    lowered = raw.lower()
    if "-err" not in lowered:
        return
    details = {"command": command, "output_sample": raw[:200]}
    if "permission denied" in lowered or "not allowed" in lowered:
        raise ToolError(NOT_ALLOWED, "FreeSWITCH read command not allowed", details)
    if "not found" in lowered or "invalid profile" in lowered or "no such" in lowered:
        raise ToolError(NOT_FOUND, "FreeSWITCH read resource not found", details)
    raise ToolError(UPSTREAM_ERROR, "FreeSWITCH read command reported an error", details)


def _validate_api_command(command: str) -> str:
    cleaned = " ".join(command.strip().split())
    lowered = cleaned.lower()
    if lowered in _API_SAFE_EXACT:
        return cleaned
    for pattern in _API_SAFE_PATTERNS:
        if pattern.match(lowered):
            return cleaned
    raise ToolError(
        NOT_ALLOWED,
        "FreeSWITCH API command is not in the read-only allowlist",
        {
            "command": command,
            "allowlist_exact": sorted(_API_SAFE_EXACT),
            "allowlist_patterns": [p.pattern for p in _API_SAFE_PATTERNS],
        },
    )


def _parse_key_value_lines(raw: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in raw.replace("\r", "").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        parsed[key] = value
    return parsed


def _parse_version_value(raw: str) -> str:
    cleaned = raw.replace("\r", " ").replace("\n", " ").strip()
    match = re.search(r"FreeSWITCH(?:\s+Version)?\s+([0-9][0-9A-Za-z_.-]*)", cleaned)
    return match.group(1) if match else "unknown"


def _sofia_status_with_fallback(esl: FreeSWITCHESLConnector) -> tuple[str, dict[str, Any]]:
    primary_raw = esl.api("sofia status")
    _validate_esl_read_response(primary_raw, command="sofia status")
    normalized = norm.normalize_sofia_status(primary_raw)
    if normalized.get("profiles") or normalized.get("gateways"):
        return primary_raw, normalized

    fallback_chunks: list[str] = []
    for profile in ("internal", "external"):
        cmd = f"sofia status profile {profile}"
        chunk = esl.api(cmd)
        _validate_esl_read_response(chunk, command=cmd)
        fallback_chunks.append(chunk)
    fallback_raw = "\n".join(fallback_chunks).strip()
    fallback_normalized = norm.normalize_sofia_status(fallback_raw)
    if fallback_normalized.get("profiles") or fallback_normalized.get("gateways"):
        return fallback_raw, fallback_normalized
    raise ToolError(
        UPSTREAM_ERROR,
        "Sofia profile discovery returned no structured profile data",
        {"commands": ["sofia status", "sofia status profile internal", "sofia status profile external"]},
    )


def _classify_read_failure(exc: ToolError) -> str:
    if exc.code in {CONNECTION_FAILED, TIMEOUT}:
        details = exc.details or {}
        command = str(details.get("cmd") or details.get("command") or "").strip().lower()
        if command in {"greeting", "auth"}:
            return "esl_unreachable"
        return "target_unreachable"
    if exc.code == AUTH_FAILED:
        return "auth_failed"
    if exc.code == NOT_FOUND:
        return "command_unavailable"
    details = exc.details or {}
    message = exc.message.lower()
    sample = str(details.get("output_sample") or "").lower()
    if "no structured" in message:
        return "parse_failed"
    if "not found" in sample or "invalid profile" in sample or "no such" in sample:
        return "command_unavailable"
    return "command_failed"


def _read_command_status(data_quality: dict[str, Any] | None = None) -> tuple[bool, str]:
    if not isinstance(data_quality, dict):
        return True, "ok"
    result_kind = str(data_quality.get("result_kind", "ok")).strip().lower()
    if result_kind == "empty_valid":
        return True, "empty_valid"
    if result_kind == "parse_failed":
        return False, "parse_failed"
    return True, "ok"


def _build_read_result(
    *,
    tool_name: str,
    target: Any,
    payload: dict[str, Any],
    source_command: str | list[str],
    include_raw: bool,
    raw_payload: str | dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    degraded: bool = False,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    observed_at = _observed_at()
    warning_items = list(warnings or [])
    payload_copy = dict(payload)
    data_quality = payload_copy.get("data_quality")
    command_ok, command_status = _read_command_status(
        data_quality if isinstance(data_quality, dict) else None
    )
    result = {
        "ok": not error and command_ok,
        "tool": tool_name,
        "target": {"type": target.type, "id": target.id},
        "observed_at": observed_at,
        "transport": {"kind": "esl", "ok": True, "status": "reachable"},
        "auth": {"ok": True, "status": "authenticated"},
        "command": {
            "name": source_command,
            "ok": not error and command_ok,
            "status": command_status if not error else "error",
        },
        "payload": payload_copy,
        "warnings": warning_items,
        "error": error,
        "degraded": degraded or bool(error) or command_status == "parse_failed",
    }
    if include_raw and raw_payload is not None:
        result["raw"] = {"esl": raw_payload}
    if "raw" in payload_copy and not include_raw:
        payload_copy.pop("raw", None)
    result.update(payload_copy)
    return result


def _build_capability_status(*, supported: bool, available: bool, reason: str | None = None) -> dict[str, Any]:
    status = {"supported": supported, "available": available}
    if reason:
        status["reason"] = reason
    return status


def _event_monitor(ctx: Any, pbx_id: str) -> Any:
    monitor_getter = getattr(ctx.server, "get_freeswitch_event_monitor", None)
    if not callable(monitor_getter):
        raise ToolError(
            UPSTREAM_ERROR,
            "FreeSWITCH event monitor runtime is unavailable",
            {"pbx_id": pbx_id},
        )
    return monitor_getter(pbx_id)


def _normalize_event_names_arg(args: dict[str, Any]) -> set[str] | None:
    value = args.get("event_names")
    if value is None:
        return None
    if isinstance(value, list):
        parsed = {str(item).strip() for item in value if str(item).strip()}
        return parsed or None
    raise ToolError(
        VALIDATION_ERROR,
        "Field 'event_names' must be a list of non-empty strings",
    )


def health(ctx: Any, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    include_raw = _bool_arg(args, "include_raw", default=False)
    target, esl = _connector(ctx, pbx_id)
    warnings: list[str] = []
    sofia_raw: str | None = None
    sofia: dict[str, Any] = {"profiles": []}
    try:
        ping = esl.ping()
        version_text = esl.api("version")
        ping_raw = str(ping.get("raw", ""))
        _validate_esl_read_response(ping_raw, command="status")
        _validate_esl_read_response(version_text, command="version")
        try:
            sofia_raw, sofia = _sofia_status_with_fallback(esl)
        except ToolError as exc:
            warnings.append(
                f"Sofia discovery degraded during health check: {_classify_read_failure(exc)}."
            )
    finally:
        esl.close()
    version = _parse_version_value(version_text)
    payload = norm.normalize_health(
        latency_ms=int(ping.get("latency_ms", 0)),
        version=version,
        profiles=sofia.get("profiles", []),
    )
    payload["data_quality"] = {
        "completeness": "partial" if warnings else "full",
        "issues": warnings,
        "result_kind": "degraded" if warnings else "ok",
    }
    raw_payload: dict[str, Any] | None = None
    if include_raw:
        raw_payload = {
            "status": ping_raw,
            "version": version_text,
        }
        if sofia_raw is not None:
            raw_payload["sofia_status"] = sofia_raw
    return {"type": target.type, "id": target.id}, _build_read_result(
        tool_name="freeswitch.health",
        target=target,
        payload=payload,
        source_command=["status", "version", "sofia status"],
        include_raw=include_raw,
        raw_payload=raw_payload,
        warnings=warnings,
        degraded=bool(warnings),
    )


def sofia_status(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    include_raw = _bool_arg(args, "include_raw", default=False)
    profile = args.get("profile")
    target, esl = _connector(ctx, pbx_id)
    try:
        if isinstance(profile, str) and profile:
            cmd = f"sofia status profile {profile}"
            raw = esl.api(cmd)
            normalized = norm.normalize_sofia_status(raw)
        else:
            cmd = "sofia status"
            raw, normalized = _sofia_status_with_fallback(esl)
    finally:
        esl.close()
    _validate_esl_read_response(raw, command=cmd)
    return {"type": target.type, "id": target.id}, _build_read_result(
        tool_name="freeswitch.sofia_status",
        target=target,
        payload=normalized,
        source_command=cmd,
        include_raw=include_raw,
        raw_payload=raw,
        warnings=list(normalized.get("data_quality", {}).get("issues", [])),
        degraded=str(normalized.get("data_quality", {}).get("completeness", "full")) != "full",
    )


def channels(ctx: Any, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    include_raw = _bool_arg(args, "include_raw", default=False)
    limit = _positive_int_arg(args, "limit", default=200, max_value=2000)

    target, esl = _connector(ctx, pbx_id)
    try:
        raw = esl.api("show channels")
    finally:
        esl.close()
    _validate_esl_read_response(raw, command="show channels")

    payload = norm.normalize_channels([], limit, raw)
    return {"type": target.type, "id": target.id}, _build_read_result(
        tool_name="freeswitch.channels",
        target=target,
        payload=payload,
        source_command="show channels",
        include_raw=include_raw,
        raw_payload=raw,
        warnings=list(payload.get("data_quality", {}).get("issues", [])),
        degraded=str(payload.get("data_quality", {}).get("completeness", "full")) != "full",
    )


def registrations(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    include_raw = _bool_arg(args, "include_raw", default=False)
    profile = args.get("profile")
    limit = _positive_int_arg(args, "limit", default=200, max_value=2000)

    target, esl = _connector(ctx, pbx_id)
    cmd = "sofia status profile internal reg"
    if isinstance(profile, str) and profile:
        cmd = f"sofia status profile {profile} reg"
    try:
        raw = esl.api(cmd)
    finally:
        esl.close()
    _validate_esl_read_response(raw, command=cmd)
    payload = norm.normalize_registrations([], limit, raw)
    return {"type": target.type, "id": target.id}, _build_read_result(
        tool_name="freeswitch.registrations",
        target=target,
        payload=payload,
        source_command=cmd,
        include_raw=include_raw,
        raw_payload=raw,
        warnings=list(payload.get("data_quality", {}).get("issues", [])),
        degraded=str(payload.get("data_quality", {}).get("completeness", "full")) != "full",
    )


def gateway_status(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    include_raw = _bool_arg(args, "include_raw", default=False)
    gateway = _require_str(args, "gateway")
    target, esl = _connector(ctx, pbx_id)
    try:
        raw = esl.api(f"sofia status gateway {gateway}")
    finally:
        esl.close()
    _validate_esl_read_response(raw, command=f"sofia status gateway {gateway}")
    payload = norm.normalize_gateway_status(gateway, raw)
    return {"type": target.type, "id": target.id}, _build_read_result(
        tool_name="freeswitch.gateway_status",
        target=target,
        payload=payload,
        source_command=f"sofia status gateway {gateway}",
        include_raw=include_raw,
        raw_payload=raw,
    )


def calls(ctx: Any, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    include_raw = _bool_arg(args, "include_raw", default=False)
    limit = _positive_int_arg(args, "limit", default=200, max_value=2000)

    target, esl = _connector(ctx, pbx_id)
    try:
        raw = esl.api("show calls")
    finally:
        esl.close()
    _validate_esl_read_response(raw, command="show calls")
    payload = norm.normalize_calls([], limit, raw)
    return {"type": target.type, "id": target.id}, _build_read_result(
        tool_name="freeswitch.calls",
        target=target,
        payload=payload,
        source_command="show calls",
        include_raw=include_raw,
        raw_payload=raw,
        warnings=list(payload.get("data_quality", {}).get("issues", [])),
        degraded=str(payload.get("data_quality", {}).get("completeness", "full")) != "full",
    )


def channel_details(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    include_raw = _bool_arg(args, "include_raw", default=False)
    channel_uuid = _require_str(args, "uuid")
    target, esl = _connector(ctx, pbx_id)
    command = f"uuid_dump {channel_uuid}"
    try:
        raw = esl.api(command)
    finally:
        esl.close()
    _validate_esl_read_response(raw, command=command)
    fields = _parse_key_value_lines(raw)
    if not fields:
        raise ToolError(
            NOT_FOUND,
            "FreeSWITCH channel details not found",
            {"uuid": channel_uuid, "command": command},
        )
    payload = {
        "channel_id": channel_uuid,
        "uuid": channel_uuid,
        "name": fields.get("Channel-Name", ""),
        "state": (
            fields.get("Channel-Call-State")
            or fields.get("Channel-State")
            or fields.get("Answer-State")
            or "Unknown"
        ),
        "caller": fields.get("Caller-Caller-ID-Number", ""),
        "callee": fields.get("Caller-Destination-Number", ""),
        "data_quality": {"completeness": "full", "issues": [], "result_kind": "ok"},
    }
    return {"type": target.type, "id": target.id}, _build_read_result(
        tool_name="freeswitch.channel_details",
        target=target,
        payload=payload,
        source_command=command,
        include_raw=include_raw,
        raw_payload=raw,
    )


def reloadxml(ctx: Any, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    target, esl = _connector(ctx, pbx_id)
    command = "reloadxml"
    try:
        response = esl.api(command)
    finally:
        esl.close()
    _validate_esl_mutation_response(response, command=command)
    return {"type": target.type, "id": target.id}, {"reloaded": True}


def originate_probe(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    destination = validate_probe_destination(_require_str(args, "destination"))
    timeout_s = _positive_int_arg(args, "timeout_s", default=20, max_value=60)
    probe_id_arg = args.get("probe_id")
    probe_id = (
        probe_id_arg.strip()
        if isinstance(probe_id_arg, str) and probe_id_arg.strip()
        else f"probe-{pbx_id}-{int(time.time())}"
    )
    if os.getenv("TELECOM_MCP_ENABLE_ACTIVE_PROBES", "").strip() != "1":
        raise ToolError(
            NOT_ALLOWED,
            "Active probes are disabled; set TELECOM_MCP_ENABLE_ACTIVE_PROBES=1",
            {"required_env": "TELECOM_MCP_ENABLE_ACTIVE_PROBES"},
        )
    target, esl = _connector(ctx, pbx_id)
    require_active_target_lab_safe(target, tool_name="freeswitch.originate_probe")
    command = (
        "originate "
        "{ignore_early_media=true,origination_caller_id_name="
        + probe_id
        + ",origination_caller_id_number="
        + probe_id
        + ",sip_h_X-Telecom-Mcp-Probe-Id="
        + probe_id
        + ",originate_timeout="
        + str(timeout_s)
        + "}sofia/internal/"
        + destination
        + " &park()"
    )
    try:
        with active_operation_controller.guard(
            operation="freeswitch.originate_probe",
            pbx_id=pbx_id,
        ):
            response = esl.api(command)
    finally:
        esl.close()
    _validate_esl_mutation_response(response, command=command)
    return {"type": target.type, "id": target.id}, {
        "probe_id": probe_id,
        "destination": destination,
        "platform": "freeswitch",
        "initiated": True,
        "timeout_s": timeout_s,
        "source_command": command,
        "raw": {"esl": response},
        "captured_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }


def api(ctx: Any, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    include_raw = _bool_arg(args, "include_raw", default=False)
    command = _require_str(args, "command")
    safe_command = _validate_api_command(command)
    target, esl = _connector(ctx, pbx_id)
    try:
        raw = esl.api(safe_command)
    finally:
        esl.close()
    _validate_esl_read_response(raw, command=safe_command)
    lines = [line.strip() for line in raw.replace("\r", "").splitlines() if line.strip()]
    payload = {
        "pbx_id": pbx_id,
        "platform": "freeswitch",
        "tool": "freeswitch.api",
        "summary": f"{len(lines)} API output lines returned",
        "counts": {"total": len(lines)},
        "items": [{"line_no": idx + 1, "message": line} for idx, line in enumerate(lines)],
        "warnings": [],
        "truncated": False,
        "source_command": safe_command,
        "captured_at": _observed_at(),
        "data_quality": {"completeness": "full", "issues": [], "result_kind": "ok"},
    }
    return {"type": target.type, "id": target.id}, _build_read_result(
        tool_name="freeswitch.api",
        target=target,
        payload=payload,
        source_command=safe_command,
        include_raw=include_raw,
        raw_payload=raw,
    )


def sofia_profile_rescan(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    profile = _require_str(args, "profile")
    target, esl = _connector(ctx, pbx_id)
    command = f"sofia profile {profile} rescan"
    try:
        response = esl.api(command)
    finally:
        esl.close()
    _validate_esl_mutation_response(response, command=command)
    return {"type": target.type, "id": target.id}, {
        "rescanned": True,
        "profile": profile,
    }


def version(ctx: Any, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    include_raw = _bool_arg(args, "include_raw", default=False)
    target, esl = _connector(ctx, pbx_id)
    try:
        raw = esl.api("version")
    finally:
        esl.close()
    _validate_esl_read_response(raw, command="version")
    parsed = _parse_version_value(raw)
    payload = {
        "version": parsed,
        "captured_at": _observed_at(),
        "data_quality": {"completeness": "full", "issues": [], "result_kind": "ok"},
    }
    return {"type": target.type, "id": target.id}, _build_read_result(
        tool_name="freeswitch.version",
        target=target,
        payload=payload,
        source_command="version",
        include_raw=include_raw,
        raw_payload=raw,
    )


def modules(ctx: Any, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    include_raw = _bool_arg(args, "include_raw", default=False)
    target, esl = _connector(ctx, pbx_id)
    try:
        raw = esl.api("show modules")
    finally:
        esl.close()
    _validate_esl_read_response(raw, command="show modules")
    lines = [line.strip() for line in raw.replace("\r", "").splitlines() if line.strip()]
    items: list[dict[str, Any]] = []
    for line in lines:
        lower = line.lower()
        if not (
            lower.startswith("mod_")
            or "/mod_" in lower
            or lower.endswith(".so")
            or ".so " in lower
        ):
            continue
        module_name = line.split()[0].strip()
        items.append({"module": module_name, "status": "loaded", "raw_line": line})
    payload = {
        "pbx_id": pbx_id,
        "platform": "freeswitch",
        "tool": "freeswitch.modules",
        "summary": f"{len(items)} modules parsed",
        "counts": {"total": len(items)},
        "items": items,
        "warnings": ([] if items else ["No module rows parsed from show modules output."]),
        "truncated": False,
        "source_command": "show modules",
        "captured_at": _observed_at(),
        "data_quality": {
            "completeness": "full" if items else "partial",
            "issues": [] if items else ["No structured module rows parsed from ESL output."],
            "result_kind": "ok" if items else "parse_failed",
        },
    }
    return {"type": target.type, "id": target.id}, _build_read_result(
        tool_name="freeswitch.modules",
        target=target,
        payload=payload,
        source_command="show modules",
        include_raw=include_raw,
        raw_payload=raw,
        warnings=list(payload["warnings"]),
        degraded=not items,
    )


def capabilities(ctx: Any, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    include_raw = _bool_arg(args, "include_raw", default=False)
    target, esl = _connector(ctx, pbx_id)
    mode = getattr(ctx, "mode", Mode.INSPECT)
    observed_at = _observed_at()
    warnings: list[str] = []
    raw_payload: dict[str, Any] | None = {} if include_raw else None
    transport_ok = False
    auth_ok = False
    read_ok = False
    version = "unknown"
    degraded_reason: str | None = None
    error_payload: dict[str, Any] | None = None
    try:
        esl.connect()
        transport_ok = True
        version_raw = esl.api("version")
        _validate_esl_read_response(version_raw, command="version")
        auth_ok = True
        read_ok = True
        version = _parse_version_value(version_raw)
        if include_raw and raw_payload is not None:
            raw_payload["version"] = version_raw
    except ToolError as exc:
        degraded_reason = _classify_read_failure(exc)
        error_payload = exc.to_dict()
        if degraded_reason == "auth_failed":
            transport_ok = True
        elif degraded_reason == "command_unavailable":
            transport_ok = True
            auth_ok = True
        warnings.append(f"Capability probe degraded: {degraded_reason}.")
    finally:
        esl.close()

    monitor = _event_monitor(ctx, pbx_id)
    monitor.ensure_started()
    event_status = monitor.status_snapshot()
    event_reason = None
    if isinstance(event_status.get("last_error"), dict):
        event_reason = str(event_status["last_error"].get("code") or "").strip() or None
    event_available = bool(event_status.get("available"))
    event_degraded = bool(event_status.get("degraded"))
    if event_degraded:
        warnings.append("Passive event readback is degraded.")

    writes_allowed = mode in {Mode.EXECUTE_SAFE, Mode.EXECUTE_FULL}
    payload = {
        "target_identity": {"id": target.id, "type": target.type, "host": target.host},
        "mode": str(mode),
        "capabilities": {
            "target_reachability": _build_capability_status(
                supported=True,
                available=transport_ok,
                reason=None if transport_ok else degraded_reason,
            ),
            "esl_socket_reachability": _build_capability_status(
                supported=bool(target.esl),
                available=transport_ok,
                reason=None if transport_ok else degraded_reason,
            ),
            "auth_usability": _build_capability_status(
                supported=bool(target.esl),
                available=auth_ok,
                reason=None if auth_ok else degraded_reason,
            ),
            "read_command_execution": _build_capability_status(
                supported=True,
                available=read_ok,
                reason=None if read_ok else degraded_reason,
            ),
            "raw_evidence_mode": _build_capability_status(supported=True, available=True),
            "passive_event_readback": _build_capability_status(
                supported=True,
                available=event_available,
                reason=(event_reason if not event_available else ("degraded" if event_degraded else None)),
            ),
            "snapshot_support": _build_capability_status(supported=True, available=True),
            "write_actions": _build_capability_status(
                supported=True,
                available=writes_allowed,
                reason=None if writes_allowed else "mode_blocked",
            ),
        },
        "event_readback": {
            "state": event_status.get("state"),
            "buffer_capacity": event_status.get("buffer_capacity"),
            "buffered_events": event_status.get("buffered_events"),
            "dropped_events": event_status.get("dropped_events"),
            "last_event_at": event_status.get("last_event_at"),
            "session_id": event_status.get("session_id"),
        },
        "freeswitch_version": version,
        "data_quality": {
            "completeness": "partial" if warnings else "full",
            "issues": warnings,
            "result_kind": "degraded" if warnings else "ok",
        },
    }
    return {"type": target.type, "id": target.id}, {
        "ok": error_payload is None,
        "tool": "freeswitch.capabilities",
        "target": {"type": target.type, "id": target.id},
        "observed_at": observed_at,
        "transport": {"kind": "esl", "ok": transport_ok, "status": "reachable" if transport_ok else "unreachable"},
        "auth": {"ok": auth_ok, "status": "authenticated" if auth_ok else ("failed" if degraded_reason == "auth_failed" else "unavailable")},
        "command": {"name": "version", "ok": read_ok, "status": "ok" if read_ok else degraded_reason or "error"},
        "payload": payload,
        "warnings": warnings,
        "error": error_payload,
        "degraded": bool(warnings),
        **payload,
        **({"raw": {"esl": raw_payload}} if include_raw and raw_payload is not None else {}),
    }


def recent_events(ctx: Any, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    include_raw = _bool_arg(args, "include_raw", default=False)
    limit = _positive_int_arg(
        args,
        "limit",
        default=20,
        max_value=max_recent_events_return_limit(),
    )
    event_names = _normalize_event_names_arg(args)
    event_family = args.get("event_family")
    if event_family is not None and not isinstance(event_family, str):
        raise ToolError(VALIDATION_ERROR, "Field 'event_family' must be a string")

    target = ctx.settings.get_target(pbx_id)
    if target.type != "freeswitch":
        raise ToolError(NOT_FOUND, f"Target is not a FreeSWITCH system: {pbx_id}")

    monitor = _event_monitor(ctx, pbx_id)
    monitor.ensure_started()
    snapshot = monitor.snapshot(
        limit=limit,
        event_names=event_names,
        event_family=event_family,
        include_raw=include_raw,
    )
    state = str(snapshot.get("state") or "unavailable")
    last_error = snapshot.get("last_error")
    events = snapshot.get("events", [])
    if not isinstance(events, list):
        events = []
    warnings: list[str] = []
    if snapshot.get("overflowed"):
        warnings.append("Recent event buffer overflowed; older events were dropped.")
    if state == "degraded":
        warnings.append("Passive event capture is degraded; returning buffered events if available.")

    payload = {
        "events": events,
        "counts": {
            "returned": len(events),
            "buffered": int(snapshot.get("buffered_events", 0) or 0),
        },
        "filters": {
            "event_names": sorted(event_names) if event_names else [],
            "event_family": event_family.strip().lower()
            if isinstance(event_family, str) and event_family.strip()
            else None,
        },
        "event_buffer": {
            "capacity": int(snapshot.get("buffer_capacity", max_event_buffer_capacity()) or 0),
            "buffered_events": int(snapshot.get("buffered_events", 0) or 0),
            "dropped_events": int(snapshot.get("dropped_events", 0) or 0),
            "overflowed": bool(snapshot.get("overflowed")),
            "last_event_at": snapshot.get("last_event_at"),
            "session_id": snapshot.get("session_id"),
        },
        "data_quality": {
            "completeness": "partial" if state == "degraded" else "full",
            "issues": warnings,
            "result_kind": "empty_valid" if not events else ("degraded" if state == "degraded" else "ok"),
        },
    }
    command_ok = state != "unavailable"
    command_status = (
        "unavailable" if state == "unavailable" else ("degraded" if state == "degraded" else ("empty_valid" if not events else "ok"))
    )
    error_payload = last_error if state == "unavailable" and not events and isinstance(last_error, dict) else None
    result = {
        "ok": command_ok,
        "tool": "freeswitch.recent_events",
        "target": {"type": target.type, "id": target.id},
        "observed_at": _observed_at(),
        "transport": {
            "kind": "esl",
            "ok": state in {"available", "degraded", "starting"},
            "status": state,
        },
        "auth": {
            "ok": state in {"available", "degraded", "starting"},
            "status": "authenticated" if state == "available" else state,
        },
        "command": {
            "name": "internal passive event buffer",
            "ok": command_ok,
            "status": command_status,
        },
        "payload": payload,
        "warnings": warnings,
        "error": error_payload,
        "degraded": state == "degraded",
        **payload,
    }
    return {"type": target.type, "id": target.id}, result


def logs(ctx: Any, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    grep = args.get("grep")
    level = args.get("level")
    if grep is not None and not isinstance(grep, str):
        raise ToolError(VALIDATION_ERROR, "Field 'grep' must be a string")
    if level is not None:
        if not isinstance(level, str):
            raise ToolError(VALIDATION_ERROR, "Field 'level' must be a string")
        if level.lower() not in _LOG_LEVELS:
            raise ToolError(
                VALIDATION_ERROR,
                "Field 'level' must be one of debug|info|notice|warning|error|critical",
            )
        level = level.lower()
    tail = _positive_int_arg(args, "tail", default=200, max_value=2000)

    target = ctx.settings.get_target(pbx_id)
    if target.type != "freeswitch":
        raise ToolError(NOT_FOUND, f"Target is not a FreeSWITCH system: {pbx_id}")
    if target.logs is None:
        raise ToolError(
            NOT_FOUND,
            "FreeSWITCH logs source is not configured for this target",
            {"pbx_id": pbx_id},
        )
    items, truncated = _read_log_lines(
        path=target.logs.path,
        grep=grep.strip() if isinstance(grep, str) and grep.strip() else None,
        tail=tail,
        level=level,
    )
    return {"type": target.type, "id": target.id}, {
        "pbx_id": pbx_id,
        "platform": "freeswitch",
        "tool": "freeswitch.logs",
        "summary": f"{len(items)} log lines returned",
        "counts": {"total": len(items)},
        "items": items,
        "warnings": [],
        "truncated": truncated,
        "source_command": target.logs.source_command or f"tail -n {tail} {target.logs.path}",
        "captured_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
