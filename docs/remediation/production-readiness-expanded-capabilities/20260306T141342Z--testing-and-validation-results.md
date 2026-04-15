# Testing And Validation Results

## Tests added
- `tests/test_expansion_batch4_tools.py`
  - non-lab denial for `telecom.run_registration_probe`
  - non-lab denial for `telecom.run_trunk_probe`
  - non-lab denial for `asterisk.originate_probe`
  - non-lab denial for `freeswitch.originate_probe`
- `tests/test_stage03_scorecard_policy_inputs.py`
  - deterministic mapping metadata assertions (`mapping_revision`, `mapping_schema`, `mapping_checksum`)
  - state persistence warning visibility in `telecom.scorecard_target`

## Tests updated
- `tests/test_stage03_scorecard_policy_inputs.py`
  - replaced static default scorecard timestamp with runtime-fresh timestamp generation to prevent time-fragile baseline failures (`PRR-VER-001`)

## Negative-path coverage added
- Direct active wrapper denial on non-lab-safe targets.
- Platform originate denial on non-lab-safe targets.
- Persistence backend write failure visibility.

## Remaining blind spots
- No end-to-end stress validation for cross-target concurrent active validation bounds in this run.
- No consolidated denial telemetry summary endpoint in this run (Batch C scope).

## Validation summary
- Targeted suites:
  - `pytest -q tests/test_stage03_scorecard_policy_inputs.py tests/test_expansion_batch4_tools.py tests/test_stage03_probe_suite.py` -> pass
- Full baseline:
  - `pytest -q` -> pass (`2026-03-06` run, 0 failures)
