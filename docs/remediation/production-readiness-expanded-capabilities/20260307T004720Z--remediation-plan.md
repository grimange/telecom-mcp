# Remediation Plan

Timestamp (UTC): 20260307T004720Z

## Batch A - Production blockers
- None from selected audit set.

## Batch B - Hardening before pilot
- Finding ID: EXP-HARD-001
  - Source: `20260306T221301Z--security-and-hardening-audit.md`
  - Subsystem: runtime capability-class governance
  - Files: `src/telecom_mcp/config.py`, `tests/test_config.py`, `README.md`, `docs/security.md`, `docs/runbook.md`
  - Approach: require explicit approval env when hardened profiles enable `chaos`/`remediation` classes
  - Risk: medium (startup-policy tightening)
  - Tests: new `test_config.py` cases for deny/allow behavior
  - Acceptance: hardened profile startup fails closed without explicit high-risk class approval
  - Rollback: remove added env gate and tests
- Finding ID: EXP-HARD-002
  - Source: `20260306T221301Z--security-and-hardening-audit.md`
  - Subsystem: hardened profile durability controls
  - Files: `src/telecom_mcp/config.py`, `tests/test_config.py`, docs/changelog
  - Approach: extend production-grade startup hardening to `pilot` runtime profile
  - Risk: medium (pilot startup can now fail without required controls)
  - Tests: new pilot-profile hardening test
  - Acceptance: `TELECOM_MCP_RUNTIME_PROFILE=pilot` enforces mandatory hardening controls
  - Rollback: narrow hardening profile back to production/prod only

## Batch C - Pilot stabilization
- Finding ID: EXP-HARD-003
  - Source: `20260306T221301Z--runtime-safety-and-gating-audit.md`
  - Subsystem: advanced flow gating complexity
  - Files: tests/docs only in this pass
  - Approach: preserve code behavior, strengthen explicit policy docs and existing gating test traceability
  - Risk: low
  - Tests: full suite rerun
  - Acceptance: no regression; policy behavior documented

## Batch D - Post-pilot improvements
- Finding ID: EXP-HARD-004
  - Source: `20260306T221301Z--testing-and-evidence-audit.md`
  - Subsystem: MCP runtime dependency in test environment
  - Files: CI/runtime env not changed in this pass
  - Approach: defer with explicit note
  - Risk: low-medium
  - Acceptance (future): no skipped MCP initialize tests in CI

