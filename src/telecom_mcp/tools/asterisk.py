"""Asterisk tool implementations."""

from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path
import re
import time
from typing import Any

from ..connectors.asterisk_ami import AsteriskAMIConnector
from ..connectors.asterisk_ari import AsteriskARIConnector
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
from ..normalize import asterisk as norm
from ..safety import require_active_target_lab_safe, validate_probe_destination


_LOG_LEVELS = {"debug", "info", "notice", "warning", "error", "critical"}
_CLI_SAFE_EXACT = {
    "core show version",
    "core show uptime",
    "core show channels",
    "pjsip show endpoints",
    "pjsip show contacts",
    "pjsip show registrations outbound",
    "bridge show all",
}
_CLI_SAFE_PATTERNS = (
    re.compile(r"^pjsip show endpoint [A-Za-z0-9_.:-]+$"),
    re.compile(r"^core show channel [A-Za-z0-9_./:-]+$"),
)
def _require_pbx_id(args: dict[str, Any]) -> str:
    pbx_id = args.get("pbx_id")
    if not isinstance(pbx_id, str) or not pbx_id:
        raise ToolError(VALIDATION_ERROR, "Field 'pbx_id' must be a non-empty string")
    return pbx_id


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


def _validated_filter(
    raw_filter: dict[str, Any],
    *,
    allowed_keys: set[str],
    field_name: str,
) -> dict[str, str]:
    unknown = sorted(set(raw_filter) - allowed_keys)
    if unknown:
        raise ToolError(
            VALIDATION_ERROR,
            f"Field '{field_name}' has unknown keys",
            {
                "field": field_name,
                "allowed_keys": sorted(allowed_keys),
                "unknown_keys": unknown,
            },
        )

    validated: dict[str, str] = {}
    for key in allowed_keys:
        if key not in raw_filter:
            continue
        value = raw_filter[key]
        if not isinstance(value, str):
            raise ToolError(
                VALIDATION_ERROR,
                f"Field '{field_name}.{key}' must be a string",
            )
        validated[key] = value
    return validated


def _positive_int_arg(
    args: dict[str, Any], key: str, *, default: int, max_value: int
) -> int:
    value = args.get(key, default)
    if not isinstance(value, int) or value < 1:
        raise ToolError(VALIDATION_ERROR, f"Field '{key}' must be a positive integer")
    return min(value, max_value)


def _connectors(
    ctx: Any,
    pbx_id: str,
) -> tuple[Any, AsteriskAMIConnector | None, AsteriskARIConnector | None]:
    target = ctx.settings.get_target(pbx_id)
    if target.type != "asterisk":
        raise ToolError(NOT_FOUND, f"Target is not an Asterisk system: {pbx_id}")
    timeout_s = ctx.remaining_timeout_s()
    ami = (
        AsteriskAMIConnector(target.ami, timeout_s=timeout_s) if target.ami else None
    )
    ari = (
        AsteriskARIConnector(target.ari, timeout_s=timeout_s) if target.ari else None
    )
    return (
        target,
        ami,
        ari,
    )


def _raise_for_ami_error(ami_response: dict[str, Any], *, endpoint: str | None = None) -> None:
    response = str(ami_response.get("Response", "")).strip().lower()
    if response != "error":
        return
    message = str(ami_response.get("Message", "")).strip() or "AMI error response"
    lowered = message.lower()
    details: dict[str, Any] = {"ami_message": message}
    if endpoint:
        details["endpoint"] = endpoint
    if "authentication" in lowered:
        raise ToolError(AUTH_FAILED, "AMI authentication failed", details)
    if "permission denied" in lowered or "not allowed" in lowered:
        raise ToolError(NOT_ALLOWED, "AMI action not allowed", details)
    if (
        "not found" in lowered
        or "unknown" in lowered
        or "does not exist" in lowered
        or "unable to retrieve endpoint" in lowered
    ):
        raise ToolError(NOT_FOUND, message, details)
    raise ToolError(UPSTREAM_ERROR, message, details)


