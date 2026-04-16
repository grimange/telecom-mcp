# Security and Gating Fixes

- Timestamp (UTC): `20260306T150039Z`

## Findings addressed
- Batch A: `F-SEC-001`, `F-RT-001`, `G-TEST-001`
- Batch B: `F-SEC-002`, `F-SEC-003`, `F-SEC-004`

## Code areas changed
- Wrapper fail-closed and delegated error propagation:
  - `src/telecom_mcp/tools/telecom.py`
- Caller identity/auth boundary:
  - `src/telecom_mcp/server.py`
  - `src/telecom_mcp/mcp_server/server.py`
  - `src/telecom_mcp/logging.py`
- Startup hardening profile and target metadata policy:
  - `src/telecom_mcp/config.py`
- State persistence durability and strict-mode failure handling:
  - `src/telecom_mcp/tools/telecom.py`

## Hardening improvements
- Probe wrappers now require delegated originate success; delegated denial escalates as top-level `ok=false` with `failed_sources` details.
- Delegated wrapper flows now carry required write intent (`reason`, `change_ticket`) and optional `confirm_token` to downstream write tools.
- Optional authenticated-caller boundary added with policy envs:
  - `TELECOM_MCP_REQUIRE_AUTHENTICATED_CALLER`
  - `TELECOM_MCP_AUTH_TOKEN`
  - `TELECOM_MCP_ALLOWED_CALLERS`
- Audit records now include principal/auth context (`principal`, `principal_authenticated`, `auth_scheme`).
- Production runtime profile gate added (`TELECOM_MCP_RUNTIME_PROFILE=production`) requiring auth + target-policy + strict-persistence controls.
- Target metadata policy enforcement added for hardened mode.
- Governance state persistence hardened with lock + atomic replace and strict fail-closed behavior for critical files.

## Residual risks
- `F-SEC-005` remains: redaction is still pattern-based and may miss novel secret field names.
- `G-TEST-002` remains partially: some high-risk domains still use mocked contexts in parts of suite.
- MCP stdio transport tests remain skipped in this local runtime due missing `mcp` dependency.

## Intentionally deferred issues
- Batch C: `F-SEC-005`, `G-TEST-002`
- Batch D: `IO-001`, `GOV-001`
- Defer rationale: not required to clear Batch A/B rollout gates in this remediation run.
