# Durable Closure Test Plan

Run timestamp (UTC): `20260306T161805Z`

## A. Shared-contract tests
- Added `tests/test_safety_policy.py`:
  - active target eligibility allow/deny contract
  - fail-closed required/actual details
  - shared probe destination validation contract
- Existing regression coverage retained for:
  - production-target denial
  - unsupported action rejection
  - write-intent enforcement

## B. Shared active-lifecycle tests
- Added concurrency recurrence tests in `tests/test_expansion_batch4_tools.py`:
  - vendor originate denied when shared active guard is saturated
  - probe wrapper denied when shared active guard is saturated
- Existing probe/chaos/self-healing lifecycle tests retained in:
  - `tests/test_stage03_probe_suite.py`
  - `tests/test_stage03_chaos_framework.py`
  - `tests/test_stage03_self_healing.py`

## C. Shared evidence/governance tests
- Existing suites continue to validate redaction/export safety, policy handoff restrictions, and envelope contracts.
- No new redaction-engine code introduced in this structural batch.

## D. Recurrence-prevention tests (explicit)
- Root cause: duplicated target eligibility logic
  - Guarded by `tests/test_safety_policy.py` and platform/wrapper denial tests.
- Root cause: missing shared active concurrency controls
  - Guarded by new saturation-denial tests in `tests/test_expansion_batch4_tools.py`.
- Root cause: subsystem divergence risk
  - Guarded by full regression run plus targeted stage03 suites.

## Negative-path coverage checklist
- production-target denial: covered.
- stale evidence/low-confidence suppression: existing stage03 policy-input/release-gate suites.
- unsupported action rejection: covered.
- partial cleanup failure surfacing: existing cleanup/self-healing tests.
- probe/chaos/self-healing contract divergence: stage03 suites + new shared control tests.

## Validation commands (executed)
- `pytest -q tests/test_safety_policy.py tests/test_expansion_batch4_tools.py tests/test_stage03_probe_suite.py tests/test_stage03_chaos_framework.py tests/test_stage03_self_healing.py`
- `pytest -q -ra`
