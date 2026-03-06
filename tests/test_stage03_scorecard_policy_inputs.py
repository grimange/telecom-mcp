from __future__ import annotations

from types import SimpleNamespace

from telecom_mcp.tools import telecom


class _Ctx:
    def __init__(self) -> None:
        self.mode = SimpleNamespace(value="inspect")
        self._target = SimpleNamespace(id="pbx-1", type="asterisk", tags=["lab"])
        self.settings = SimpleNamespace(get_target=lambda _pbx_id: self._target)

    def call_tool_internal(self, tool_name: str, args: dict[str, object]):
        if tool_name == "telecom.audit_target":
            return {"ok": True, "data": {"score": 90, "status": "acceptable", "violations": []}}
        if tool_name == "telecom.run_smoke_suite":
            return {
                "ok": True,
                "data": {
                    "suite": args.get("name"),
                    "counts": {"passed": 4, "warning": 0, "failed": 1},
                    "warnings": [],
                },
            }
        if tool_name == "telecom.run_playbook":
            return {
                "ok": True,
                "data": {
                    "playbook": args.get("name"),
                    "status": "warning",
                    "failed_sources": [],
                },
            }
        if tool_name == "telecom.verify_cleanup":
            return {"ok": True, "data": {"clean": True}}
        if tool_name == "telecom.scorecard_target":
            _target, data = telecom.scorecard_target(self, args)
            return {"ok": True, "data": data}
        raise AssertionError(f"unexpected tool call: {tool_name}")


def _dim(name: str, score: int, confidence: str = "high") -> dict[str, object]:
    return {
        "name": name,
        "score": score,
        "weight": 15,
        "confidence": confidence,
        "key_inputs": ["fixture"],
        "positive_signals": [],
        "negative_signals": [],
        "warnings": [],
    }


def _scorecard(
    *,
    score: int = 70,
    confidence: str = "high",
    generated_at: str = "2026-03-06T12:00:00Z",
    top_strengths: list[str] | None = None,
    top_risks: list[str] | None = None,
    dimensions: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "entity_type": "pbx",
        "entity_id": "pbx-1",
        "score": score,
        "band": "degraded",
        "confidence": confidence,
        "confidence_reasons": [],
        "dimensions": dimensions
        or [
            _dim("Configuration Integrity", 80),
            _dim("Runtime Health", 60),
            _dim("Detection Readiness", 62),
            _dim("Validation Confidence", 75),
            _dim("Fault Resilience", 72),
            _dim("Incident Burden", 70),
        ],
        "top_strengths": top_strengths or [],
        "top_risks": top_risks or [],
        "trend_summary": {"absolute_change": -12},
        "generated_at": generated_at,
    }


def test_degraded_runtime_high_confidence_yields_low_risk_candidate() -> None:
    _target, data = telecom.scorecard_policy_inputs(
        _Ctx(),
        {"entity_type": "pbx", "pbx_id": "pbx-1", "scorecard": _scorecard(confidence="high")},
    )
    candidates = [
        row["policy"]
        for row in data["policy_input"]["recommended_policy_candidates"]
        if isinstance(row, dict) and "policy" in row
    ]
    assert "observability_refresh_retry" in candidates


def test_degraded_runtime_low_confidence_forces_evidence_refresh() -> None:
    _target, data = telecom.scorecard_policy_inputs(
        _Ctx(),
        {"entity_type": "pbx", "pbx_id": "pbx-1", "scorecard": _scorecard(confidence="low")},
    )
    assert data["policy_input"]["required_evidence_refresh"]
    assert "confidence_below_threshold" in data["policy_input"]["policy_handoff"]["stop_conditions"]


def test_strong_total_with_degraded_dimension_keeps_targeted_recommendation() -> None:
    card = _scorecard(score=88, confidence="high")
    card["dimensions"] = [
        _dim("Configuration Integrity", 95),
        _dim("Runtime Health", 58),
        _dim("Detection Readiness", 60),
        _dim("Validation Confidence", 90),
        _dim("Fault Resilience", 90),
        _dim("Incident Burden", 90),
    ]
    _target, data = telecom.scorecard_policy_inputs(_Ctx(), {"scorecard": card})
    candidates = [row["policy"] for row in data["policy_input"]["recommended_policy_candidates"]]
    assert "observability_refresh_retry" in candidates


def test_severe_drift_recommends_escalate_only() -> None:
    card = _scorecard(score=52, confidence="high")
    card["dimensions"] = [
        _dim("Configuration Integrity", 40),
        _dim("Runtime Health", 64),
        _dim("Detection Readiness", 62),
        _dim("Validation Confidence", 70),
        _dim("Fault Resilience", 70),
        _dim("Incident Burden", 70),
    ]
    _target, data = telecom.scorecard_policy_inputs(_Ctx(), {"scorecard": card})
    assert data["policy_input"]["recommended_escalations"]
    assert any(
        row.get("name") == "high_risk_integrity_no_automation"
        for row in data["policy_input"]["recommended_no_act_candidates"]
    )


def test_repeated_incident_burden_escalates_with_acceptable_score() -> None:
    card = _scorecard(score=78, confidence="high")
    card["dimensions"] = [
        _dim("Configuration Integrity", 85),
        _dim("Runtime Health", 82),
        _dim("Detection Readiness", 78),
        _dim("Validation Confidence", 80),
        _dim("Fault Resilience", 78),
        _dim("Incident Burden", 50),
    ]
    _target, data = telecom.scorecard_policy_inputs(_Ctx(), {"scorecard": card})
    assert any(
        row.get("reason") == "repeated_incident_burden"
        for row in data["policy_input"]["recommended_escalations"]
    )


def test_stale_scorecard_blocks_action_handoff() -> None:
    _target, data = telecom.scorecard_policy_inputs(
        _Ctx(),
        {
            "scorecard": _scorecard(generated_at="2026-03-01T00:00:00Z", confidence="high"),
        },
    )
    handoff = data["policy_input"]["policy_handoff"]
    assert handoff["action_posture"] == "no_act_or_escalate"
    assert "stale_score_with_no_refresh" in handoff["stop_conditions"]


def test_conflicting_evidence_suppresses_candidates() -> None:
    card = _scorecard(
        confidence="high",
        top_strengths=["Runtime Health is strong (92)."],
        top_risks=["Runtime Health is weak (58)."],
    )
    _target, data = telecom.scorecard_policy_inputs(_Ctx(), {"scorecard": card})
    assert data["policy_input"]["recommended_policy_candidates"] == []
    assert any(
        row.get("name") == "conflicting_evidence_no_action"
        for row in data["policy_input"]["recommended_no_act_candidates"]
    )


def test_policy_input_handoff_never_allows_direct_execution() -> None:
    _target, data = telecom.scorecard_policy_inputs(_Ctx(), {"scorecard": _scorecard()})
    assert data["policy_input"]["policy_handoff"]["no_bypass"]["direct_execution_allowed"] is False


def test_evaluate_self_healing_uses_scorecard_handoff_suppression() -> None:
    _target, data = telecom.evaluate_self_healing(
        _Ctx(),
        {
            "pbx_id": "pbx-1",
            "context": {"change_context": "post-deploy"},
        },
    )
    assert data["tool"] == "telecom.evaluate_self_healing"
    assert isinstance(data["recommended_policy_candidates"], list)
    assert isinstance(data["scorecard_policy_handoff"], dict)
