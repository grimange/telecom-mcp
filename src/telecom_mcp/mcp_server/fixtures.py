"""Deterministic fixture scenarios for sandbox-safe MCP tools."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

SCENARIOS: dict[str, list[dict[str, Any]]] = {
    "inbound_ring": [
        {
            "call_id": "call-inbound-1001",
            "direction": "inbound",
            "state": "ringing",
            "caller": "+12065550100",
            "callee": "1001",
            "platform": "asterisk",
        }
    ],
    "originate_success": [
        {
            "call_id": "call-outbound-2001",
            "direction": "outbound",
            "state": "answered",
            "caller": "2001",
            "callee": "+12065550199",
            "platform": "asterisk",
        }
    ],
    "originate_no_answer": [
        {
            "call_id": "call-outbound-2002",
            "direction": "outbound",
            "state": "no_answer",
            "caller": "2002",
            "callee": "+12065550222",
            "platform": "freeswitch",
        }
    ],
}


@dataclass(slots=True)
class FixtureState:
    state_dir: Path
    current_scenario: str | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)

    def load_scenario(self, scenario_name: str) -> dict[str, Any]:
        if scenario_name not in SCENARIOS:
            raise KeyError(scenario_name)

        calls = deepcopy(SCENARIOS[scenario_name])
        self.current_scenario = scenario_name
        self.calls = calls
        self._persist()
        return {
            "scenario": scenario_name,
            "calls": len(calls),
        }

    def list_calls(self) -> list[dict[str, Any]]:
        return deepcopy(self.calls)

    def get_call(self, call_id: str) -> dict[str, Any] | None:
        for item in self.calls:
            if item.get("call_id") == call_id:
                return deepcopy(item)
        return None

    def _persist(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "scenario": self.current_scenario,
            "calls": self.calls,
        }
        (self.state_dir / "state.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )


def default_fixture_state() -> FixtureState:
    return FixtureState(state_dir=Path(".telecom_mcp/fixtures"))
