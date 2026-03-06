"""Score-to-policy mapping rules for safe self-healing recommendation inputs."""

from __future__ import annotations

from typing import Any


def risk_level_from_score(score: int) -> str:
    if score <= 49:
        return "critical"
    if score <= 64:
        return "high"
    if score <= 79:
        return "medium"
    return "low"


def trend_from_score_delta(delta: int) -> str:
    if delta <= -10:
        return "deteriorating"
    if delta >= 10:
        return "improving"
    return "stable"


def recommended_posture(*, dimension_name: str, risk_level: str, confidence: str) -> str:
    if confidence in {"low", "unknown"}:
        return "collect_more_evidence"
    if dimension_name == "Configuration Integrity" and risk_level in {"high", "critical"}:
        return "escalate_only"
    if dimension_name in {"Runtime Health", "Detection Readiness"} and risk_level in {
        "high",
        "critical",
    }:
        return "evaluate_low_risk_policy"
    if dimension_name in {"Validation Confidence", "Fault Resilience", "Incident Burden"} and risk_level in {
        "high",
        "critical",
    }:
        return "evaluate_lab_only_policy"
    return "no_action"


def map_to_policy_candidates(
    *,
    score: int,
    confidence: str,
    freshness: str,
    dimensions: dict[str, dict[str, Any]],
    trend_delta: int,
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    no_act: list[dict[str, Any]] = []
    escalations: list[dict[str, Any]] = []
    required_prechecks: list[str] = []
    required_evidence_refresh: list[str] = []
    warnings: list[str] = []

    runtime = dimensions.get("Runtime Health", {})
    detection = dimensions.get("Detection Readiness", {})
    validation = dimensions.get("Validation Confidence", {})
    integrity = dimensions.get("Configuration Integrity", {})
    incidents = dimensions.get("Incident Burden", {})

    runtime_score = int(runtime.get("dimension_score", 50))
    detection_score = int(detection.get("dimension_score", 50))
    validation_score = int(validation.get("dimension_score", 50))
    integrity_score = int(integrity.get("dimension_score", 50))
    incident_score = int(incidents.get("dimension_score", 50))

    deteriorating = trend_from_score_delta(trend_delta) == "deteriorating"

    if freshness != "fresh":
        required_evidence_refresh.extend(
            [
                "refresh recent smoke results",
                "refresh recent playbook and audit evidence",
            ]
        )
        no_act.append(
            {
                "name": "stale_scorecard_no_action",
                "reason": "stale_or_unknown_freshness",
            }
        )

    if confidence in {"low", "unknown"}:
        required_evidence_refresh.append("collect stronger confidence evidence before policy evaluation")
        no_act.append(
            {
                "name": "low_confidence_no_action",
                "reason": "confidence_too_low_for_action_recommendation",
            }
        )

    if integrity_score <= 55:
        escalations.append(
            {
                "name": "escalate_high_risk_drift_change",
                "reason": "configuration_integrity_high_risk",
            }
        )
        no_act.append(
            {
                "name": "high_risk_integrity_no_automation",
                "reason": "high_risk_integrity_prohibits_automated_recovery",
            }
        )

    if runtime_score <= 64 and detection_score <= 69:
        if confidence in {"high", "medium"} and freshness == "fresh":
            candidates.append(
                {
                    "policy": "observability_refresh_retry",
                    "priority": 95 if deteriorating else 85,
                    "reason": "runtime_and_detection_degraded",
                }
            )
        else:
            no_act.append(
                {
                    "name": "observability_requires_fresh_confident_scorecard",
                    "reason": "runtime_detection_degraded_but_confidence_or_freshness_insufficient",
                }
            )

    if runtime_score <= 64 and validation_score >= 60:
        if confidence == "high" and freshness == "fresh":
            candidates.append(
                {
                    "policy": "safe_sip_reload_refresh",
                    "priority": 80,
                    "reason": "runtime_degraded_with_validation_signal",
                }
            )
            candidates.append(
                {
                    "policy": "gateway_profile_rescan",
                    "priority": 76,
                    "reason": "stale_runtime_state_may_benefit_from_profile_refresh",
                }
            )
        else:
            required_prechecks.append("verify target is lab-remediation-safe")

    if deteriorating and runtime_score <= 72 and validation_score <= 65:
        candidates.append(
            {
                "policy": "post_change_validation_failure_recovery",
                "priority": 72,
                "reason": "post_change_instability_pattern",
            }
        )

    if incident_score <= 60:
        escalations.append(
            {
                "name": "incident_burden_escalation",
                "reason": "repeated_incident_burden",
            }
        )

    if score <= 59 and confidence in {"low", "unknown"}:
        no_act.append(
            {
                "name": "low_score_low_confidence_no_action",
                "reason": "insufficient_confidence_for_low_score",
            }
        )

    if score <= 59 and confidence == "high" and integrity_score > 55 and freshness == "fresh":
        candidates.append(
            {
                "policy": "drift_triggered_lab_recovery",
                "priority": 68,
                "reason": "low_score_high_confidence_with_noncritical_integrity",
            }
        )

    if not candidates and not escalations:
        warnings.append("No actionable low-risk candidates were derived from current scorecard signals.")

    return {
        "recommended_policy_candidates": candidates,
        "recommended_no_act_candidates": no_act,
        "recommended_escalations": escalations,
        "required_prechecks": sorted(set(required_prechecks)),
        "required_evidence_refresh": sorted(set(required_evidence_refresh)),
        "warnings": warnings,
    }
