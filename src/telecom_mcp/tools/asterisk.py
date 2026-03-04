"""Asterisk tool implementations."""

from __future__ import annotations

from typing import Any

from ..connectors.asterisk_ami import AsteriskAMIConnector
from ..connectors.asterisk_ari import AsteriskARIConnector
from ..errors import NOT_FOUND, VALIDATION_ERROR, ToolError
from ..normalize import asterisk as norm


def _require_pbx_id(args: dict[str, Any]) -> str:
    pbx_id = args.get("pbx_id")
    if not isinstance(pbx_id, str) or not pbx_id:
        raise ToolError(VALIDATION_ERROR, "Field 'pbx_id' must be a non-empty string")
    return pbx_id


def _dict_arg(args: dict[str, Any], key: str) -> dict[str, Any]:
    value = args.get(key)
    if isinstance(value, dict):
        return value
    return {}


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
    return target, AsteriskAMIConnector(target.ami), AsteriskARIConnector(target.ari)


def health(ctx: Any, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    target, ami, ari = _connectors(ctx, pbx_id)

    try:
        ami_ping = ami.ping()
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

    data = norm.normalize_health(
        ari_ok=bool(ari_health.get("ok", False)),
        ari_latency=int(ari_health.get("latency_ms", 0)),
        ami_ok=bool(ami_ping.get("ok", False)),
        ami_latency=int(ami_ping.get("latency_ms", 0)),
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
        ami_response = ami.send_action({"Action": "PJSIPShowEndpoints"})
    finally:
        ami.close()

    items: list[dict[str, Any]] = [ami_response]
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
        _ = ami.send_action({"Action": "Command", "Command": "pjsip reload"})
    finally:
        ami.close()
    return {"type": target.type, "id": target.id}, {"reloaded": True}
