from __future__ import annotations

from types import SimpleNamespace

import pytest

from telecom_mcp.errors import ToolError, VALIDATION_ERROR
from telecom_mcp.tools import telecom


@pytest.fixture(autouse=True)
def _reset_score_state() -> None:
    telecom._SCORECARD_HISTORY.clear()


class _Ctx:
    def __init__(self) -> None:
        self.mode = SimpleNamespace(value="inspect")
        self.settings = SimpleNamespace(
            targets=[
                SimpleNamespace(id="pbx-1", type="asterisk"),
                SimpleNamespace(id="fs-1", type="freeswitch"),
            ],
            get_target=self._get_target,
        )

    def _get_target(self, pbx_id: str):
        if pbx_id == "pbx-1":
            return SimpleNamespace(id="pbx-1", type="asterisk")
        return SimpleNamespace(id="fs-1", type="freeswitch")

    def call_tool_internal(self, tool_name: str, args: dict[str, object]):
        if tool_name == "telecom.audit_target":
            return {
                "ok": True,
                "data": {
                    "score": 88,
                    "status": "acceptable",
                    "violations": [
                        {
                            "policy_id": "TLS_AVAILABLE",
                            "severity": "warning",
                            "message": "tls signal weak",
                        }
                    ],
                },
            }
        if tool_name == "telecom.run_smoke_suite":
            return {
                "ok": True,
                "data": {
                    "suite": args.get("name"),
                    "counts": {"passed": 4, "warning": 1, "failed": 0},
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
        if tool_name == "telecom.scorecard_cluster":
            _target, data = telecom.scorecard_cluster(self, args)
            return {"ok": True, "data": data}
        if tool_name == "telecom.scorecard_environment":
            _target, data = telecom.scorecard_environment(self, args)
            return {"ok": True, "data": data}
        raise AssertionError(f"unexpected tool call: {tool_name}")


def test_scorecard_target_returns_dimensions_and_confidence() -> None:
    _target, data = telecom.scorecard_target(_Ctx(), {"pbx_id": "pbx-1"})
    card = data["scorecard"]
    assert card["entity_type"] == "pbx"
    assert len(card["dimensions"]) == 6
    assert card["confidence"] in {"high", "medium", "low"}


def test_scorecard_cluster_and_environment_rollup() -> None:
    ctx = _Ctx()
    _target, cluster = telecom.scorecard_cluster(
        ctx, {"cluster_id": "cluster-a", "pbx_ids": ["pbx-1", "fs-1"]}
    )
    assert cluster["scorecard"]["entity_type"] == "cluster"

    _target, env = telecom.scorecard_environment(
        ctx, {"environment_id": "prod", "pbx_ids": ["pbx-1", "fs-1"]}
    )
    assert env["scorecard"]["entity_type"] == "environment"


def test_scorecard_compare_and_trend() -> None:
    ctx = _Ctx()
    _ = telecom.scorecard_target(ctx, {"pbx_id": "pbx-1"})
    _ = telecom.scorecard_target(ctx, {"pbx_id": "pbx-1"})

    _target, compare = telecom.scorecard_compare(
        ctx, {"entity_type": "pbx", "entity_a": "pbx-1", "entity_b": "fs-1"}
    )
    assert compare["tool"] == "telecom.scorecard_compare"

    _target, trend = telecom.scorecard_trend(
        ctx, {"entity_type": "pbx", "entity_id": "pbx-1", "window": "30d"}
    )
    assert trend["tool"] == "telecom.scorecard_trend"


def test_scorecard_export_markdown() -> None:
    ctx = _Ctx()
    _ = telecom.scorecard_target(ctx, {"pbx_id": "pbx-1"})
    _target, data = telecom.scorecard_export(
        ctx,
        {
            "entity_type": "pbx",
            "entity_id": "pbx-1",
            "format": "markdown",
            "pbx_ids": ["pbx-1", "fs-1"],
        },
    )
    assert "Telecom Resilience Scorecard" in data["export"]


def test_scorecard_cluster_requires_members() -> None:
    with pytest.raises(ToolError) as exc:
        telecom.scorecard_cluster(_Ctx(), {"cluster_id": "cluster-a", "pbx_ids": []})
    assert exc.value.code == VALIDATION_ERROR
