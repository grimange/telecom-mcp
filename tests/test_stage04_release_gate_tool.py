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
            return {"ok": True, "data": {"score": 88, "status": "acceptable", "violations": []}}
        if tool_name == "telecom.run_smoke_suite":
            status = "passed"
            if args.get("name") == "registration_visibility_smoke":
                status = "passed"
            return {
                "ok": True,
                "data": {
                    "suite": args.get("name"),
                    "status": status,
                    "counts": {"passed": 4, "warning": 0, "failed": 0},
                    "warnings": [],
                },
            }
        if tool_name == "telecom.run_playbook":
            return {
                "ok": True,
                "data": {
                    "playbook": args.get("name"),
                    "status": "passed",
                    "failed_sources": [],
                },
            }
        if tool_name == "telecom.verify_cleanup":
            return {"ok": True, "data": {"clean": True}}
        if tool_name == "telecom.scorecard_target":
            _target, data = telecom.scorecard_target(self, args)
            return {"ok": True, "data": data}
        raise AssertionError(f"unexpected tool call: {tool_name}")


def test_release_gate_decision_allow_with_inline_inputs() -> None:
    _target, data = telecom.release_gate_decision(
        _Ctx(),
        {
            "pbx_id": "pbx-1",
            "policy_input": {
                "score": 86,
                "confidence": "high",
                "freshness": "fresh",
                "recommended_escalations": [],
                "policy_handoff": {"stop_conditions": []},
            },
            "validation": {
                "smoke_status": "passed",
                "post_change_status": "passed",
                "cleanup_ok": True,
                "conflicting_evidence": False,
            },
        },
    )
    assert data["tool"] == "telecom.release_gate_decision"
    assert data["decision"]["decision"] == "allow"


def test_release_gate_decision_hold_when_low_confidence() -> None:
    _target, data = telecom.release_gate_decision(
        _Ctx(),
        {
            "pbx_id": "pbx-1",
            "policy_input": {
                "score": 70,
                "confidence": "low",
                "freshness": "fresh",
                "recommended_escalations": [],
                "policy_handoff": {"stop_conditions": []},
            },
            "validation": {
                "smoke_status": "passed",
                "post_change_status": "passed",
                "cleanup_ok": True,
                "conflicting_evidence": False,
            },
        },
    )
    assert data["decision"]["decision"] == "hold"
    assert "scorecard_confidence_too_low" in data["decision"]["reasons"]


def test_release_gate_decision_escalate_when_scorecard_escalates() -> None:
    _target, data = telecom.release_gate_decision(
        _Ctx(),
        {
            "pbx_id": "pbx-1",
            "policy_input": {
                "score": 68,
                "confidence": "high",
                "freshness": "fresh",
                "recommended_escalations": [{"name": "incident_burden_escalation"}],
                "policy_handoff": {"stop_conditions": []},
            },
            "validation": {
                "smoke_status": "passed",
                "post_change_status": "passed",
                "cleanup_ok": True,
                "conflicting_evidence": False,
            },
        },
    )
    assert data["decision"]["decision"] == "escalate"
    assert "scorecard_requested_escalation" in data["decision"]["reasons"]


def test_release_gate_decision_can_derive_policy_input_and_validation() -> None:
    _target, data = telecom.release_gate_decision(_Ctx(), {"pbx_id": "pbx-1"})
    assert data["decision"]["decision"] in {"allow", "hold", "escalate"}
    assert isinstance(data["validation_summary"], dict)
