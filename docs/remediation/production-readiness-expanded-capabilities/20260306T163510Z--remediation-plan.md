# Remediation Plan

## PRX-001
- source artifact: `20260306T155037Z--security-and-hardening-audit.md`, `20260306T155037Z--remediation-batches.md`
- impacted subsystem: server dispatch class policy
- files/modules:
  - `src/telecom_mcp/server.py`
  - `tests/test_tools_contract_smoke.py`
  - `tests/test_mcp_server_stage10.py`
  - `README.md`, `docs/security.md`, `docs/runbook.md`
- remediation approach:
  - switch unset class policy to fail-closed `observability` in non-lab profiles
  - retain explicit lab/test compatibility via runtime profile (`lab`, `test`, `ci`, `dev`)
  - add negative-path test for default validation denial
- risk of change: medium (default policy hardening can deny previously allowed advanced tools)
- required tests: dispatch denial tests, wrapper tests, full regression
- acceptance criteria:
  - unset class policy denies `validation/chaos/remediation/export` tools in non-lab profiles
  - explicit class policy still enables intended classes
- rollback consideration: restore prior default-open behavior only with explicit risk acceptance

## PRX-002
- source artifact: `20260306T155037Z--security-and-hardening-audit.md`, `20260306T155037Z--remediation-batches.md`
- impacted subsystem: request caller-auth boundary
- files/modules:
  - `src/telecom_mcp/server.py`
  - `src/telecom_mcp/mcp_server/server.py`
  - `tests/test_tools_contract_smoke.py`
  - `tests/test_mcp_server_stage10.py`
  - `README.md`, `docs/security.md`, `docs/runbook.md`
- remediation approach:
  - require authenticated caller by default outside lab/test runtime profiles
  - preserve explicit lab/testing override via `TELECOM_MCP_REQUIRE_AUTHENTICATED_CALLER=0`
  - keep MCP SDK internal caller identity explicit and non-ambiguous in audit context
- risk of change: medium (stricter default auth behavior)
- required tests: auth negative-path tests + MCP health policy assertions
- acceptance criteria:
  - unauthenticated request path denied by default
  - healthcheck reports effective caller-auth policy correctly
- rollback consideration: return to opt-in auth only if rollout policy explicitly accepts risk

## PRX-003 / PRX-004 revalidation
- source artifact: `20260306T155037Z--runtime-safety-and-gating-audit.md`, `20260306T155037Z--remediation-batches.md`
- impacted subsystem: strict persistence + active concurrency
- files/modules: no net-new code in this run; rerun validation suites
- remediation approach: revalidate existing controls and ensure no regression from Batch A changes
- risk of change: low
- required tests: strict persistence tests, active concurrency tests, chaos/probe/self-healing suites
- acceptance criteria: all targeted suites pass with no behavior regressions
- rollback consideration: none needed (validation-only)
