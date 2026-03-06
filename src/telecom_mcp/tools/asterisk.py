"""Asterisk tool implementations."""

from __future__ import annotations

import time
from typing import Any

from ..connectors.asterisk_ami import AsteriskAMIConnector
from ..connectors.asterisk_ari import AsteriskARIConnector
from ..errors import (
    AUTH_FAILED,
    NOT_ALLOWED,
    NOT_FOUND,
    UPSTREAM_ERROR,
    VALIDATION_ERROR,
    ToolError,
)
from ..normalize import asterisk as norm


def _require_pbx_id(args: dict[str, Any]) -> str:
    pbx_id = args.get("pbx_id")
    if not isinstance(pbx_id, str) or not pbx_id:
        raise ToolError(VALIDATION_ERROR, "Field 'pbx_id' must be a non-empty string")
    return pbx_id


def _dict_arg(args: dict[str, Any], key: str) -> dict[str, Any]:
    if key not in args:
        return {}
    value = args.get(key)
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    raise ToolError(VALIDATION_ERROR, f"Field '{key}' must be an object")


def _connectors(
    ctx: Any, pbx_id: str
) -> tuple[Any, AsteriskAMIConnector, AsteriskARIConnector]:
    target = ctx.settings.get_target(pbx_id)
    if target.type != "asterisk":
        raise ToolError(NOT_FOUND, f"Target is not an Asterisk system: {pbx_id}")
    if not target.ami or not target.ari:
        raise ToolError(
            NOT_FOUND, f"Asterisk target missing AMI/ARI configuration: {pbx_id}"
        )
    timeout_s = ctx.remaining_timeout_s()
    return (
        target,
        AsteriskAMIConnector(target.ami, timeout_s=timeout_s),
        AsteriskARIConnector(target.ari, timeout_s=timeout_s),
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
    if "not found" in lowered or "unknown" in lowered or "does not exist" in lowered:
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


def health(ctx: Any, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    target, ami, ari = _connectors(ctx, pbx_id)

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
    filter_obj = _dict_arg(args, "filter")
    starts_with = filter_obj.get("starts_with")
    contains = filter_obj.get("contains")
    limit = args.get("limit", 200)
    if not isinstance(limit, int) or limit < 1:
        raise ToolError(VALIDATION_ERROR, "Field 'limit' must be a positive integer")

    target, ami, _ = _connectors(ctx, pbx_id)
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


def active_channels(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    filter_obj = _dict_arg(args, "filter")
    limit = args.get("limit", 200)
    if not isinstance(limit, int) or limit < 1:
        raise ToolError(VALIDATION_ERROR, "Field 'limit' must be a positive integer")

    target, ami, ari = _connectors(ctx, pbx_id)
    channels: list[dict[str, Any]]

    try:
        ari_payload = ari.get("channels")
        if isinstance(ari_payload, list):
            channels = [c for c in ari_payload if isinstance(c, dict)]
        elif isinstance(ari_payload, dict):
            payload_channels = ari_payload.get("channels", [])
            channels = [c for c in payload_channels if isinstance(c, dict)]
        else:
            channels = []
    except Exception:
        channels = [ami.send_action({"Action": "CoreShowChannels"})]
    finally:
        ami.close()
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

    return {"type": target.type, "id": target.id}, norm.normalize_active_channels(
        channels, limit
    )


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
    try:
        ami_response = ami.send_action(
            {"Action": "PJSIPShowRegistrationOutbound", "Registration": registration}
        )
    finally:
        ami.close()
    _raise_for_ami_error(ami_response, endpoint=registration)

    return {"type": target.type, "id": target.id}, norm.normalize_pjsip_registration(
        registration, ami_response
    )


def bridges(ctx: Any, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    limit = args.get("limit", 200)
    if not isinstance(limit, int) or limit < 1:
        raise ToolError(VALIDATION_ERROR, "Field 'limit' must be a positive integer")

    target, ami, ari = _connectors(ctx, pbx_id)
    items: list[dict[str, Any]] = []
    try:
        ari_payload = ari.get("bridges")
        if isinstance(ari_payload, list):
            items = [item for item in ari_payload if isinstance(item, dict)]
        elif isinstance(ari_payload, dict):
            maybe_items = ari_payload.get("bridges", [])
            if isinstance(maybe_items, list):
                items = [item for item in maybe_items if isinstance(item, dict)]
    except Exception:
        items = [ami.send_action({"Action": "BridgeList"})]
    finally:
        ami.close()
        ari.close()

    return {"type": target.type, "id": target.id}, norm.normalize_bridges(items, limit)


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
    payload: dict[str, Any]
    try:
        ari_payload = ari.get(f"channels/{channel_id}")
        if isinstance(ari_payload, dict):
            payload = ari_payload
        else:
            payload = {}
    except ToolError:
        payload = ami.send_action({"Action": "CoreShowChannel", "Channel": channel_id})
        _raise_for_ami_error(payload, endpoint=channel_id)
    finally:
        ami.close()
        ari.close()

    if not payload:
        raise ToolError(NOT_FOUND, f"Channel not found: {channel_id}")
    return {"type": target.type, "id": target.id}, norm.normalize_channel_details(
        channel_id, payload
    )


def reload_pjsip(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    target, ami, _ = _connectors(ctx, pbx_id)
    try:
        response = ami.send_action({"Action": "Command", "Command": "pjsip reload"})
    finally:
        ami.close()
    _validate_command_response(response, command="pjsip reload")
    return {"type": target.type, "id": target.id}, {"reloaded": True}
