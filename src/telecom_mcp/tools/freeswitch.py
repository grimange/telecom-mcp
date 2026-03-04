"""FreeSWITCH tool implementations."""

from __future__ import annotations

from typing import Any

from ..connectors.freeswitch_esl import FreeSWITCHESLConnector
from ..errors import NOT_FOUND, VALIDATION_ERROR, ToolError
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
        raise ToolError(NOT_FOUND, f"FreeSWITCH target missing ESL configuration: {pbx_id}")
    return target, FreeSWITCHESLConnector(target.esl)


def health(ctx: Any, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    target, esl = _connector(ctx, pbx_id)
    try:
        ping = esl.ping()
        version_text = esl.api("version")
    finally:
        esl.close()

    return {"type": target.type, "id": target.id}, norm.normalize_health(
        latency_ms=int(ping.get("latency_ms", 0)), version=version_text.strip() or "unknown"
    )


def sofia_status(ctx: Any, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    target, esl = _connector(ctx, pbx_id)
    try:
        raw = esl.api("sofia status")
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
        _ = esl.api("show channels")
    finally:
        esl.close()

    return {"type": target.type, "id": target.id}, norm.normalize_channels([], limit)
