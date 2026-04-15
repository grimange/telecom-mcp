"""FreeSWITCH tool implementations."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
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
_ROUTE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.@:+*#-]+$")
_ROUTE_EVIDENCE_LIMIT = 4096
_MANAGEMENT_SHOW_COMMAND = "show management as json"


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


def _canonical_key(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _first_row_value(row: dict[str, Any], *keys: str) -> str:
    normalized = {_canonical_key(key): value for key, value in row.items()}
    for key in keys:
        value = _stringify(normalized.get(_canonical_key(key)))
        if value:
            return value
    return ""


def _coerce_int(value: str) -> int | None:
    cleaned = value.strip()
    if not cleaned:
        return None
    if cleaned.isdigit():
        return int(cleaned)
    return None


def _inbound_esl_identity_contract_summary() -> dict[str, Any]:
    return {
        "primary_identifier_field": "session_id",
        "secondary_selector_field": "session_fingerprint",
        "secondary_selector_role": "reselect_discovered_session_record",
        "targetable_when": [
            "session is visible as inbound ESL",
            "session_id is present",
            "session_id is unique within the current management snapshot",
        ],
        "untargetable_when": [
            "session_id is missing",
            "session_id is duplicated within the current management snapshot",
            "session visibility does not support one exact session identity contract",
        ],
    }


def _base_inbound_esl_identity_source() -> dict[str, Any]:
    return {
        "source_name": "show_management",
        "source_kind": "freeswitch_management_api",
        "source_command": _MANAGEMENT_SHOW_COMMAND,
        "source_status": "unknown",
        "source_support_level": "repo_modeled",
        "target_support_state": "unknown",
    }


def _is_inbound_esl_session(row: dict[str, Any]) -> bool:
    evidence_text = " ".join(_stringify(value).lower() for value in row.values())
    if "event_socket" in evidence_text or "event socket" in evidence_text:
        return True
    if "esl" in evidence_text:
        return True
    return False


def _session_fingerprint(*, session_id: str, remote_host: str, remote_port: str, connected_at: str) -> str:
    seed = "|".join([session_id, remote_host, remote_port, connected_at])
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _row_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "profile": _first_row_value(row, "profile", "module", "application") or None,
        "type": _first_row_value(row, "type", "session_type", "kind") or None,
        "listen_id": _first_row_value(
            row, "listen-id", "listen_id", "listener_id", "session_id", "id"
        )
        or None,
        "remote_endpoint": {
            "host": _first_row_value(row, "remote_ip", "remote_host", "ip", "host")
            or None,
            "port": _first_row_value(row, "remote_port", "port") or None,
        },
    }


def _normalize_management_session(row: dict[str, Any]) -> dict[str, Any]:
    session_id = _first_row_value(
        row,
        "listen-id",
        "listen_id",
        "listener_id",
        "session_id",
        "id",
    )
    remote_host = _first_row_value(row, "remote_ip", "remote_host", "ip", "host")
    remote_port = _first_row_value(row, "remote_port", "port")
    local_host = _first_row_value(row, "listen_ip", "local_ip", "listen_host", "local_host")
    local_port = _first_row_value(row, "listen_port", "local_port")
    connected_at = _first_row_value(
        row,
        "created",
        "created_at",
        "connected_at",
        "connected_since",
        "started_at",
    )
    age_s = _coerce_int(_first_row_value(row, "age", "age_s", "duration", "duration_s"))
    inbound_esl = _is_inbound_esl_session(row)
    fingerprint = _session_fingerprint(
        session_id=session_id or "missing-id",
        remote_host=remote_host,
        remote_port=remote_port,
        connected_at=connected_at,
    )
    metadata = {
        key: value
        for key, value in row.items()
        if _stringify(value)
    }
    return {
        "session_id": session_id or None,
        "session_fingerprint": fingerprint,
        "session_type": "inbound_esl" if inbound_esl else "other_management_session",
        "is_inbound_esl": inbound_esl,
        "targetable": False,
        "remote_endpoint": {"host": remote_host or None, "port": remote_port or None},
        "local_endpoint": {"host": local_host or None, "port": local_port or None},
        "connected_at": connected_at or None,
        "age_s": age_s,
        "ambiguity_notes": [],
        "identity_contract": {
            "primary_identifier": {
                "field": "session_id",
                "value": session_id or None,
                "authoritative": bool(session_id),
            },
            "secondary_selector": {
                "field": "session_fingerprint",
                "value": fingerprint,
                "derived": True,
            },
            "supporting_evidence": {
                "remote_endpoint": {"host": remote_host or None, "port": remote_port or None},
                "local_endpoint": {"host": local_host or None, "port": local_port or None},
                "connected_at": connected_at or None,
                "age_s": age_s,
            },
            "confidence": "low",
            "targetability": "untargetable",
            "reason": "identity_contract_not_evaluated",
        },
        "metadata": metadata,
    }


def _apply_inbound_esl_identity_contract(
    sessions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    id_counts: dict[str, int] = {}
    for item in sessions:
        session_id = _stringify(item.get("session_id"))
        if session_id:
            id_counts[session_id] = id_counts.get(session_id, 0) + 1

    for item in sessions:
        session_id = _stringify(item.get("session_id"))
        ambiguity_notes: list[str] = []
        identity_contract = item.get("identity_contract")
        if not isinstance(identity_contract, dict):
            identity_contract = {}
            item["identity_contract"] = identity_contract

        if not session_id:
            ambiguity_notes.append(
                "Session appears to be inbound ESL but FreeSWITCH did not expose a stable listener identifier."
            )
            confidence = "low"
            targetability = "untargetable"
            reason = "missing_primary_identifier"
        elif id_counts.get(session_id, 0) > 1:
            ambiguity_notes.append(
                "Session ID is duplicated within the current management snapshot, so exact targeting is unsafe."
            )
            confidence = "low"
            targetability = "untargetable"
            reason = "duplicate_primary_identifier"
        else:
            confidence = "high"
            targetability = "targetable"
            reason = "unique_primary_identifier"

        item["targetable"] = targetability == "targetable"
        item["ambiguity_notes"] = ambiguity_notes
        identity_contract["confidence"] = confidence
        identity_contract["targetability"] = targetability
        identity_contract["reason"] = reason

    return sessions


def _inspect_inbound_esl_identity_source(esl: FreeSWITCHESLConnector) -> dict[str, Any]:
    source = _base_inbound_esl_identity_source()
    raw: str | None = None
    parsed_payload: dict[str, Any] | list[Any] | None = None
    rows: list[dict[str, Any]] = []
    row_diagnostics: list[dict[str, Any]] = []
    sessions: list[dict[str, Any]] = []
    warnings: list[str] = []
    notes: list[str] = []
    error: dict[str, Any] | None = None

    try:
        raw = esl.api(_MANAGEMENT_SHOW_COMMAND)
        _validate_esl_read_response(raw, command=_MANAGEMENT_SHOW_COMMAND)
    except ToolError as exc:
        source["source_status"] = "error"
        source["source_support_level"] = "target_unavailable"
        source["target_support_state"] = "unknown"
        error = {
            "code": getattr(exc, "code", UPSTREAM_ERROR),
            "message": str(exc),
            "details": getattr(exc, "details", None),
        }
        notes.append("Identity discovery source could not be queried successfully.")
        return {
            "identity_source": source,
            "raw": raw,
            "parsed_payload": parsed_payload,
            "rows": rows,
            "row_diagnostics": row_diagnostics,
            "sessions": sessions,
            "warnings": warnings,
            "notes": notes,
            "error": error,
            "target_support_state": source["target_support_state"],
            "usable_identity_found": False,
        }

    cleaned = raw.strip() if isinstance(raw, str) else ""
    if not cleaned:
        source["source_status"] = "error"
        source["source_support_level"] = "target_unavailable"
        source["target_support_state"] = "unknown"
        error = {
            "code": UPSTREAM_ERROR,
            "message": "FreeSWITCH management session discovery returned an empty payload",
            "details": {"command": _MANAGEMENT_SHOW_COMMAND},
        }
        notes.append("Identity discovery source returned an empty payload.")
        return {
            "identity_source": source,
            "raw": raw,
            "parsed_payload": parsed_payload,
            "rows": rows,
            "row_diagnostics": row_diagnostics,
            "sessions": sessions,
            "warnings": warnings,
            "notes": notes,
            "error": error,
            "target_support_state": source["target_support_state"],
            "usable_identity_found": False,
        }

    try:
        parsed_payload = json.loads(cleaned)
    except json.JSONDecodeError:
        source["source_status"] = "incompatible_schema"
        source["source_support_level"] = "target_incompatible"
        source["target_support_state"] = "repo_support_only"
        warnings.append("Identity discovery source returned non-JSON output on this target.")
        notes.append("Target did not expose a parseable management-session schema for identity discovery.")
        error = {
            "code": UPSTREAM_ERROR,
            "message": "FreeSWITCH management session discovery did not return valid JSON",
            "details": {"command": _MANAGEMENT_SHOW_COMMAND, "output_sample": raw[:200]},
        }
        return {
            "identity_source": source,
            "raw": raw,
            "parsed_payload": parsed_payload,
            "rows": rows,
            "row_diagnostics": row_diagnostics,
            "sessions": sessions,
            "warnings": warnings,
            "notes": notes,
            "error": error,
            "target_support_state": source["target_support_state"],
            "usable_identity_found": False,
        }

    if isinstance(parsed_payload, list):
        rows = [row for row in parsed_payload if isinstance(row, dict)]
    elif isinstance(parsed_payload, dict):
        if isinstance(parsed_payload.get("rows"), list):
            rows = [row for row in parsed_payload["rows"] if isinstance(row, dict)]
        elif isinstance(parsed_payload.get("data"), list):
            rows = [row for row in parsed_payload["data"] if isinstance(row, dict)]
        elif isinstance(parsed_payload.get("items"), list):
            rows = [row for row in parsed_payload["items"] if isinstance(row, dict)]
        else:
            source["source_status"] = "incompatible_schema"
            source["source_support_level"] = "target_incompatible"
            source["target_support_state"] = "repo_support_only"
            warnings.append("Identity discovery source returned JSON without a recognized rows/data/items collection.")
            notes.append("Target JSON schema does not match the supported management-session container formats.")
            return {
                "identity_source": source,
                "raw": raw,
                "parsed_payload": parsed_payload,
                "rows": rows,
                "row_diagnostics": row_diagnostics,
                "sessions": sessions,
                "warnings": warnings,
                "notes": notes,
                "error": None,
                "target_support_state": source["target_support_state"],
                "usable_identity_found": False,
            }
    else:
        source["source_status"] = "incompatible_schema"
        source["source_support_level"] = "target_incompatible"
        source["target_support_state"] = "repo_support_only"
        warnings.append("Identity discovery source returned a JSON type that telecom-mcp does not model for management rows.")
        notes.append("Target JSON schema does not expose management rows in a supported top-level structure.")
        return {
            "identity_source": source,
            "raw": raw,
            "parsed_payload": parsed_payload,
            "rows": rows,
            "row_diagnostics": row_diagnostics,
            "sessions": sessions,
            "warnings": warnings,
            "notes": notes,
            "error": None,
            "target_support_state": source["target_support_state"],
            "usable_identity_found": False,
        }

    candidate_rows: list[dict[str, Any]] = []
    candidate_indexes: list[int] = []
    for index, row in enumerate(rows):
        resembles_inbound_esl = _is_inbound_esl_session(row)
        row_diag = {
            "row_index": index,
            "row_keys": sorted(_stringify(key) for key in row.keys()),
            "row_summary": _row_summary(row),
            "resembles_inbound_esl": resembles_inbound_esl,
            "considered_for_identity": resembles_inbound_esl,
            "rejection_reasons": [] if resembles_inbound_esl else ["not_inbound_esl_candidate"],
        }
        row_diagnostics.append(row_diag)
        if resembles_inbound_esl:
            candidate_rows.append(row)
            candidate_indexes.append(index)

    sessions = [_normalize_management_session(row) for row in candidate_rows]
    sessions = _apply_inbound_esl_identity_contract(sessions)
    for row_index, session in zip(candidate_indexes, sessions):
        identity_contract = session.get("identity_contract")
        if isinstance(identity_contract, dict) and not session.get("targetable"):
            reason = _stringify(identity_contract.get("reason"))
            if reason:
                row_diagnostics[row_index]["rejection_reasons"] = [reason]

    if not rows:
        source["source_status"] = "empty_valid"
        source["source_support_level"] = "target_exposed_but_empty"
        source["target_support_state"] = "identity_unavailable_on_target"
        warnings.append("Identity discovery source returned zero management rows on this target.")
        notes.append("No management rows were exposed by the target while querying the supported source.")
    elif not candidate_rows:
        source["source_status"] = "unusable_for_identity"
        source["source_support_level"] = "target_exposed_but_unusable"
        source["target_support_state"] = "identity_unavailable_on_target"
        warnings.append("Management rows were returned, but none resembled inbound ESL listeners.")
        notes.append("Target exposed management rows, but no row matched telecom-mcp's inbound ESL candidate criteria.")
    elif any(bool(item.get("targetable")) for item in sessions):
        source["source_status"] = "supported"
        source["source_support_level"] = "target_exposed"
        source["target_support_state"] = "identity_available"
        notes.append("Target exposed at least one inbound ESL session with a usable primary identifier.")
    elif any(
        isinstance(item.get("identity_contract"), dict)
        and item["identity_contract"].get("reason") == "duplicate_primary_identifier"
        for item in sessions
    ):
        source["source_status"] = "unusable_for_identity"
        source["source_support_level"] = "target_exposed_but_unusable"
        source["target_support_state"] = "identity_ambiguous_on_target"
        warnings.append("Inbound ESL candidate rows were visible, but the target exposed duplicate primary identifiers.")
        notes.append("Target exposed inbound ESL candidates, but exact identity remained ambiguous within the current snapshot.")
    else:
        source["source_status"] = "unusable_for_identity"
        source["source_support_level"] = "target_exposed_but_unusable"
        source["target_support_state"] = "identity_unavailable_on_target"
        warnings.append("Inbound ESL candidate rows were visible, but they did not expose a usable primary identifier.")
        notes.append("Target exposed inbound ESL candidates, but none were targetable under the identity contract.")

    if any(not bool(item.get("targetable")) for item in sessions):
        warnings.append(
            "Some inbound ESL sessions were visible but not safely targetable because the primary session identifier was missing or ambiguous."
        )
    return {
        "identity_source": source,
        "raw": raw,
        "parsed_payload": parsed_payload,
        "rows": rows,
        "row_diagnostics": row_diagnostics,
        "sessions": sessions,
        "warnings": warnings,
        "notes": notes,
        "error": error,
        "target_support_state": source["target_support_state"],
        "usable_identity_found": any(bool(item.get("targetable")) for item in sessions),
    }


def _collect_inbound_esl_sessions(
    esl: FreeSWITCHESLConnector,
) -> tuple[str | None, list[dict[str, Any]], list[str], dict[str, Any]]:
    inspection = _inspect_inbound_esl_identity_source(esl)
    return (
        inspection.get("raw"),
        list(inspection.get("sessions") or []),
        list(inspection.get("warnings") or []),
        inspection,
    )


def _match_inbound_esl_sessions(
    sessions: list[dict[str, Any]],
    *,
    session_id: str | None,
    session_fingerprint: str | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    selector = {
        "session_id": session_id,
        "session_fingerprint": session_fingerprint,
    }
    if session_id:
        matches = [item for item in sessions if item.get("session_id") == session_id]
        return matches, selector
    if session_fingerprint:
        matches = [item for item in sessions if item.get("session_fingerprint") == session_fingerprint]
        return matches, selector
    return [], selector


def _rejection_reason_counts(row_diagnostics: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in row_diagnostics:
        reasons = item.get("rejection_reasons")
        if not isinstance(reasons, list):
            continue
        for reason in reasons:
            key = _stringify(reason)
            if not key:
                continue
            counts[key] = counts.get(key, 0) + 1
    return counts


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


def _event_status_reason(event_status: dict[str, Any]) -> str | None:
    if isinstance(event_status.get("last_error"), dict):
        value = str(event_status["last_error"].get("code") or "").strip()
        if value:
            return value
    freshness = event_status.get("freshness")
    if isinstance(freshness, dict):
        reason = str(freshness.get("staleness_reason") or "").strip()
        if reason:
            return reason
    return None


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


def _optional_route_token(args: dict[str, Any], key: str) -> str | None:
    value = args.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ToolError(VALIDATION_ERROR, f"Field '{key}' must be a non-empty string")
    cleaned = value.strip()
    if not _ROUTE_TOKEN_RE.match(cleaned):
        raise ToolError(
            VALIDATION_ERROR,
            f"Field '{key}' contains unsupported characters",
            {"field": key},
        )
    return cleaned


def _required_destination(args: dict[str, Any]) -> str:
    destination = _optional_route_token(args, "destination")
    if destination is None:
        raise ToolError(VALIDATION_ERROR, "Field 'destination' must be a non-empty string")
    return destination


def _bounded_evidence_text(raw: str) -> dict[str, Any]:
    return {
        "text": raw[:_ROUTE_EVIDENCE_LIMIT],
        "truncated": len(raw) > _ROUTE_EVIDENCE_LIMIT,
        "limit_chars": _ROUTE_EVIDENCE_LIMIT,
    }


def _xml_attrs(tag_text: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for match in re.finditer(r"([A-Za-z0-9_.:-]+)\s*=\s*(['\"])(.*?)\2", tag_text):
        attrs[match.group(1).strip().lower()] = match.group(3).strip()
    return attrs


def _route_expression_matches(expression: str, destination: str) -> tuple[bool, str | None]:
    try:
        return re.search(expression, destination) is not None, None
    except re.error as exc:
        return False, f"Invalid dialplan expression ignored: {exc}"


def _parse_dialplan_route(
    *,
    raw: str,
    context: str,
    destination: str,
) -> dict[str, Any]:
    context_pattern = re.compile(
        rf"<context\b(?P<attrs>[^>]*)\bname\s*=\s*(['\"]){re.escape(context)}\2[^>]*>(?P<body>.*?)</context>",
        re.IGNORECASE | re.DOTALL,
    )
    context_match = context_pattern.search(raw)
    if not context_match:
        if "<context" in raw.lower():
            return {
                "context_found": False,
                "matched_extension": None,
                "matched_conditions": [],
                "warnings": [],
                "dynamic": False,
            }
        return {
            "context_found": False,
            "matched_extension": None,
            "matched_conditions": [],
            "warnings": ["Dialplan XML readback did not contain recognizable context elements."],
            "dynamic": True,
        }

    body = context_match.group("body")
    warnings: list[str] = []
    saw_destination_condition = False
    extension_re = re.compile(
        r"<extension\b(?P<attrs>[^>]*)>(?P<body>.*?)</extension>",
        re.IGNORECASE | re.DOTALL,
    )
    condition_re = re.compile(
        r"<condition\b(?P<attrs>[^>]*)/?>",
        re.IGNORECASE | re.DOTALL,
    )
    for extension_match in extension_re.finditer(body):
        extension_attrs = _xml_attrs(extension_match.group("attrs"))
        extension_name = extension_attrs.get("name") or extension_attrs.get("number") or "unknown"
        matched_conditions: list[dict[str, Any]] = []
        for condition_match in condition_re.finditer(extension_match.group("body")):
            attrs = _xml_attrs(condition_match.group("attrs"))
            field = attrs.get("field", "")
            expression = attrs.get("expression", "")
            if field not in {"destination_number", "${destination_number}"}:
                continue
            saw_destination_condition = True
            if not expression:
                continue
            matched, warning = _route_expression_matches(expression, destination)
            if warning:
                warnings.append(warning)
            if matched:
                matched_conditions.append(
                    {
                        "field": field,
                        "expression": expression,
                        "destination": destination,
                    }
                )
        if matched_conditions:
            return {
                "context_found": True,
                "matched_extension": extension_name,
                "matched_conditions": matched_conditions,
                "warnings": warnings,
                "dynamic": False,
            }
    return {
        "context_found": True,
        "matched_extension": None,
        "matched_conditions": [],
        "warnings": warnings,
        "dynamic": not saw_destination_condition,
    }


def _append_blocker(
    blockers: list[dict[str, Any]],
    *,
    code: str,
    severity: str,
    message: str,
    evidence: dict[str, Any] | None = None,
) -> None:
    item = {"code": code, "severity": severity, "message": message}
    if evidence is not None:
        item["evidence"] = evidence
    blockers.append(item)


def _confidence_for(route_status: str, blockers: list[dict[str, Any]], *, exact_match: bool) -> str:
    if route_status == "route_found" and exact_match and not blockers:
        return "high"
    if route_status == "no_route" and exact_match:
        hard_no_route = all(
            blocker.get("code") in {"NO_MATCHING_CONTEXT", "NO_MATCHING_EXTENSION"}
            for blocker in blockers
        )
        return "high" if hard_no_route else "medium"
    if route_status in {"route_found", "no_route"} and exact_match:
        return "medium" if blockers else "high"
    if route_status == "ambiguous":
        return "low"
    return "low"


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


def route_check(ctx: Any, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    destination = _required_destination(args)
    context = _optional_route_token(args, "context")
    caller_id_number = _optional_route_token(args, "caller_id_number")
    caller_context = _optional_route_token(args, "caller_context")
    profile = _optional_route_token(args, "profile")
    gateway = _optional_route_token(args, "gateway")
    include_evidence = _bool_arg(args, "include_evidence", default=False)

    target, esl = _connector(ctx, pbx_id)
    observed_at = _observed_at()
    warnings: list[str] = []
    blockers: list[dict[str, Any]] = []
    raw_evidence: dict[str, Any] = {}
    evidence: dict[str, Any] = {}
    matched_context: str | None = None
    matched_extension: str | None = None
    matched_conditions: list[dict[str, Any]] = []
    route_status = "ambiguous"
    exact_dialplan_evidence = False

    try:
        if context:
            dialplan_cmd = f"xml_locate dialplan {context}"
            try:
                dialplan_raw = esl.api(dialplan_cmd)
                _validate_esl_read_response(dialplan_raw, command=dialplan_cmd)
                if include_evidence:
                    raw_evidence["dialplan"] = _bounded_evidence_text(dialplan_raw)
                parsed_route = _parse_dialplan_route(
                    raw=dialplan_raw,
                    context=context,
                    destination=destination,
                )
                warnings.extend(parsed_route.get("warnings", []))
                exact_dialplan_evidence = not bool(parsed_route.get("dynamic"))
                if parsed_route.get("context_found"):
                    matched_context = context
                    matched_extension = parsed_route.get("matched_extension")
                    matched_conditions = list(parsed_route.get("matched_conditions", []))
                    if matched_extension:
                        route_status = "route_found"
                    elif parsed_route.get("dynamic"):
                        route_status = "ambiguous"
                        _append_blocker(
                            blockers,
                            code="DYNAMIC_DIALPLAN_UNSUPPORTED",
                            severity="warning",
                            message="Dialplan context is present but static destination-number rules were not visible.",
                        )
                    else:
                        route_status = "no_route"
                        _append_blocker(
                            blockers,
                            code="NO_MATCHING_EXTENSION",
                            severity="error",
                            message="No static destination-number condition matched the requested destination.",
                            evidence={"context": context, "destination": destination},
                        )
                else:
                    route_status = "no_route" if exact_dialplan_evidence else "ambiguous"
                    _append_blocker(
                        blockers,
                        code="NO_MATCHING_CONTEXT",
                        severity="error" if exact_dialplan_evidence else "warning",
                        message="Requested dialplan context was not found in static dialplan readback.",
                        evidence={"context": context},
                    )
            except ToolError as exc:
                route_status = "degraded"
                warnings.append("Dialplan readback failed; route certainty is limited.")
                _append_blocker(
                    blockers,
                    code="ROUTE_EVIDENCE_INCOMPLETE",
                    severity="warning",
                    message="Static dialplan evidence could not be read.",
                    evidence={"code": exc.code, "message": exc.message},
                )
        else:
            warnings.append("No context supplied; route_check cannot prove dialplan match.")
            _append_blocker(
                blockers,
                code="ROUTE_EVIDENCE_INCOMPLETE",
                severity="warning",
                message="Field 'context' is required for static dialplan matching.",
            )

        try:
            sofia_raw, sofia_payload = _sofia_status_with_fallback(esl)
            if include_evidence:
                raw_evidence["sofia_status"] = _bounded_evidence_text(sofia_raw)
            evidence["profiles"] = sofia_payload.get("profiles", [])
            evidence["gateways"] = sofia_payload.get("gateways", [])
            if profile:
                profile_rows = [
                    row for row in evidence["profiles"]
                    if str(row.get("name", "")).strip() == profile
                ]
                profile_state = str(profile_rows[0].get("state", "UNKNOWN")) if profile_rows else "MISSING"
                evidence["profile"] = {"name": profile, "state": profile_state}
                if profile_state not in {"RUNNING", "UP"}:
                    _append_blocker(
                        blockers,
                        code="PROFILE_UNAVAILABLE",
                        severity="error",
                        message="Requested Sofia profile is not visibly running.",
                        evidence={"profile": profile, "state": profile_state},
                    )
        except ToolError as exc:
            warnings.append("Sofia status evidence is degraded.")
            _append_blocker(
                blockers,
                code="TARGET_DEGRADED",
                severity="warning",
                message="Sofia profile and gateway evidence could not be collected.",
                evidence={"code": exc.code, "message": exc.message},
            )

        if gateway:
            gateway_cmd = f"sofia status gateway {gateway}"
            try:
                gateway_raw = esl.api(gateway_cmd)
                _validate_esl_read_response(gateway_raw, command=gateway_cmd)
                if include_evidence:
                    raw_evidence["gateway_status"] = _bounded_evidence_text(gateway_raw)
                gateway_payload = norm.normalize_gateway_status(gateway, gateway_raw)
                evidence["gateway"] = {
                    "name": gateway,
                    "state": gateway_payload.get("state", "UNKNOWN"),
                }
                if gateway_payload.get("state") != "UP":
                    _append_blocker(
                        blockers,
                        code="GATEWAY_UNAVAILABLE",
                        severity="error",
                        message="Requested gateway is not visibly UP.",
                        evidence=evidence["gateway"],
                    )
            except ToolError as exc:
                warnings.append("Gateway status evidence is degraded.")
                _append_blocker(
                    blockers,
                    code="GATEWAY_UNAVAILABLE",
                    severity="warning",
                    message="Requested gateway status could not be verified.",
                    evidence={"gateway": gateway, "code": exc.code, "message": exc.message},
                )

        if profile:
            reg_cmd = f"sofia status profile {profile} reg"
            try:
                reg_raw = esl.api(reg_cmd)
                _validate_esl_read_response(reg_raw, command=reg_cmd)
                if include_evidence:
                    raw_evidence["registrations"] = _bounded_evidence_text(reg_raw)
                reg_payload = norm.normalize_registrations([], 500, reg_raw)
                reg_items = reg_payload.get("items", [])
                matched_regs = [
                    item for item in reg_items
                    if str(item.get("user", "")).strip() in {destination, caller_id_number or ""}
                ]
                evidence["registrations"] = {
                    "total": len(reg_items) if isinstance(reg_items, list) else 0,
                    "matched_users": [item.get("user") for item in matched_regs],
                }
                if (
                    not gateway
                    and matched_extension
                    and isinstance(reg_items, list)
                    and reg_items
                    and not any(str(item.get("user", "")).strip() == destination for item in reg_items)
                ):
                    _append_blocker(
                        blockers,
                        code="REGISTRATION_MISSING",
                        severity="warning",
                        message="No matching registration for the destination was visible in the requested profile.",
                        evidence={"profile": profile, "destination": destination},
                    )
            except ToolError as exc:
                warnings.append("Registration evidence is degraded.")
                _append_blocker(
                    blockers,
                    code="ROUTE_EVIDENCE_INCOMPLETE",
                    severity="warning",
                    message="Registration state could not be verified.",
                    evidence={"profile": profile, "code": exc.code, "message": exc.message},
                )
    finally:
        esl.close()

    if blockers and route_status == "route_found":
        route_status = "degraded" if any(b["severity"] == "error" for b in blockers) else "ambiguous"
    if route_status == "ambiguous" and any(b["code"] == "NO_MATCHING_CONTEXT" and b["severity"] == "error" for b in blockers):
        route_status = "no_route"

    confidence = _confidence_for(
        route_status,
        blockers,
        exact_match=exact_dialplan_evidence and bool(context),
    )
    required_dependencies = {
        "context": context,
        "profile": profile,
        "gateway": gateway,
        "caller_id_number": caller_id_number,
        "caller_context": caller_context,
    }
    result = {
        "ok": True,
        "tool": "freeswitch.route_check",
        "target": {"type": target.type, "id": target.id},
        "observed_at": observed_at,
        "route_status": route_status,
        "confidence": confidence,
        "matched_context": matched_context,
        "matched_extension": matched_extension,
        "matched_conditions": matched_conditions,
        "required_dependencies": required_dependencies,
        "blocking_findings": blockers,
        "warnings": warnings,
        "evidence": evidence,
        "error": None,
    }
    if include_evidence:
        result["raw_evidence"] = raw_evidence
    return {"type": target.type, "id": target.id}, result


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
    identity_inspection: dict[str, Any] = {
        "identity_source": _base_inbound_esl_identity_source(),
        "target_support_state": "unknown",
        "usable_identity_found": False,
        "warnings": [],
        "notes": [],
        "error": None,
    }
    try:
        esl.connect()
        transport_ok = True
        version_raw = esl.api("version")
        _validate_esl_read_response(version_raw, command="version")
        auth_ok = True
        read_ok = True
        version = _parse_version_value(version_raw)
        identity_inspection = _inspect_inbound_esl_identity_source(esl)
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
    event_reason = _event_status_reason(event_status)
    event_available = bool(event_status.get("available"))
    event_degraded = bool(event_status.get("degraded"))
    event_freshness = event_status.get("freshness", {})
    if event_degraded:
        warnings.append("Passive event readback is degraded.")
    if isinstance(event_freshness, dict) and event_freshness.get("is_stale"):
        warnings.append(
            f"Passive event readback is stale: {event_freshness.get('staleness_reason') or 'unknown'}."
        )

    writes_allowed = mode in {Mode.EXECUTE_SAFE, Mode.EXECUTE_FULL}
    live_identity_available = (
        identity_inspection.get("target_support_state") == "identity_available"
    )
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
            "inbound_esl_session_discovery": _build_capability_status(
                supported=True,
                available=read_ok,
                reason=None if read_ok else degraded_reason,
            ),
            "inbound_esl_identity_repo_support": _build_capability_status(
                supported=True,
                available=True,
            ),
            "inbound_esl_identity_live_target": _build_capability_status(
                supported=True,
                available=live_identity_available,
                reason=(
                    None
                    if live_identity_available
                    else _stringify(identity_inspection.get("target_support_state")) or "unknown"
                ),
            ),
            "inbound_esl_session_drop": _build_capability_status(
                supported=False,
                available=False,
                reason="no_safe_session_disconnect_strategy",
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
            "monitor_state": event_freshness.get("monitor_state"),
            "buffer_capacity": event_status.get("buffer_capacity"),
            "buffered_events": event_status.get("buffered_events"),
            "dropped_events": event_status.get("dropped_events"),
            "monitor_started_at": event_status.get("monitor_started_at"),
            "last_event_at": event_status.get("last_event_at"),
            "last_healthy_at": event_status.get("last_healthy_at"),
            "idle_duration_ms": event_freshness.get("idle_duration_ms"),
            "is_stale": event_freshness.get("is_stale"),
            "staleness_reason": event_freshness.get("staleness_reason"),
            "session_id": event_status.get("session_id"),
        },
        "freeswitch_version": version,
        "inbound_esl_session_identity_contract": _inbound_esl_identity_contract_summary(),
        "inbound_esl_identity_source": identity_inspection.get("identity_source"),
        "inbound_esl_identity_target_support": {
            "target_support_state": identity_inspection.get("target_support_state"),
            "usable_identity_found": bool(identity_inspection.get("usable_identity_found")),
            "warnings": list(identity_inspection.get("warnings") or []),
            "notes": list(identity_inspection.get("notes") or []),
        },
        "inbound_esl_session_drop_policy": {
            "minimum_mode": Mode.EXECUTE_FULL.value,
            "requires_lab_safe_target": True,
            "requires_write_allowlist": True,
            "disconnect_strategy_available": False,
            "support_state": "unsupported_current_posture",
            "reason": "telecom-mcp can discover inbound ESL sessions but does not have a verified one-session disconnect primitive in the current connector/server posture",
        },
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
    freshness = snapshot.get("freshness", {})
    warnings: list[str] = []
    if snapshot.get("overflowed"):
        warnings.append("Recent event buffer overflowed; older events were dropped.")
    if state == "degraded":
        warnings.append("Passive event capture is degraded; returning buffered events if available.")
    if isinstance(freshness, dict) and freshness.get("is_stale"):
        warnings.append(
            f"Passive event capture is stale: {freshness.get('staleness_reason') or 'unknown'}."
        )

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
            "monitor_state": freshness.get("monitor_state"),
            "monitor_started_at": snapshot.get("monitor_started_at"),
            "last_event_at": snapshot.get("last_event_at"),
            "last_healthy_at": snapshot.get("last_healthy_at"),
            "idle_duration_ms": freshness.get("idle_duration_ms"),
            "is_stale": freshness.get("is_stale"),
            "staleness_reason": freshness.get("staleness_reason"),
            "session_id": snapshot.get("session_id"),
        },
        "freshness": freshness if isinstance(freshness, dict) else {},
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


def inbound_esl_sessions(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    include_raw = _bool_arg(args, "include_raw", default=False)
    target, esl = _connector(ctx, pbx_id)
    try:
        raw, sessions, warnings, inspection = _collect_inbound_esl_sessions(esl)
    finally:
        esl.close()

    payload = {
        "items": sessions,
        "counts": {
            "total": len(sessions),
            "targetable": sum(1 for item in sessions if item.get("targetable")),
            "untargetable": sum(1 for item in sessions if not item.get("targetable")),
            "duplicate_primary_identifiers": sum(
                1
                for item in sessions
                if (
                    isinstance(item.get("identity_contract"), dict)
                    and item["identity_contract"].get("reason") == "duplicate_primary_identifier"
                )
            ),
        },
        "summary": f"{len(sessions)} inbound ESL sessions visible",
        "identity_contract": _inbound_esl_identity_contract_summary(),
        "identity_source": inspection.get("identity_source"),
        "target_support_state": inspection.get("target_support_state"),
        "usable_identity_found": bool(inspection.get("usable_identity_found")),
        "data_quality": {
            "completeness": "partial" if warnings or inspection.get("error") else "full",
            "issues": warnings,
            "result_kind": (
                "parse_failed"
                if inspection.get("error") or _stringify((inspection.get("identity_source") or {}).get("source_status")) == "incompatible_schema"
                else ("empty_valid" if not sessions else ("degraded" if warnings else "ok"))
            ),
        },
    }
    return {"type": target.type, "id": target.id}, _build_read_result(
        tool_name="freeswitch.inbound_esl_sessions",
        target=target,
        payload=payload,
        source_command=_MANAGEMENT_SHOW_COMMAND,
        include_raw=include_raw,
        raw_payload=raw,
        warnings=warnings,
        degraded=bool(warnings),
        error=inspection.get("error"),
    )


def inbound_esl_diagnostics(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    include_raw = _bool_arg(args, "include_raw", default=False)
    target, esl = _connector(ctx, pbx_id)
    try:
        inspection = _inspect_inbound_esl_identity_source(esl)
    finally:
        esl.close()

    row_diagnostics = list(inspection.get("row_diagnostics") or [])
    payload = {
        "queried_sources": [inspection.get("identity_source")],
        "identity_source": inspection.get("identity_source"),
        "rows_observed": len(inspection.get("rows") or []),
        "rows_considered": sum(
            1 for item in row_diagnostics if bool(item.get("considered_for_identity"))
        ),
        "rows_rejected": [
            {
                "row_index": item.get("row_index"),
                "rejection_reasons": item.get("rejection_reasons"),
                "row_summary": item.get("row_summary"),
            }
            for item in row_diagnostics
            if item.get("rejection_reasons")
        ],
        "rejection_reasons": _rejection_reason_counts(row_diagnostics),
        "usable_identity_found": bool(inspection.get("usable_identity_found")),
        "target_support_state": inspection.get("target_support_state"),
        "notes": list(inspection.get("notes") or []),
        "row_diagnostics": row_diagnostics,
        "identity_contract": _inbound_esl_identity_contract_summary(),
        "data_quality": {
            "completeness": "partial" if inspection.get("warnings") or inspection.get("error") else "full",
            "issues": list(inspection.get("warnings") or []),
            "result_kind": (
                "parse_failed"
                if inspection.get("error")
                or _stringify((inspection.get("identity_source") or {}).get("source_status")) == "incompatible_schema"
                else "ok"
            ),
        },
    }
    if include_raw:
        payload["raw_rows"] = list(inspection.get("rows") or [])
    return {"type": target.type, "id": target.id}, _build_read_result(
        tool_name="freeswitch.inbound_esl_diagnostics",
        target=target,
        payload=payload,
        source_command=_MANAGEMENT_SHOW_COMMAND,
        include_raw=include_raw,
        raw_payload=inspection.get("raw"),
        warnings=list(inspection.get("warnings") or []),
        degraded=bool(inspection.get("warnings")),
        error=inspection.get("error"),
    )


def drop_inbound_esl_session(
    ctx: Any, args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    pbx_id = _require_pbx_id(args)
    requested_session_id = _stringify(args.get("session_id")) or None
    requested_fingerprint = _stringify(args.get("session_fingerprint")) or None
    confirm_session_id = _stringify(args.get("confirm_session_id"))
    include_raw = _bool_arg(args, "include_raw", default=False)
    if not requested_session_id and not requested_fingerprint:
        raise ToolError(
            VALIDATION_ERROR,
            "Session-specific disconnect requires either 'session_id' or 'session_fingerprint'",
            {
                "tool": "freeswitch.drop_inbound_esl_session",
                "required_one_of": ["session_id", "session_fingerprint"],
            },
        )

    target, esl = _connector(ctx, pbx_id)
    require_active_target_lab_safe(target, tool_name="freeswitch.drop_inbound_esl_session")
    observed_at = _observed_at()
    try:
        collected = _collect_inbound_esl_sessions(esl)
    finally:
        esl.close()
    if len(collected) == 4:
        raw, sessions, warnings, inspection = collected
    else:
        raw, sessions, warnings = collected
        inspection = {
            "identity_source": _base_inbound_esl_identity_source(),
            "target_support_state": "unknown",
        }

    matches, selector = _match_inbound_esl_sessions(
        sessions,
        session_id=requested_session_id,
        session_fingerprint=requested_fingerprint,
    )
    matched_session = matches[0] if len(matches) == 1 else None

    blocker: dict[str, Any] | None = None
    if not matches:
        blocker = {
            "code": "NO_MATCH",
            "message": "No inbound ESL session matched the requested selector.",
        }
    elif len(matches) > 1:
        blocker = {
            "code": "AMBIGUOUS_SELECTOR",
            "message": "Requested selector matched more than one inbound ESL session.",
            "matched_session_ids": [item.get("session_id") for item in matches],
        }
    elif matched_session is None:
        blocker = {
            "code": "MATCH_STATE_INVALID",
            "message": "Internal match state was inconsistent; refusing to proceed.",
        }
    elif not bool(matched_session.get("targetable")):
        blocker = {
            "code": "UNTARGETABLE_SESSION",
            "message": "Matched inbound ESL session is visible but does not expose a safe stable identifier for disconnect.",
        }
    elif confirm_session_id != _stringify(matched_session.get("session_id")):
        blocker = {
            "code": "CONFIRMATION_MISMATCH",
            "message": "Field 'confirm_session_id' must exactly match the selected session_id.",
            "expected_session_id": matched_session.get("session_id"),
        }
    else:
        blocker = {
            "code": "UNSUPPORTED_DISCONNECT_STRATEGY",
            "message": "Current telecom-mcp posture can discover inbound ESL sessions but does not support executing a verified one-session disconnect.",
            "investigation_basis": [
                _MANAGEMENT_SHOW_COMMAND,
                "mod_event_socket listener tracking is internal to FreeSWITCH",
                "no verified session-specific disconnect command is exposed through the current ESL connector surface",
            ],
        }

    result = {
        "ok": False,
        "tool": "freeswitch.drop_inbound_esl_session",
        "target": {"type": target.type, "id": target.id},
        "observed_at": observed_at,
        "requested_target": selector,
        "identity_source": inspection.get("identity_source"),
        "target_support_state": inspection.get("target_support_state"),
        "match_result": {
            "matched_count": len(matches),
            "matched_session_id": matched_session.get("session_id") if matched_session else None,
            "matched_session_fingerprint": matched_session.get("session_fingerprint") if matched_session else None,
            "candidate_session_ids": [
                item.get("session_id") if isinstance(item, dict) else None
                for item in matches
            ],
            "unique_match": len(matches) == 1,
        },
        "matched_session": matched_session,
        "execution": {
            "attempted": False,
            "executed": False,
            "post_action_verified": False,
            "strategy": None,
            "result": "unsupported",
        },
        "post_verification": {
            "performed": False,
            "targeted_session_present_after_action": None,
            "non_target_sessions_observed_after_action": None,
            "result": "not_performed",
            "reason": "disconnect_not_attempted",
        },
        "blocker": blocker,
        "warnings": warnings,
        "degraded": False,
        "support_state": "unsupported_current_posture",
    }
    if include_raw:
        result["raw"] = {"esl": raw}
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