def _validate_command_response(
    ami_response: dict[str, Any], *, command: str
) -> dict[str, Any]:
    _raise_for_ami_error(ami_response)
    response = str(ami_response.get("Response", "")).strip().lower()
    message = str(ami_response.get("Message", "")).strip()
    output = str(ami_response.get("Output", "")).strip()
    details = {
        "command": command,
        "ami_response": {
            "Response": ami_response.get("Response"),
            "Message": ami_response.get("Message"),
        },
    }
    if output:
        details["output_sample"] = output[:200]

    if response and response not in {"success", "follows"}:
        raise ToolError(
            UPSTREAM_ERROR,
            f"AMI command returned unexpected response state: {response}",
            details,
        )

    combined = f"{message}\n{output}".lower()
    if "permission denied" in combined or "not allowed" in combined:
        raise ToolError(NOT_ALLOWED, "AMI action not allowed", details)
    if "no such command" in combined or "unable to" in combined or "failed" in combined:
        raise ToolError(UPSTREAM_ERROR, f"AMI command failed: {command}", details)
    return ami_response


def _validate_cli_command(command: str) -> str:
    cleaned = " ".join(command.strip().split())
    lowered = cleaned.lower()
    if lowered in _CLI_SAFE_EXACT:
        return cleaned
    for pattern in _CLI_SAFE_PATTERNS:
        if pattern.match(lowered):
            return cleaned
    raise ToolError(
        NOT_ALLOWED,
        "Asterisk CLI command is not in the read-only allowlist",
        {
            "command": command,
            "allowlist_exact": sorted(_CLI_SAFE_EXACT),
            "allowlist_patterns": [p.pattern for p in _CLI_SAFE_PATTERNS],
        },
    )


def _command_lines(response: dict[str, Any]) -> list[str]:
    output = str(response.get("Output", "")).replace("\r", "\n")
    message = str(response.get("Message", "")).replace("\r", "\n")
    blob = output if output.strip() else message
    return [line.strip() for line in blob.splitlines() if line.strip()]


def _send_action_with_retry_on_not_allowed(
    ami: AsteriskAMIConnector,
    action: dict[str, Any],
    *,
    endpoint: str | None = None,
    attempts: int = 2,
) -> dict[str, Any]:
    last_error: ToolError | None = None
    for attempt in range(1, attempts + 1):
        response = ami.send_action(action)
        try:
            _raise_for_ami_error(response, endpoint=endpoint)
            return response
        except ToolError as exc:
            last_error = exc
            if exc.code == NOT_ALLOWED and attempt < attempts:
                time.sleep(0.05)
                continue
            if attempt > 1:
                details = dict(exc.details or {})
                details["attempts"] = attempt
                raise ToolError(exc.code, exc.message, details)
            raise

    if last_error is not None:
        raise last_error
    return {}


def _should_fallback_to_ami(exc: ToolError) -> bool:
    return exc.code in {CONNECTION_FAILED, TIMEOUT, UPSTREAM_ERROR, NOT_ALLOWED}


def _probe_ami_capabilities(
    ami: AsteriskAMIConnector,
) -> tuple[dict[str, Any], list[str]]:
    capability_probes = {
        "pjsip_show_endpoints": {"Action": "PJSIPShowEndpoints"},
        "core_show_channels": {"Action": "CoreShowChannels"},
    }
    capabilities: dict[str, Any] = {}
    warnings: list[str] = []

    for capability, action in capability_probes.items():
        try:
            response = ami.send_action(action)
            _raise_for_ami_error(response)
            capabilities[capability] = {"ok": True}
        except ToolError as exc:
            entry: dict[str, Any] = {
                "ok": False,
                "code": exc.code,
                "message": exc.message,
            }
            if exc.details:
                entry["details"] = exc.details
            if exc.code == NOT_ALLOWED:
                entry["hint"] = (
                    "Grant AMI account permissions for this diagnostic action."
                )
                warnings.append(
                    f"AMI capability '{capability}' is not allowed for this account."
                )
            else:
                warnings.append(
                    f"AMI capability probe failed for '{capability}': {exc.code}."
                )
            capabilities[capability] = entry
    return capabilities, warnings


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
        candidate = line
        if grep and grep not in candidate:
            continue
        if level and level not in candidate.lower():
            continue
        matched.append(candidate)
    truncated = len(matched) > tail
    tail_lines = matched[-tail:]
    items = [{"line_no": index + 1, "message": text} for index, text in enumerate(tail_lines)]
    return items, truncated


