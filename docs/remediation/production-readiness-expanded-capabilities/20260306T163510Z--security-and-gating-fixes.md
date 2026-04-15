# Security and Gating Fixes

## findings addressed
- `PRX-001`: addressed
- `PRX-002`: addressed
- `PRX-003`: revalidated
- `PRX-004`: revalidated

## code areas changed
- dispatch class-policy defaults and caller-auth defaults:
  - `src/telecom_mcp/server.py`
- MCP SDK health policy reporting alignment:
  - `src/telecom_mcp/mcp_server/server.py`
- safety regression and contract coverage updates:
  - `tests/test_tools_contract_smoke.py`
  - `tests/test_mcp_server_stage10.py`

## hardening improvements
- Unset capability-class policy now fails closed to `observability` for non-lab runtime profiles.
- Caller authentication is now default-on for non-lab runtime profiles.
- MCP SDK internal dispatch remains explicit (`mcp-sdk`) and health output reflects effective caller-auth posture.
- Existing strict-persistence and shared active-concurrency controls were rerun and remained intact.

## residual risks
- Distributed/multi-process concurrency coordination remains process-local.
- At-rest evidence/state governance policy (permissions/retention/encryption strategy) is not fully closed in this run.

## intentionally deferred issues
- `PRX-005`, `PRX-006` (Batch C) deferred with documented rationale.
- `PRX-007`, `PRX-008` (Batch D) deferred to post-pilot hardening track.
