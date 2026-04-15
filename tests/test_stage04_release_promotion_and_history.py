from __future__ import annotations

from types import SimpleNamespace

import pytest

from telecom_mcp.errors import ToolError, VALIDATION_ERROR
from telecom_mcp.tools import telecom


class _Ctx:
    def __init__(self) -> None:
        self.mode = SimpleNamespace(value="inspect")
        self._targets = {
            "pbx-1": SimpleNamespace(id="pbx-1", type="asterisk", environment="staging"),
            "fs-1": SimpleNamespace(id="fs-1", type="freeswitch", environment="staging"),
        }
        self.settings = SimpleNamespace(get_target=self._get_target)

    def _get_target(self, pbx_id: str):
        return self._targets[pbx_id]

    def call_tool_internal(self, tool_name: str, args: dict[str, object]):
        if tool_name == "telecom.audit_target":
            score = 88 if args.get("pbx_id") == "pbx-1" else 72
            return {"ok": True, "data": {"score": score, "status": "acceptable", "violations": []}}
        if tool_name == "telecom.run_smoke_suite":
            return {
                "ok": True,
                "data": {
                    "suite": args.get("name"),
                    "status": "passed",
                    "counts": {"passed": 3, "warning": 0, "failed": 0},
                    "warnings": [],
                },
            }
        if tool_name == "telecom.run_playbook":
            return {"ok": True, "data": {"playbook": args.get("name"), "status": "passed", "failed_sources": []}}
        if tool_name == "telecom.verify_cleanup":
            return {"ok": True, "data": {"clean": True}}
        if tool_name == "telecom.scorecard_target":
            _target, data = telecom.scorecard_target(self, args)
            return {"ok": True, "data": data}
        raise AssertionError(f"unexpected tool call: {tool_name}")


def test_release_promotion_decision_aggregates_members() -> None:
    _target, data = telecom.release_promotion_decision(
        _Ctx(),
        {
            "environment_id": "staging",
            "pbx_ids": ["pbx-1", "fs-1"],
            "context": {"high_risk_change": False},
        },
    )
    assert data["tool"] == "telecom.release_promotion_decision"
    assert data["decision"]["decision"] in {"allow", "hold", "escalate"}
    assert len(data["members"]) == 2


def test_release_gate_history_tracks_and_rolls_up() -> None:
    ctx = _Ctx()
    _ = telecom.release_gate_decision(ctx, {"pbx_id": "pbx-1"})
    _ = telecom.release_gate_decision(ctx, {"pbx_id": "pbx-1", "context": {"high_risk_change": True}})

    _target, history = telecom.release_gate_history(
        ctx,
        {"entity_type": "pbx", "entity_id": "pbx-1", "limit": 10},
    )
    assert history["tool"] == "telecom.release_gate_history"
    assert history["counts"]["allow"] + history["counts"]["hold"] + history["counts"]["escalate"] >= 2
    assert len(history["entries"]) >= 2


def test_release_promotion_requires_membership_alignment() -> None:
    with pytest.raises(ToolError) as exc:
        telecom.release_promotion_decision(
            _Ctx(),
            {
                "environment_id": "production",
                "pbx_ids": ["pbx-1"],
            },
        )
    assert exc.value.code == VALIDATION_ERROR
