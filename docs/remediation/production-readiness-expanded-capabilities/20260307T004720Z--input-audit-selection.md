# Input Audit Selection

Timestamp (UTC): 20260307T004720Z

## Selected audit set
- Selected timestamp: `20260306T221301Z`
- Source root: `docs/audit/production-readiness-expanded-capabilities/`
- Files consumed:
  - `20260306T221301Z--production-readiness-summary.md`
  - `20260306T221301Z--capability-surface-inventory.md`
  - `20260306T221301Z--security-and-hardening-audit.md`
  - `20260306T221301Z--runtime-safety-and-gating-audit.md`
  - `20260306T221301Z--operability-and-observability-audit.md`
  - `20260306T221301Z--testing-and-evidence-audit.md`
  - `20260306T221301Z--release-readiness-scorecard.md`
  - `20260306T221301Z--remediation-batches.md`
  - `20260306T221301Z--final-production-readiness-report.md`

## Normalized findings list
- EXP-HARD-001
  - Severity: High
  - Subsystem: runtime policy / dispatch governance
  - Production blocker: No (pilot blocker)
  - Impacts: code + tests + docs + config
  - Validation type: startup-policy tests, negative-path policy tests
- EXP-HARD-002
  - Severity: Medium
  - Subsystem: governance durability / persistence
  - Production blocker: No (pilot hardening)
  - Impacts: policy profile enforcement + docs
  - Validation type: hardened-profile startup checks
- EXP-HARD-003
  - Severity: Medium
  - Subsystem: inspect-mode advanced flow complexity
  - Production blocker: No
  - Impacts: test coverage + docs/runbook clarity
  - Validation type: contract and negative-path tests
- EXP-HARD-004
  - Severity: Medium
  - Subsystem: MCP runtime dependency coverage
  - Production blocker: No
  - Impacts: CI/test runtime alignment
  - Validation type: environment/dependency validation

## Dependencies
- EXP-HARD-001 and EXP-HARD-002 share startup profile controls in `src/telecom_mcp/config.py`; remediate together.
- EXP-HARD-003 depends on preserving existing gating behavior; remediation is additive tests/docs, not behavior relaxation.
- EXP-HARD-004 depends on CI/runtime package provisioning (deferred in this pass).

## Deferred findings
- EXP-HARD-004 deferred:
  - reason: current runtime does not include `mcp` package in this execution context; tests remain skipped locally.
  - required follow-up: enforce MCP dependency installation in CI/runtime parity path.

## Remediation assumptions
- No widening of mutation capabilities.
- Fail-closed startup/profile behavior is preferred over permissive fallback.
- Existing tool contracts remain backward compatible unless restricted by explicit hardening policy.
