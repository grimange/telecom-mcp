# Security and Gating Fixes

## findings addressed
- `SH-MED-006`: addressed
- `OP-MED-002`: addressed
- `TV-MED-001`: addressed

## code areas changed
- production startup policy hardening:
  - `src/telecom_mcp/config.py`
- startup warning posture for write-capable runtime:
  - `src/telecom_mcp/mcp_server/server.py`
- CI transport-test enforcement:
  - `.github/workflows/ci.yml`

## hardening improvements
- production runtime profile now requires explicit capability-class policy env and valid values.
- production runtime profile now requires `observability` class presence in class policy.
- write-capable startup emits `CAPABILITY_CLASS_POLICY_UNSET` warning when class policy env is absent.
- CI now explicitly executes MCP initialize transport tests.
- operator runbook includes deterministic triage map for `contract_failure_reason`.

## residual risks
- non-production runtimes still allow implicit all-class default when class policy env is unset by design.
- CI behavior depends on dependency installation success for optional MCP package.

## intentionally deferred issues
- `GOV-LOW-001` remains deferred (post-pilot) per batch policy.
