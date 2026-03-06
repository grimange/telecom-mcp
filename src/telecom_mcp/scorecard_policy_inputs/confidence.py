"""Confidence evaluation for scorecard policy input generation."""

from __future__ import annotations


def normalize_confidence(value: str) -> str:
    lowered = str(value or "").strip().lower()
    if lowered in {"high", "medium", "low"}:
        return lowered
    return "unknown"


def evaluate_confidence(
    *,
    confidence: str,
    confidence_reasons: list[str],
) -> tuple[str, list[str], bool]:
    normalized = normalize_confidence(confidence)
    reasons = [str(reason) for reason in confidence_reasons if str(reason).strip()]
    blocks_action = normalized in {"low", "unknown"}
    if normalized == "unknown":
        reasons.append("Scorecard confidence is unknown; action-oriented recommendations are blocked.")
    elif normalized == "low":
        reasons.append("Low confidence forces evidence refresh, no-act, or escalation paths.")
    return normalized, reasons, blocks_action
