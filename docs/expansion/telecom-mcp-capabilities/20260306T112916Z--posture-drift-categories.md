# Posture Drift Categories Expansion

## Implemented
- Added module posture policy checks in `telecom.inventory`:
  - critical modules missing
  - risky modules loaded
- Added semantic `drift_categories` in `telecom.compare_targets` for posture-level differences.
- Added policy env overrides:
  - `TELECOM_MCP_CRITICAL_MODULES`
  - `TELECOM_MCP_RISKY_MODULE_PATTERNS`

## Validation
- `pytest -q` passed.