def health(ctx: Any, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    target, ami, ari = _connectors(ctx, pbx_id)
    if ami is None or ari is None:
        raise ToolError(
            NOT_FOUND, f"Asterisk target missing AMI/ARI configuration: {pbx_id}"
        )

    try:
        ami_ping = ami.ping()
        ami_capabilities, ami_warnings = _probe_ami_capabilities(ami)
    finally:
        ami.close()

    try:
        ari_health = ari.health()
    finally:
        ari.close()

    raw_health = ari_health.get("raw", {})
    version = "unknown"
    if isinstance(raw_health, dict):
        version = str(raw_health.get("system", {}).get("version", "unknown"))

    ami_connectivity_ok = bool(ami_ping.get("ok", False))
    ami_capability_ok = all(
        bool(item.get("ok", False))
        for item in ami_capabilities.values()
        if isinstance(item, dict)
    )
    ami_ok = ami_connectivity_ok and ami_capability_ok
    data = norm.normalize_health(
        ari_ok=bool(ari_health.get("ok", False)),
        ari_latency=int(ari_health.get("latency_ms", 0)),
        ami_ok=ami_ok,
        ami_latency=int(ami_ping.get("latency_ms", 0)),
        ami_connectivity_ok=ami_connectivity_ok,
        ami_capability_ok=ami_capability_ok,
        ami_capabilities=ami_capabilities,
        warnings=ami_warnings,
        version=version,
    )
    return {"type": target.type, "id": target.id}, data


def pjsip_show_endpoint(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    endpoint = args.get("endpoint")
    if not isinstance(endpoint, str) or not endpoint:
        raise ToolError(VALIDATION_ERROR, "Field 'endpoint' must be a non-empty string")

    target, ami, _ = _connectors(ctx, pbx_id)
    if ami is None:
        raise ToolError(
            NOT_FOUND, f"Asterisk target missing AMI configuration: {pbx_id}"
        )
    try:
        ami_response = ami.send_action(
            {"Action": "PJSIPShowEndpoint", "Endpoint": endpoint}
        )
    finally:
        ami.close()
    _raise_for_ami_error(ami_response, endpoint=endpoint)

    data = norm.normalize_pjsip_endpoint(endpoint, ami_response)
    if not data["exists"]:
        raise ToolError(NOT_FOUND, f"Endpoint not found: {endpoint}")
    return {"type": target.type, "id": target.id}, data


def pjsip_show_endpoints(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    filter_obj = _validated_filter(
        _dict_arg(args, "filter"),
        allowed_keys={"starts_with", "contains"},
        field_name="filter",
    )
    starts_with = filter_obj.get("starts_with")
    contains = filter_obj.get("contains")
    limit = args.get("limit", 200)
    if not isinstance(limit, int) or limit < 1:
        raise ToolError(VALIDATION_ERROR, "Field 'limit' must be a positive integer")

    target, ami, _ = _connectors(ctx, pbx_id)
    if ami is None:
        raise ToolError(
            NOT_FOUND, f"Asterisk target missing AMI configuration: {pbx_id}"
        )
    try:
        ami_response = _send_action_with_retry_on_not_allowed(
            ami,
            {"Action": "PJSIPShowEndpoints"},
        )
    finally:
        ami.close()

    items = norm.extract_pjsip_endpoint_items(ami_response)
    if isinstance(starts_with, str):
        items = [
            i
            for i in items
            if str(i.get("endpoint", i.get("ObjectName", ""))).startswith(starts_with)
        ]
    if isinstance(contains, str):
        items = [
            i
            for i in items
            if contains in str(i.get("endpoint", i.get("ObjectName", "")))
        ]

    return {"type": target.type, "id": target.id}, norm.normalize_pjsip_endpoints(
        items, limit
    )


def pjsip_show_contacts(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    filter_obj = _validated_filter(
        _dict_arg(args, "filter"),
        allowed_keys={"starts_with", "contains"},
        field_name="filter",
    )
    starts_with = filter_obj.get("starts_with")
    contains = filter_obj.get("contains")
    limit = _positive_int_arg(args, "limit", default=200, max_value=2000)

    target, ami, _ = _connectors(ctx, pbx_id)
    if ami is None:
        raise ToolError(
            NOT_FOUND, f"Asterisk target missing AMI configuration: {pbx_id}"
        )
    try:
        ami_response = _send_action_with_retry_on_not_allowed(
            ami,
            {"Action": "PJSIPShowContacts"},
        )
    finally:
        ami.close()
    items = norm.extract_pjsip_contact_items(ami_response)
    if isinstance(starts_with, str):
        items = [
            item
            for item in items
            if str(item.get("ObjectName", "") or item.get("Contact", "")).startswith(starts_with)
        ]
    if isinstance(contains, str):
        items = [
            item
            for item in items
            if contains in str(item.get("ObjectName", "") or item.get("Contact", ""))
        ]
    return {"type": target.type, "id": target.id}, norm.normalize_pjsip_contacts(items, limit)


def active_channels(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    filter_obj = _validated_filter(
        _dict_arg(args, "filter"),
        allowed_keys={"state", "caller", "callee"},
        field_name="filter",
    )
    limit = args.get("limit", 200)
    if not isinstance(limit, int) or limit < 1:
        raise ToolError(VALIDATION_ERROR, "Field 'limit' must be a positive integer")

    target, ami, ari = _connectors(ctx, pbx_id)
    if ami is None:
        raise ToolError(
            NOT_FOUND, f"Asterisk target missing AMI configuration: {pbx_id}"
        )
    channels: list[dict[str, Any]]

    fallback_reason: dict[str, Any] | None = None
    try:
        if ari is None:
            raise ToolError(
                CONNECTION_FAILED,
                "ARI connector not configured for this target",
                {"pbx_id": pbx_id},
            )
        ari_payload = ari.get("channels")
        if isinstance(ari_payload, list):
            channels = [c for c in ari_payload if isinstance(c, dict)]
        elif isinstance(ari_payload, dict):
            payload_channels = ari_payload.get("channels", [])
            channels = [c for c in payload_channels if isinstance(c, dict)]
        else:
            channels = []
    except ToolError as exc:
        if not _should_fallback_to_ami(exc):
            raise
        fallback_reason = {"code": exc.code, "message": exc.message}
        fallback_response = ami.send_action({"Action": "CoreShowChannels"})
        _raise_for_ami_error(fallback_response)
        fallback_events = norm.parse_ami_event_list(str(fallback_response.get("raw", "")))
        channels = [event for event in fallback_events if isinstance(event, dict)] or [
            fallback_response
        ]
    finally:
        ami.close()
        if ari is not None:
            ari.close()

    state = filter_obj.get("state")
    caller = filter_obj.get("caller")
    callee = filter_obj.get("callee")

    if isinstance(state, str):
        channels = [
            c
            for c in channels
            if str(c.get("state", c.get("ChannelStateDesc", ""))) == state
        ]
    if isinstance(caller, str):
        channels = [
            c
            for c in channels
            if caller in str(c.get("caller", c.get("CallerIDNum", "")))
        ]
    if isinstance(callee, str):
        channels = [
            c
            for c in channels
            if callee in str(c.get("callee", c.get("ConnectedLineNum", "")))
        ]

    payload = norm.normalize_active_channels(channels, limit)
    if fallback_reason is not None:
        payload["data_quality"] = {
            "completeness": "partial",
            "fallback_used": True,
            "issues": [
                "ARI channel inventory failed; AMI CoreShowChannels fallback applied."
            ],
            "fallback_reason": fallback_reason,
        }
    return {"type": target.type, "id": target.id}, payload


def pjsip_show_registration(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    registration = args.get("registration")
    if not isinstance(registration, str) or not registration:
        raise ToolError(
            VALIDATION_ERROR, "Field 'registration' must be a non-empty string"
        )

    target, ami, _ = _connectors(ctx, pbx_id)
    if ami is None:
        raise ToolError(
            NOT_FOUND, f"Asterisk target missing AMI configuration: {pbx_id}"
        )
    try:
        ami_response = ami.send_action(
            {"Action": "PJSIPShowRegistrationOutbound", "Registration": registration}
        )
        _raise_for_ami_error(ami_response, endpoint=registration)
    except ToolError as exc:
        if exc.code != NOT_FOUND:
            raise
        lowered = exc.message.lower()
        if "unknown command" not in lowered and "invalid" not in lowered:
            raise
        raise ToolError(
            NOT_ALLOWED,
            "AMI registration inspection action unsupported on this target",
            {
                "pbx_id": pbx_id,
                "registration": registration,
                "required_action": "PJSIPShowRegistrationOutbound",
                "hint": "Enable AMI registration inspection capability or use CLI/ARI alternatives.",
            },
        ) from exc
    finally:
        ami.close()

    return {"type": target.type, "id": target.id}, norm.normalize_pjsip_registration(
        registration, ami_response
    )


def bridges(ctx: Any, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    limit = args.get("limit", 200)
    if not isinstance(limit, int) or limit < 1:
        raise ToolError(VALIDATION_ERROR, "Field 'limit' must be a positive integer")

    target, ami, ari = _connectors(ctx, pbx_id)
    if ami is None:
        raise ToolError(
            NOT_FOUND, f"Asterisk target missing AMI configuration: {pbx_id}"
        )
    items: list[dict[str, Any]] = []
    fallback_reason: dict[str, Any] | None = None
    try:
        if ari is None:
            raise ToolError(
                CONNECTION_FAILED,
                "ARI connector not configured for this target",
                {"pbx_id": pbx_id},
            )
        ari_payload = ari.get("bridges")
        if isinstance(ari_payload, list):
            items = [item for item in ari_payload if isinstance(item, dict)]
        elif isinstance(ari_payload, dict):
            maybe_items = ari_payload.get("bridges", [])
            if isinstance(maybe_items, list):
                items = [item for item in maybe_items if isinstance(item, dict)]
    except ToolError as exc:
        if not _should_fallback_to_ami(exc):
            raise
        fallback_reason = {"code": exc.code, "message": exc.message}
        fallback_response = ami.send_action({"Action": "BridgeList"})
        _raise_for_ami_error(fallback_response)
        fallback_events = norm.parse_ami_event_list(str(fallback_response.get("raw", "")))
        items = [event for event in fallback_events if isinstance(event, dict)] or [
            fallback_response
        ]
    finally:
        ami.close()
        if ari is not None:
            ari.close()

    payload = norm.normalize_bridges(items, limit)
    if fallback_reason is not None:
        payload["data_quality"] = {
            "completeness": "partial",
            "fallback_used": True,
            "issues": ["ARI bridge inventory failed; AMI BridgeList fallback applied."],
            "fallback_reason": fallback_reason,
        }
    return {"type": target.type, "id": target.id}, payload


def channel_details(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    channel_id = args.get("channel_id")
    if not isinstance(channel_id, str) or not channel_id:
        raise ToolError(
            VALIDATION_ERROR, "Field 'channel_id' must be a non-empty string"
        )

    target, ami, ari = _connectors(ctx, pbx_id)
    if ami is None:
        raise ToolError(
            NOT_FOUND, f"Asterisk target missing AMI configuration: {pbx_id}"
        )
    payload: dict[str, Any]
    try:
        if ari is None:
            raise ToolError(
                NOT_FOUND,
                f"ARI connector not configured for this target: {pbx_id}",
                {"pbx_id": pbx_id},
            )
        ari_payload = ari.get(f"channels/{channel_id}")
        if isinstance(ari_payload, dict):
            payload = ari_payload
        else:
            payload = {}
    except ToolError:
        payload = ami.send_action({"Action": "CoreShowChannel", "Channel": channel_id})
        try:
            _raise_for_ami_error(payload, endpoint=channel_id)
        except ToolError as exc:
            lowered = exc.message.lower()
            if exc.code == NOT_FOUND and (
                "invalid/unknown command" in lowered
                or "unknown command" in lowered
                or "no such command" in lowered
            ):
                raise ToolError(
                    NOT_ALLOWED,
                    "AMI channel detail action unsupported on this target",
                    {
                        "pbx_id": pbx_id,
                        "channel_id": channel_id,
                        "required_action": "CoreShowChannel",
                        "ami_message": exc.message,
                    },
                ) from exc
            raise
    finally:
        ami.close()
        if ari is not None:
            ari.close()

    if not payload:
        raise ToolError(NOT_FOUND, f"Channel not found: {channel_id}")
    return {"type": target.type, "id": target.id}, norm.normalize_channel_details(
        channel_id, payload
    )


def core_show_channel(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    channel_id = args.get("channel_id")
    if not isinstance(channel_id, str) or not channel_id:
        raise ToolError(
            VALIDATION_ERROR, "Field 'channel_id' must be a non-empty string"
        )
    target, ami, _ = _connectors(ctx, pbx_id)
    if ami is None:
        raise ToolError(
            NOT_FOUND, f"Asterisk target missing AMI configuration: {pbx_id}"
        )
    try:
        payload = _send_action_with_retry_on_not_allowed(
            ami,
            {"Action": "CoreShowChannel", "Channel": channel_id},
            endpoint=channel_id,
        )
    finally:
        ami.close()
    return {"type": target.type, "id": target.id}, norm.normalize_channel_details(
        channel_id, payload
    )


def reload_pjsip(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    target, ami, _ = _connectors(ctx, pbx_id)
    if ami is None:
        raise ToolError(
            NOT_FOUND, f"Asterisk target missing AMI configuration: {pbx_id}"
        )
    try:
        response = ami.send_action({"Action": "Command", "Command": "pjsip reload"})
    finally:
        ami.close()
    _validate_command_response(response, command="pjsip reload")
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

    target, ami, _ = _connectors(ctx, pbx_id)
    if ami is None:
        raise ToolError(
            NOT_FOUND, f"Asterisk target missing AMI configuration: {pbx_id}"
        )
    require_active_target_lab_safe(target, tool_name="asterisk.originate_probe")
    action = {
        "Action": "Originate",
        "Channel": f"PJSIP/{destination}",
        "Context": "default",
        "Exten": destination,
        "Priority": "1",
        "Async": "true",
        "Timeout": str(timeout_s * 1000),
        "CallerID": probe_id,
        "Variable": f"TELECOM_MCP_PROBE_ID={probe_id}",
    }
    try:
        with active_operation_controller.guard(
            operation="asterisk.originate_probe",
            pbx_id=pbx_id,
        ):
            response = ami.send_action(action)
            _raise_for_ami_error(response, endpoint=destination)
    finally:
        ami.close()
    return {"type": target.type, "id": target.id}, {
        "probe_id": probe_id,
        "destination": destination,
        "platform": "asterisk",
        "initiated": True,
        "timeout_s": timeout_s,
        "source_command": "AMI Originate",
        "raw": {"ami_response": response},
        "captured_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }


def version(ctx: Any, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    target, ami, _ = _connectors(ctx, pbx_id)
    if ami is None:
        raise ToolError(
            NOT_FOUND, f"Asterisk target missing AMI configuration: {pbx_id}"
        )
    try:
        response = ami.send_action({"Action": "Command", "Command": "core show version"})
    finally:
        ami.close()
    validated = _validate_command_response(response, command="core show version")
    output = str(validated.get("Output", "")).strip()
    message = str(validated.get("Message", "")).strip()
    sample = output or message
    version_match = re.search(r"Asterisk\s+([0-9][0-9A-Za-z_.-]*)", sample)
    parsed = version_match.group(1) if version_match else "unknown"
    return {"type": target.type, "id": target.id}, {
        "version": parsed,
        "raw": {"ami_response": validated},
        "captured_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }


def modules(ctx: Any, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    target, ami, _ = _connectors(ctx, pbx_id)
    if ami is None:
        raise ToolError(
            NOT_FOUND, f"Asterisk target missing AMI configuration: {pbx_id}"
        )
    try:
        response = ami.send_action({"Action": "Command", "Command": "module show like"})
    finally:
        ami.close()
    validated = _validate_command_response(response, command="module show like")
    blob = str(validated.get("Output", "") or validated.get("Message", ""))
    lines = [line.strip() for line in blob.replace("\r", "\n").splitlines() if line.strip()]
    items: list[dict[str, Any]] = []
    for line in lines:
        if ".so" not in line:
            continue
        parts = [p for p in re.split(r"\s{2,}", line) if p]
        module_name = parts[0].strip()
        description = parts[1].strip() if len(parts) > 1 else ""
        use_count_raw = parts[2].strip() if len(parts) > 2 else "0"
        status = parts[3].strip() if len(parts) > 3 else ""
        try:
            use_count = int(use_count_raw)
        except ValueError:
            use_count = 0
        items.append(
            {
                "module": module_name,
                "description": description,
                "use_count": use_count,
                "status": status or "unknown",
            }
        )
    return {"type": target.type, "id": target.id}, {
        "pbx_id": pbx_id,
        "platform": "asterisk",
        "tool": "asterisk.modules",
        "summary": f"{len(items)} modules parsed",
        "counts": {"total": len(items)},
        "items": items,
        "warnings": ([] if items else ["No module rows parsed from module show output."]),
        "truncated": False,
        "source_command": "module show like",
        "captured_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }


def cli(ctx: Any, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    command = args.get("command")
    if not isinstance(command, str) or not command.strip():
        raise ToolError(VALIDATION_ERROR, "Field 'command' must be a non-empty string")
    normalized_command = _validate_cli_command(command)

    target, ami, _ = _connectors(ctx, pbx_id)
    if ami is None:
        raise ToolError(
            NOT_FOUND, f"Asterisk target missing AMI configuration: {pbx_id}"
        )
    try:
        response = ami.send_action({"Action": "Command", "Command": normalized_command})
    finally:
        ami.close()
    validated = _validate_command_response(response, command=normalized_command)
    lines = _command_lines(validated)
    return {"type": target.type, "id": target.id}, {
        "pbx_id": pbx_id,
        "platform": "asterisk",
        "tool": "asterisk.cli",
        "summary": f"{len(lines)} CLI output lines returned",
        "counts": {"total": len(lines)},
        "items": [{"line_no": idx + 1, "message": line} for idx, line in enumerate(lines)],
        "warnings": [],
        "truncated": False,
        "source_command": normalized_command,
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
    if target.type != "asterisk":
        raise ToolError(NOT_FOUND, f"Target is not an Asterisk system: {pbx_id}")
    if target.logs is None:
        raise ToolError(
            NOT_FOUND,
            "Asterisk logs source is not configured for this target",
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
        "platform": "asterisk",
        "tool": "asterisk.logs",
        "summary": f"{len(items)} log lines returned",
        "counts": {"total": len(items)},
        "items": items,
        "warnings": [],
        "truncated": truncated,
        "source_command": target.logs.source_command or f"tail -n {tail} {target.logs.path}",
        "captured_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
