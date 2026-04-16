# Command Model Fixes

## Status
No unsafe expansion of command surface was introduced.

## Confirmed Behavior
- Read commands continue using `api` path only.
- `bgapi` remains disallowed in connector.
- Tool-level read allowlist remains enforced in `src/telecom_mcp/tools/freeswitch.py`.
- Command response validation now better resists control-frame contamination via strict connector routing.

## Notes
Audit concern was primarily response association, not allowlist completeness. This remediation focused on deterministic response routing and validation order.
