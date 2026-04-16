# Remediation Plan

## SH-MED-006
- source artifact: `20260306T154130Z--security-and-hardening-audit.md`
- impacted subsystem: production hardening profile and startup policy posture
- files/modules:
  - `src/telecom_mcp/config.py`
  - `src/telecom_mcp/mcp_server/server.py`
  - `tests/test_config.py`
  - `tests/test_mcp_server_stage10.py`
- remediation approach:
  - require explicit `TELECOM_MCP_ALLOWED_CAPABILITY_CLASSES` in production profile startup checks
  - validate capability-class values and required `observability` class
  - add startup warning when running write-capable modes without explicit class policy env
- risk of change: medium (harder startup requirements for production profile)
- required tests: config profile acceptance/rejection tests + startup warning test
- acceptance criteria:
  - production profile fails when class policy env missing or invalid
  - healthcheck/startup warnings surface missing class policy in write-capable mode
- rollback consideration: remove class-policy requirement from production profile check if incompatible with deployment constraints

## OP-MED-002
- source artifact: `20260306T154130Z--operability-and-observability-audit.md`
- impacted subsystem: operator triage documentation
- files/modules:
  - `docs/runbook.md`
  - `docs/security.md`
  - `README.md`
- remediation approach:
  - add explicit `contract_failure_reason` triage matrix mapping reason -> first response action
  - cross-reference triage section from security/readme hardening notes
- risk of change: low (documentation only)
- required tests: n/a (doc remediation)
- acceptance criteria:
  - runbook includes concrete reason-code mapping table
  - top-level docs point operators to runbook mapping
- rollback consideration: doc-only; revert section if taxonomy schema changes

## TV-MED-001
- source artifact: `20260306T154130Z--testing-and-evidence-audit.md`
- impacted subsystem: CI/test gating
- files/modules:
  - `.github/workflows/ci.yml`
- remediation approach:
  - add explicit CI step for `tests/test_mcp_stdio_initialize.py` before full pytest
  - capture local `.venv` proof showing MCP initialize tests execute without skip
- risk of change: low (workflow additive)
- required tests: workflow static check + local targeted test run
- acceptance criteria:
  - CI invokes MCP initialize tests explicitly
  - local evidence shows `2 passed` in aligned environment
- rollback consideration: remove explicit test step if redundant with future test partitioning
