# Testing and Validation Results

## Tests added

- `tests/test_tools_contract_smoke.py`
  - `test_active_validation_smoke_propagates_write_intent`
  - `test_active_validation_smoke_missing_write_intent_fails_closed`
  - `test_active_probe_route_propagates_write_intent`
- `tests/test_stage03_self_healing.py`
  - `test_write_capable_self_healing_policy_requires_change_ticket`
- `tests/test_expansion_batch4_tools.py`
  - `test_platform_originate_probe_rejects_invalid_destination`

## Tests updated

- `tests/test_stage03_probe_suite.py`
  - updated active probe success case to include required write-intent params.

## Negative-path coverage added

- Missing write-intent in active smoke path -> `VALIDATION_ERROR`.
- Missing explicit ticket for write-capable self-healing policies -> `VALIDATION_ERROR`.
- Invalid destination in direct originate tools -> `VALIDATION_ERROR`.

## Remaining blind spots

- Capability-class authz metadata tests (`validation`, `chaos`, `remediation`, `export`) remain deferred.
- Additional non-mocked end-to-end orchestration scenarios remain deferred.

## Validation summary

- Focused remediation test run:
  - `pytest -q tests/test_tools_contract_smoke.py tests/test_stage03_probe_suite.py tests/test_stage03_self_healing.py tests/test_expansion_batch4_tools.py`
  - Result: pass
- Full regression run:
  - `pytest -ra`
  - Result: `221 passed, 2 skipped in 1.01s`
