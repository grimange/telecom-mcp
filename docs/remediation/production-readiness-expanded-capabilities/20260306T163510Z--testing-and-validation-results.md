# Testing and Validation Results

## tests added
- `tests/test_tools_contract_smoke.py::test_authenticated_caller_required_by_default`
- `tests/test_tools_contract_smoke.py::test_default_capability_policy_denies_validation_outside_lab_profile`

## tests updated
- `tests/test_tools_contract_smoke.py`
  - execute-safe validation/remediation paths now run under explicit class policy env in test setup
- `tests/test_mcp_server_stage10.py`
  - healthcheck policy assertions updated for hardened defaults

## negative-path coverage added
- denied validation execution when class policy env is unset in non-lab profiles
- denied unauthenticated caller requests by default

## remaining blind spots
- No distributed lock backend for active-operation concurrency across multiple processes/instances.
- At-rest evidence/state governance still relies on deployment controls outside current code path.

## validation summary
- Targeted hardening suites:
  - `pytest -q tests/test_tools_contract_smoke.py tests/test_mcp_server_stage10.py tests/test_config.py tests/test_expansion_batch4_tools.py` (pass)
- Safety/readiness rerun:
  - `pytest -q tests/test_safety_policy.py tests/test_stage03_probe_suite.py tests/test_stage03_chaos_framework.py tests/test_stage03_self_healing.py tests/test_remediation_hardening.py tests/test_release_gates.py tests/test_observability.py` (pass)
- Full regression:
  - `pytest` -> `232 passed, 2 skipped in 1.09s`
