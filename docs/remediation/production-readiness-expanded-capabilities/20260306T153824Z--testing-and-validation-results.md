# Testing and Validation Results

## tests added
- `tests/test_tools_contract_smoke.py::test_capability_class_policy_blocks_validation_tools`
- `tests/test_tools_contract_smoke.py::test_non_mocked_orchestration_records_contract_failure_taxonomy`

## tests updated
- `tests/test_observability.py`
  - validates `internal_subcall_contract_failure_count` snapshot behavior
- `tests/test_mcp_server_stage10.py`
  - validates healthcheck policy now includes capability-class metadata

## negative-path coverage added
- class-policy denial path (`NOT_ALLOWED`) for validation tool when class is excluded.
- delegated orchestration denial path captures taxonomy reason and caller->callee metric.

## remaining blind spots
- no live-PBX integration in CI for these tests (by project requirement to avoid real PBX dependency).
- taxonomy coverage is strongest for delegated policy/validation failures; live network timeout subclasses remain environment-driven.

## validation summary
- command: `pytest -ra`
- result: `223 passed, 2 skipped in 1.09s`
- skipped:
  - `tests/test_mcp_stdio_initialize.py` (2 tests) due missing optional `mcp` package in current runtime.
