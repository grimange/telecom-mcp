# Implementation Plan

## Implemented Components
- `src/telecom_mcp/scorecard_policy_inputs/schemas.py`
- `src/telecom_mcp/scorecard_policy_inputs/confidence.py`
- `src/telecom_mcp/scorecard_policy_inputs/freshness.py`
- `src/telecom_mcp/scorecard_policy_inputs/mapping.py`
- `src/telecom_mcp/scorecard_policy_inputs/ranking.py`
- `src/telecom_mcp/scorecard_policy_inputs/handoff.py`
- `src/telecom_mcp/scorecard_policy_inputs/engine.py`
- `telecom.scorecard_policy_inputs` tool in `src/telecom_mcp/tools/telecom.py`

## Integration Points
- Core server tool registry updated (`src/telecom_mcp/server.py`).
- MCP SDK wrapper tool added (`src/telecom_mcp/mcp_server/server.py`).
- `telecom.evaluate_self_healing` now consumes scorecard handoff and suppression/stop conditions.

## Design Properties
- additive, backward-compatible
- centralized mapping/freshness/confidence/no-act logic
- fixture-friendly; no live PBX requirement for tests
- scorecards remain decision support, not direct execution triggers

## Deferred
- persistent policy recommendation analytics
- dimension-level freshness metadata from upstream evidence systems
- richer evidence-pack mutation schema for scorecard handoff persistence
