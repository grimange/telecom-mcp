from __future__ import annotations

from telecom_mcp.release_gates import evaluate_release_gate


def _policy_input(**overrides):
    base = {
        "score": 82,
        "confidence": "high",
        "freshness": "fresh",
        "recommended_escalations": [],
        "policy_handoff": {"stop_conditions": []},
    }
    base.update(overrides)
    return base


def _validation(**overrides):
    base = {
        "smoke_status": "passed",
        "post_change_status": "passed",
        "cleanup_ok": True,
        "conflicting_evidence": False,
    }
    base.update(overrides)
    return base


def test_allow_when_confident_fresh_and_validation_clean() -> None:
    decision = evaluate_release_gate(
        policy_input=_policy_input(),
        validation=_validation(),
    )
    assert decision["decision"] == "allow"


def test_hold_when_low_confidence() -> None:
    decision = evaluate_release_gate(
        policy_input=_policy_input(confidence="low"),
        validation=_validation(),
    )
    assert decision["decision"] == "hold"
    assert "scorecard_confidence_too_low" in decision["reasons"]


def test_hold_when_stale() -> None:
    decision = evaluate_release_gate(
        policy_input=_policy_input(freshness="stale"),
        validation=_validation(),
    )
    assert decision["decision"] == "hold"
    assert "scorecard_not_fresh" in decision["reasons"]


def test_hold_when_validation_fails() -> None:
    decision = evaluate_release_gate(
        policy_input=_policy_input(),
        validation=_validation(smoke_status="failed"),
    )
    assert decision["decision"] == "hold"
    assert "smoke_validation_not_passed" in decision["reasons"]


def test_escalate_when_scorecard_requests_escalation() -> None:
    decision = evaluate_release_gate(
        policy_input=_policy_input(recommended_escalations=[{"name": "incident_burden_escalation"}]),
        validation=_validation(),
    )
    assert decision["decision"] == "escalate"
    assert "scorecard_requested_escalation" in decision["reasons"]


def test_escalate_for_high_confidence_very_low_score() -> None:
    decision = evaluate_release_gate(
        policy_input=_policy_input(score=50, confidence="high"),
        validation=_validation(),
    )
    assert decision["decision"] == "escalate"
    assert "high_confidence_low_score_release_risk" in decision["reasons"]


def test_high_risk_change_needs_stronger_score() -> None:
    decision = evaluate_release_gate(
        policy_input=_policy_input(score=80),
        validation=_validation(),
        change_context={"high_risk_change": True},
    )
    assert decision["decision"] == "hold"
    assert "high_risk_change_requires_stronger_score" in decision["reasons"]
