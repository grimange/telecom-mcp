# Structural Remediation Plan

Run timestamp (UTC): `20260306T161805Z`

## Selected workstreams

### Workstream A — Unified Gating and Mode Enforcement
- Recurrence evidence: repeated active-gating regressions (`PRX-RUN-001`, `F-SEC-001`, `RB-001`).
- Affected subsystems: `tools/telecom.py`, `tools/asterisk.py`, `tools/freeswitch.py`.
- Shared abstraction: `safety/policy.py::require_active_target_lab_safe`.
- Expected recurrence reduction: high for eligibility drift across active wrappers/vendor tools.
- Migration complexity: low-medium.
- Risk of change: low; behavior preserved as fail-closed.
- Proof required: existing + new tests for non-lab denial and shared policy behavior.

### Workstream B/C — Unified Target Eligibility + Bounded Action Controls
- Recurrence evidence: recurring target-policy drift + input validation divergence.
- Affected subsystems: same as Workstream A.
- Shared abstraction: `safety/policy.py::target_allows_active_validation` and `validate_probe_destination`.
- Expected recurrence reduction: high.
- Migration complexity: low.
- Risk of change: low.
- Proof required: destination rejection tests and active-target denial tests continue passing.

### Workstream E — Unified Retry/Cooldown/Concurrency Layer
- Recurrence evidence: `PRX-004` and repeated active-flow control concerns.
- Affected subsystems: `telecom.run_* active`, vendor originate tools.
- Shared abstraction: `execution/active_control.py::ActiveOperationController.guard`.
- Expected recurrence reduction: medium-high.
- Migration complexity: medium.
- Risk of change: medium (denials under saturation are intentional behavior change).
- Proof required: new concurrency saturation tests + regression baseline pass.

### Workstream H — Shared Result/Traceability Contract Reinforcement via Tests
- Recurrence evidence: repeated contract/test gaps (`G-TEST-001/002`, `PRX-008`).
- Affected subsystems: tests across stage03/stage04 + expansion hardening suites.
- Shared abstraction: explicit regression tests tied to shared modules.
- Expected recurrence reduction: medium.
- Migration complexity: low.
- Risk of change: low.
- Proof required: full test suite pass; targeted recurrence tests green.

## Workstreams not implemented in this batch
- Workstream D (rollback cleanup abstraction) and G (confidence/freshness central suppression) are documented for follow-on, but not required for highest-leverage recurrence elimination in this run.
