"""Schema helpers for scorecard-driven self-healing policy inputs."""

from __future__ import annotations

from typing import Any

ACTION_POSTURES = {
    "no_action",
    "collect_more_evidence",
    "evaluate_low_risk_policy",
    "evaluate_lab_only_policy",
    "escalate_only",
}


def make_dimension_signal(
    *,
    dimension_name: str,
    dimension_score: int,
    dimension_confidence: str,
    risk_level: str,
    trend: str,
    supporting_evidence_refs: list[str],
    policy_relevance: list[str],
    recommended_action_posture: str,
) -> dict[str, Any]:
    posture = (
        recommended_action_posture
        if recommended_action_posture in ACTION_POSTURES
        else "no_action"
    )
    return {
        "dimension_name": dimension_name,
        "dimension_score": max(0, min(100, int(dimension_score))),
        "dimension_confidence": dimension_confidence,
        "risk_level": risk_level,
        "trend": trend,
        "supporting_evidence_refs": supporting_evidence_refs,
        "policy_relevance": policy_relevance,
        "recommended_action_posture": posture,
    }
