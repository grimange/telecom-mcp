"""Self-healing handoff adapter for scorecard policy inputs."""

from __future__ import annotations

from typing import Any


def build_policy_handoff(
    *,
    policy_input: dict[str, Any],
    policy_catalog: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    candidates = policy_input.get("recommended_policy_candidates", [])
    if not isinstance(candidates, list):
        candidates = []

    candidate_ids = [
        str(item.get("policy"))
        for item in candidates
        if isinstance(item, dict) and str(item.get("policy", "")).strip()
    ]
    candidate_set = set(candidate_ids)

    suppressed = []
    for policy_name in sorted(policy_catalog):
        if policy_name in candidate_set:
            continue
        suppressed.append(
            {
                "policy": policy_name,
                "reason": "not_selected_by_scorecard_mapping",
            }
        )

    freshness = str(policy_input.get("freshness", "unknown")).lower()
    confidence = str(policy_input.get("confidence", "unknown")).lower()
    stop_conditions: list[str] = []
    if freshness != "fresh":
        stop_conditions.append("stale_score_with_no_refresh")
    if confidence in {"low", "unknown"}:
        stop_conditions.append("confidence_below_threshold")

    action_posture = "evaluation_only"
    if stop_conditions:
        action_posture = "no_act_or_escalate"

    return {
        "action_posture": action_posture,
        "eligible_policy_candidates": candidate_ids,
        "suppressed_policy_candidates": suppressed,
        "stop_conditions": stop_conditions,
        "no_bypass": {
            "direct_execution_allowed": False,
            "cooldown_override_allowed": False,
            "denylist_override_allowed": False,
            "production_override_allowed": False,
        },
    }
