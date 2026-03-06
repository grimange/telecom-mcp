# Remediation Plan

- Timestamp (UTC): `20260306T150039Z`
- Input batch source: `20260306T143958Z--remediation-batches.md`

## Batch A — Production blockers

### Item `F-SEC-001` / `F-RT-001`
- Finding ID: `F-SEC-001`, `F-RT-001`
- Source artifact: `security-and-hardening-audit`, `runtime-safety-and-gating-audit`
- Impacted subsystem: probe wrappers (`telecom.run_registration_probe`, `telecom.run_trunk_probe`)
- Exact files/modules:
  - `src/telecom_mcp/tools/telecom.py`
  - `tests/test_expansion_batch4_tools.py`
  - `tests/test_tools_contract_smoke.py`
- Remediation approach:
  - require delegated-write success for wrapper success
  - propagate delegated error to top-level failure with `failed_sources`
  - enforce write intent/confirm token pass-through for delegated calls
- Risk of change: medium (active probe wrappers behavior intentionally made stricter)
- Required tests:
  - delegated denial -> wrapper failure
  - delegated allowlisted success path
  - confirm token propagation
- Acceptance criteria:
  - wrapper `ok=true` only when delegated write executed successfully
  - delegated denial returns `ok=false` with explicit error and delegated details
- Rollback consideration:
  - rollback would reintroduce false-success safety defect; not acceptable for pilot

### Item `G-TEST-001`
- Finding ID: `G-TEST-001`
- Source artifact: `testing-and-evidence-audit`
- Impacted subsystem: server dispatch + wrapper contract tests
- Exact files/modules:
  - `tests/test_tools_contract_smoke.py`
  - `tests/test_expansion_batch4_tools.py`
- Remediation approach:
  - add server-level integration tests through full mode/allowlist chain
- Risk of change: low
- Required tests: added and passing in full suite
- Acceptance criteria: old behavior fails tests, remediated behavior passes
- Rollback consideration: would remove blocker-detecting coverage

## Batch B — Hardening before pilot

### Item `F-SEC-002`
- Finding ID: `F-SEC-002`
- Source artifact: `security-and-hardening-audit`
- Impacted subsystem: caller authentication boundary + audit trail
- Exact files/modules:
  - `src/telecom_mcp/server.py`
  - `src/telecom_mcp/logging.py`
  - `src/telecom_mcp/mcp_server/server.py`
  - `tests/test_tools_contract_smoke.py`
  - `tests/test_mcp_server_stage10.py`
- Remediation approach:
  - add caller resolution/auth checks via env policy
  - propagate principal metadata into audit logs and envelopes
- Risk of change: medium (stricter request validation when enabled)
- Required tests: auth denial + principal logging assertions
- Acceptance criteria: authenticated-caller profile enforced and auditable
- Rollback consideration: would weaken production identity boundary

### Item `F-SEC-003`
- Finding ID: `F-SEC-003`
- Source artifact: `security-and-hardening-audit`
- Impacted subsystem: target metadata policy
- Exact files/modules:
  - `src/telecom_mcp/config.py`
  - `tests/test_config.py`
- Remediation approach:
  - enforce `environment`/`safety_tier` constraints under policy env toggle
  - reject unsafe active-validation metadata combinations
- Risk of change: low/medium (startup validation stricter under hardened mode)
- Required tests: invalid metadata denied; compliant metadata allowed
- Acceptance criteria: startup fails closed for policy violations when enabled
- Rollback consideration: would permit ambiguous/unsafe target policy in hardened rollouts

### Item `F-SEC-004`
- Finding ID: `F-SEC-004`
- Source artifact: `security-and-hardening-audit`
- Impacted subsystem: state persistence for governance artifacts
- Exact files/modules:
  - `src/telecom_mcp/tools/telecom.py`
  - `tests/test_stage03_audit_baselines.py`
  - `tests/test_stage03_self_healing.py`
- Remediation approach:
  - add locked/atomic state writes and checked reads
  - fail closed on critical governance files when strict mode enabled
- Risk of change: medium (strict mode can intentionally fail operations)
- Required tests: strict persistence negative path + coordination persistence
- Acceptance criteria: critical state persistence unreadable/unwritable -> explicit error in strict mode
- Rollback consideration: would reintroduce silent governance drift

## Batch C/D handling
- Deferred with rationale in this run:
  - Batch C: `F-SEC-005`, `G-TEST-002`
  - Batch D: `IO-001`, `GOV-001`
