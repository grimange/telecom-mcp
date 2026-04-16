# Remediation Plan

## Batch A — Production blockers

### RB-001 / SH-CRIT-001
- Finding ID: `RB-001`, `SH-CRIT-001`
- Source artifacts: runtime-safety, security-hardening, remediation-batches
- Subsystem: `telecom.run_smoke_suite(active_validation_smoke)`, `telecom.run_probe` active route
- Files/modules:
  - `src/telecom_mcp/tools/telecom.py`
  - `tests/test_tools_contract_smoke.py`
  - `tests/test_stage03_probe_suite.py`
- Remediation approach:
  - add shared write-intent extraction helper for delegated active actions
  - require and propagate `reason`, `change_ticket`, optional `confirm_token` from orchestration params
  - fail closed on missing write-intent fields
- Risk of change: Low-medium (tightens active-path contract)
- Required tests:
  - server-dispatch positive propagation tests
  - server-dispatch negative tests for missing write intent
- Acceptance criteria:
  - active smoke/probe flows succeed when explicit write intent is present
  - flows fail with `VALIDATION_ERROR` when missing required intent fields
- Rollback consideration:
  - revert helper usage in active orchestration call sites if regression detected

## Batch B — Hardening before pilot

### SH-HIGH-002
- Finding ID: `SH-HIGH-002`
- Source artifacts: security-hardening, testing-evidence, remediation-batches
- Subsystem: direct originate tools
- Files/modules:
  - `src/telecom_mcp/tools/asterisk.py`
  - `src/telecom_mcp/tools/freeswitch.py`
  - `tests/test_expansion_batch4_tools.py`
- Remediation approach:
  - enforce strict destination allow-pattern validation in direct vendor originate tools
- Risk of change: Low (input validation hardening)
- Required tests:
  - direct-tool negative tests for invalid destinations
- Acceptance criteria:
  - unsupported destination strings are rejected with `VALIDATION_ERROR`
- Rollback consideration:
  - restore prior validation path only if false positives break valid numbering

### SH-HIGH-003
- Finding ID: `SH-HIGH-003`
- Source artifacts: security-hardening, testing-evidence, remediation-batches
- Subsystem: self-healing write governance
- Files/modules:
  - `src/telecom_mcp/tools/telecom.py`
  - `tests/test_stage03_self_healing.py`
- Remediation approach:
  - remove synthetic ticket fallback and require explicit `change_ticket` for write-capable self-healing policies
- Risk of change: Low-medium (intent requirement tightened)
- Required tests:
  - explicit negative tests for missing `change_ticket`
- Acceptance criteria:
  - write-capable policies fail closed when `change_ticket` missing
- Rollback consideration:
  - no rollback planned; fallback behavior is governance-weak by audit definition
