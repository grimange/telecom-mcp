"""Engine that converts resilience scorecards into self-healing policy inputs."""

from __future__ import annotations

from typing import Any

from .confidence import evaluate_confidence
from .freshness import evaluate_freshness
from .handoff import build_policy_handoff
from .mapping import map_to_policy_candidates, recommended_posture, risk_level_from_score, trend_from_score_delta
from .ranking import rank_candidates
from .schemas import make_dimension_signal


def _has_conflicting_dimension_signals(scorecard: dict[str, Any]) -> bool:
    strengths = [str(item).lower() for item in scorecard.get("top_strengths", []) if isinstance(item, str)]
    risks = [str(item).lower() for item in scorecard.get("top_risks", []) if isinstance(item, str)]
    if not strengths or not risks:
        return False
    tracked = [
        "configuration integrity",
        "runtime health",
        "detection readiness",
        "validation confidence",
        "fault resilience",
        "incident burden",
    ]
    for name in tracked:
        if any(name in row for row in strengths) and any(name in row for row in risks):
            return True
    return False


def _dimension_index(scorecard: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    raw_dimensions = scorecard.get("dimensions", [])
    if not isinstance(raw_dimensions, list):
        return index
    for row in raw_dimensions:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name", "")).strip()
        if not name:
            continue
        index[name] = row
    return index


def build_policy_input(
    *,
    entity_type: str,
    entity_id: str,
    scorecard: dict[str, Any],
    policy_catalog: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    score = int(scorecard.get("score", 0))
    band = str(scorecard.get("band", "at_risk"))
    confidence_raw = str(scorecard.get("confidence", "unknown"))
    confidence_reasons = [
        str(reason)
        for reason in scorecard.get("confidence_reasons", [])
        if isinstance(reason, str)
    ]
    freshness, freshness_reasons, freshness_blocks_action = evaluate_freshness(
        generated_at=str(scorecard.get("generated_at", "")),
    )
    confidence, confidence_reasons, confidence_blocks_action = evaluate_confidence(
        confidence=confidence_raw,
        confidence_reasons=confidence_reasons,
    )

    trend_summary = scorecard.get("trend_summary", {})
    trend_delta = int(trend_summary.get("absolute_change", 0)) if isinstance(trend_summary, dict) else 0

    dimension_rows = _dimension_index(scorecard)
    dimension_signals: list[dict[str, Any]] = []
    indexed_signals: dict[str, dict[str, Any]] = {}
    for name, row in dimension_rows.items():
        dimension_score = int(row.get("score", 0))
        risk_level = risk_level_from_score(dimension_score)
        posture = recommended_posture(
            dimension_name=name,
            risk_level=risk_level,
            confidence=confidence,
        )
        signal = make_dimension_signal(
            dimension_name=name,
            dimension_score=dimension_score,
            dimension_confidence=str(row.get("confidence", "unknown")),
            risk_level=risk_level,
            trend=trend_from_score_delta(trend_delta),
            supporting_evidence_refs=[str(item) for item in row.get("key_inputs", []) if isinstance(item, str)],
            policy_relevance=[name.lower().replace(" ", "_")],
            recommended_action_posture=posture,
        )
        dimension_signals.append(signal)
        indexed_signals[name] = signal

    mapped = map_to_policy_candidates(
        score=score,
        confidence=confidence,
        freshness=freshness,
        dimensions=indexed_signals,
        trend_delta=trend_delta,
    )
    ranked_candidates = rank_candidates(mapped["recommended_policy_candidates"])

    warnings = [str(item) for item in scorecard.get("top_risks", []) if isinstance(item, str)]
    warnings.extend(mapped["warnings"])
    if _has_conflicting_dimension_signals(scorecard):
        ranked_candidates = []
        mapped["recommended_no_act_candidates"].append(
            {
                "name": "conflicting_evidence_no_action",
                "reason": "conflicting_dimension_signals_detected",
            }
        )
        warnings.append("Conflicting evidence across dimensions suppressed policy candidates.")
    if freshness_blocks_action:
        warnings.append("Freshness policy blocks action-oriented handoff.")
    if confidence_blocks_action:
        warnings.append("Confidence policy blocks action-oriented handoff.")

    policy_input = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "score": score,
        "band": band,
        "confidence": confidence,
        "confidence_reasons": confidence_reasons,
        "freshness": freshness,
        "freshness_reasons": freshness_reasons,
        "dimension_signals": dimension_signals,
        "recommended_policy_candidates": ranked_candidates,
        "recommended_no_act_candidates": mapped["recommended_no_act_candidates"],
        "recommended_escalations": mapped["recommended_escalations"],
        "required_prechecks": mapped["required_prechecks"],
        "required_evidence_refresh": mapped["required_evidence_refresh"],
        "warnings": sorted(set(warnings)),
        "generated_at": scorecard.get("generated_at"),
    }
    policy_input["policy_handoff"] = build_policy_handoff(
        policy_input=policy_input,
        policy_catalog=policy_catalog,
    )
    return policy_input
