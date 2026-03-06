"""FreeSWITCH tool implementations."""

from __future__ import annotations

from typing import Any

from ..connectors.freeswitch_esl import FreeSWITCHESLConnector
from ..errors import NOT_ALLOWED, NOT_FOUND, UPSTREAM_ERROR, VALIDATION_ERROR, ToolError
from ..normalize import freeswitch as norm


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


def health(ctx: Any, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    target, esl = _connector(ctx, pbx_id)
    try:
        ping = esl.ping()
        version_text = esl.api("version")
    finally:
        esl.close()

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
    return {"type": target.type, "id": target.id}, norm.normalize_sofia_status(raw)


def channels(ctx: Any, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    limit = args.get("limit", 200)
    if not isinstance(limit, int) or limit < 1:
        raise ToolError(VALIDATION_ERROR, "Field 'limit' must be a positive integer")

    target, esl = _connector(ctx, pbx_id)
    try:
        raw = esl.api("show channels")
    finally:
        esl.close()

    return {"type": target.type, "id": target.id}, norm.normalize_channels(
        [], limit, raw
    )


def registrations(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    profile = args.get("profile")
    limit = args.get("limit", 200)
    if not isinstance(limit, int) or limit < 1:
        raise ToolError(VALIDATION_ERROR, "Field 'limit' must be a positive integer")

    target, esl = _connector(ctx, pbx_id)
    cmd = "sofia status profile internal reg"
    if isinstance(profile, str) and profile:
        cmd = f"sofia status profile {profile} reg"
    try:
        raw = esl.api(cmd)
    finally:
        esl.close()
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
    return {"type": target.type, "id": target.id}, norm.normalize_gateway_status(
        gateway, raw
    )


def calls(ctx: Any, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    limit = args.get("limit", 200)
    if not isinstance(limit, int) or limit < 1:
        raise ToolError(VALIDATION_ERROR, "Field 'limit' must be a positive integer")

    target, esl = _connector(ctx, pbx_id)
    try:
        raw = esl.api("show calls")
    finally:
        esl.close()
    return {"type": target.type, "id": target.id}, norm.normalize_calls([], limit, raw)


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
