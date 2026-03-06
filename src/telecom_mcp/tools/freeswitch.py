"""FreeSWITCH tool implementations."""

from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path
import re
import time
from typing import Any

from ..connectors.freeswitch_esl import FreeSWITCHESLConnector
from ..errors import NOT_ALLOWED, NOT_FOUND, UPSTREAM_ERROR, VALIDATION_ERROR, ToolError
from ..normalize import freeswitch as norm

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


def _target_allows_active_validation(target: Any) -> bool:
    environment = str(getattr(target, "environment", "unknown")).strip().lower()
    safety_tier = str(getattr(target, "safety_tier", "standard")).strip().lower()
    allow_active_validation = bool(getattr(target, "allow_active_validation", False))
    return environment == "lab" and allow_active_validation and safety_tier == "lab_safe"


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


def health(ctx: Any, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    target, esl = _connector(ctx, pbx_id)
    try:
        ping = esl.ping()
        version_text = esl.api("version")
    finally:
        esl.close()
    ping_raw = str(ping.get("raw", ""))
    _validate_esl_read_response(ping_raw, command="status")
    _validate_esl_read_response(version_text, command="version")

    return {"type": target.type, "id": target.id}, norm.normalize_health(
        latency_ms=int(ping.get("latency_ms", 0)),
        version=version_text.strip() or "unknown",
    )


def sofia_status(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    profile = args.get("profile")
    target, esl = _connector(ctx, pbx_id)
    try:
        cmd = "sofia status"
        if isinstance(profile, str) and profile:
            cmd = f"sofia status profile {profile}"
        raw = esl.api(cmd)
    finally:
        esl.close()
    _validate_esl_read_response(raw, command=cmd)
    return {"type": target.type, "id": target.id}, norm.normalize_sofia_status(raw)


def channels(ctx: Any, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    limit = _positive_int_arg(args, "limit", default=200, max_value=2000)

    target, esl = _connector(ctx, pbx_id)
    try:
        raw = esl.api("show channels")
    finally:
        esl.close()
    _validate_esl_read_response(raw, command="show channels")

    return {"type": target.type, "id": target.id}, norm.normalize_channels(
        [], limit, raw
    )


def registrations(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
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
    return {"type": target.type, "id": target.id}, norm.normalize_registrations(
        [], limit, raw
    )


def gateway_status(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    gateway = _require_str(args, "gateway")
    target, esl = _connector(ctx, pbx_id)
    try:
        raw = esl.api(f"sofia status gateway {gateway}")
    finally:
        esl.close()
    _validate_esl_read_response(raw, command=f"sofia status gateway {gateway}")
    return {"type": target.type, "id": target.id}, norm.normalize_gateway_status(
        gateway, raw
    )


def calls(ctx: Any, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    limit = _positive_int_arg(args, "limit", default=200, max_value=2000)

    target, esl = _connector(ctx, pbx_id)
    try:
        raw = esl.api("show calls")
    finally:
        esl.close()
    _validate_esl_read_response(raw, command="show calls")
    return {"type": target.type, "id": target.id}, norm.normalize_calls([], limit, raw)


def channel_details(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
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
    return {"type": target.type, "id": target.id}, {
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
        "raw": {"esl": raw},
    }


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
    destination = _require_str(args, "destination")
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
    if not _target_allows_active_validation(target):
        raise ToolError(
            NOT_ALLOWED,
            "freeswitch.originate_probe requires environment=lab and explicit allow_active_validation with safety_tier=lab_safe.",
            {
                "tool": "freeswitch.originate_probe",
                "required": {
                    "environment": "lab",
                    "allow_active_validation": True,
                    "safety_tier": "lab_safe",
                },
                "actual": {
                    "environment": str(getattr(target, "environment", "unknown")).strip().lower(),
                    "allow_active_validation": bool(getattr(target, "allow_active_validation", False)),
                    "safety_tier": str(getattr(target, "safety_tier", "standard")).strip().lower(),
                },
            },
        )
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
    command = _require_str(args, "command")
    safe_command = _validate_api_command(command)
    target, esl = _connector(ctx, pbx_id)
    try:
        raw = esl.api(safe_command)
    finally:
        esl.close()
    _validate_esl_read_response(raw, command=safe_command)
    lines = [line.strip() for line in raw.replace("\r", "").splitlines() if line.strip()]
    return {"type": target.type, "id": target.id}, {
        "pbx_id": pbx_id,
        "platform": "freeswitch",
        "tool": "freeswitch.api",
        "summary": f"{len(lines)} API output lines returned",
        "counts": {"total": len(lines)},
        "items": [{"line_no": idx + 1, "message": line} for idx, line in enumerate(lines)],
        "warnings": [],
        "truncated": False,
        "source_command": safe_command,
        "captured_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }


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
    target, esl = _connector(ctx, pbx_id)
    try:
        raw = esl.api("version")
    finally:
        esl.close()
    _validate_esl_read_response(raw, command="version")
    cleaned = raw.replace("\r", " ").replace("\n", " ").strip()
    match = re.search(r"FreeSWITCH(?:\s+Version)?\s+([0-9][0-9A-Za-z_.-]*)", cleaned)
    parsed = match.group(1) if match else "unknown"
    return {"type": target.type, "id": target.id}, {
        "version": parsed,
        "raw": {"esl": raw},
        "captured_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }


def modules(ctx: Any, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
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
    return {"type": target.type, "id": target.id}, {
        "pbx_id": pbx_id,
        "platform": "freeswitch",
        "tool": "freeswitch.modules",
        "summary": f"{len(items)} modules parsed",
        "counts": {"total": len(items)},
        "items": items,
        "warnings": ([] if items else ["No module rows parsed from show modules output."]),
        "truncated": False,
        "source_command": "show modules",
        "captured_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }


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
