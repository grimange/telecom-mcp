# Healthcheck Fixes

## Implemented
- `freeswitch.health` now validates read response semantics immediately after `status` and `version` calls.
- Version parsing fixed to correctly extract values like `1.10.11-release`.
- Health normalization now accepts profile list input instead of forcing empty profiles.

## Files
- `src/telecom_mcp/tools/freeswitch.py`
- `src/telecom_mcp/normalize/freeswitch.py`

## Result
Health output is more protocol-trustworthy under framing/session anomalies and better aligned with expected contract fields.
