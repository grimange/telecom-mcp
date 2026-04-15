# Security and Gating Fixes

Timestamp (UTC): 20260307T004720Z

## Findings addressed
- EXP-HARD-001 (High): capability-class misconfiguration risk in hardened profiles
- EXP-HARD-002 (Medium): strict hardening not consistently applied to pilot profile

## Code areas changed
- `src/telecom_mcp/config.py`
  - Hardened startup profile enforcement now applies to `production`, `prod`, and `pilot`.
  - Added explicit high-risk class approval guard:
    - if `TELECOM_MCP_ALLOWED_CAPABILITY_CLASSES` includes `chaos` or `remediation` in hardened profiles, startup now requires `TELECOM_MCP_ENABLE_HIGH_RISK_CAPABILITY_CLASSES=1`.

## Hardening improvements
- Startup is now more deterministic and fail-closed for pilot/prod-like rollouts.
- High-risk capability classes require explicit operator intent, reducing accidental policy drift.
- Existing safety boundaries remain intact (no relaxation of mode/target/action controls).

## Residual risks
- EXP-HARD-003 remains partially mitigated by policy/docs/tests rather than structural mode-floor changes.
- EXP-HARD-004 remains open until MCP dependency parity is enforced in CI/runtime.

## Intentionally deferred issues
- CI/runtime provisioning change to remove local MCP test skips (EXP-HARD-004).
