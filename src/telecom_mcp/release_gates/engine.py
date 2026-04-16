"""Confidence-aware release gating decisions from scorecard policy inputs and validation outcomes."""

from __future__ import annotations

from typing import Any


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def evaluate_release_gate(
    *,
    policy_input: dict[str, Any],
    validation: dict[str, Any],
    change_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return release gate decision (`allow`, `hold`, or `escalate`) with evidence reasons."""
    context = _safe_dict(change_context)
    confidence = str(policy_input.get("confidence", "unknown")).lower()
    freshness = str(policy_input.get("freshness", "unknown")).lower()
    score = int(policy_input.get("score", 0))

    stop_conditions = _safe_list(_safe_dict(policy_input.get("policy_handoff")).get("stop_conditions"))
    escalations = _safe_list(policy_input.get("recommended_escalations"))

    smoke_status = str(validation.get("smoke_status", "unknown")).lower()
    post_change_status = str(validation.get("post_change_status", "unknown")).lower()
    cleanup_ok = bool(validation.get("cleanup_ok", False))
    conflicting_evidence = bool(validation.get("conflicting_evidence", False))

    decision = "allow"
    reasons: list[str] = []
    required_actions: list[str] = []

    if stop_conditions:
        decision = "hold"
        reasons.append("scorecard_stop_conditions_present")

    if freshness != "fresh":
        decision = "hold"
        reasons.append("scorecard_not_fresh")
        required_actions.append("refresh_scorecard_and_validation_evidence")

    if confidence in {"low", "unknown"}:
        decision = "hold"
        reasons.append("scorecard_confidence_too_low")
        required_actions.append("collect_higher_confidence_signals")

    if conflicting_evidence:
        decision = "hold"
        reasons.append("conflicting_validation_evidence")
        required_actions.append("resolve_conflicting_evidence_before_release")

    if smoke_status not in {"passed"}:
        decision = "hold"
        reasons.append("smoke_validation_not_passed")

    if post_change_status in {"failed", "warning"}:
        decision = "hold"
        reasons.append("post_change_validation_not_clean")

    if not cleanup_ok:
        decision = "hold"
        reasons.append("cleanup_verification_failed")

    high_risk_context = bool(context.get("high_risk_change", False))
    if high_risk_context and score < 85:
        decision = "hold"
        reasons.append("high_risk_change_requires_stronger_score")

    if escalations:
        decision = "escalate"
        reasons.append("scorecard_requested_escalation")

    if score <= 55 and confidence == "high":
        decision = "escalate"
        reasons.append("high_confidence_low_score_release_risk")

    return {
        "decision": decision,
        "reasons": sorted(set(reasons)),
        "required_actions": sorted(set(required_actions)),
        "inputs": {
            "score": score,
            "confidence": confidence,
            "freshness": freshness,
            "smoke_status": smoke_status,
            "post_change_status": post_change_status,
            "cleanup_ok": cleanup_ok,
            "conflicting_evidence": conflicting_evidence,
        },
    }
