"""Envelope validators used by chaos experiments."""

from __future__ import annotations

from telecom_mcp.errors import ALLOWED_ERROR_CODES

REQUIRED_ENVELOPE_KEYS = {
    "ok",
    "timestamp",
    "target",
    "duration_ms",
    "correlation_id",
    "data",
    "error",
}


def validate_envelope(payload: dict) -> list[str]:
    issues: list[str] = []
    missing = REQUIRED_ENVELOPE_KEYS - set(payload.keys())
    if missing:
        issues.append(f"missing_envelope_keys={sorted(missing)}")

    cid = payload.get("correlation_id")
    if not isinstance(cid, str) or not cid:
        issues.append("missing_or_invalid_correlation_id")

    ok = payload.get("ok")
    if not isinstance(ok, bool):
        issues.append("ok_must_be_bool")

    error = payload.get("error")
    if ok is False:
        if not isinstance(error, dict):
            issues.append("error_must_be_object_when_ok_false")
        else:
            code = error.get("code")
            if code not in ALLOWED_ERROR_CODES:
                issues.append(f"invalid_error_code={code}")

    return issues
