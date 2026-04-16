# Testing and Validation Results

Timestamp (UTC): 20260307T004720Z

## Tests added
- `tests/test_config.py`
  - `test_hardened_profile_rejects_high_risk_classes_without_explicit_enable`
  - `test_hardened_profile_allows_high_risk_classes_with_explicit_enable`
  - `test_pilot_profile_requires_hardening_controls`

## Tests updated
- Existing config hardening tests remain valid with expanded hardened-profile semantics.

## Negative-path coverage added
- Hardened-profile startup denial when high-risk capability classes are configured without explicit approval.
- Pilot-profile startup denial when mandatory hardening controls are missing.

## Remaining blind spots
- MCP initialize tests still skip in current local runtime due missing `mcp` package.

## Validation summary
- Targeted tests: `pytest -q tests/test_config.py` -> pass
- Full suite: `pytest` -> `235 passed, 2 skipped in 1.03s`
- Skips:
  - `tests/test_mcp_stdio_initialize.py` (2 skips, missing `mcp` package in current runtime)
