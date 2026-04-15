# Batch 4 Hardening Follow-up

## Enhancements implemented
- Added destination format validation for probe tools.
- Added per-target probe throttling with `TELECOM_MCP_PROBE_MAX_PER_MINUTE`.
- Added probe timeout cap with `TELECOM_MCP_PROBE_MAX_TIMEOUT_S`.
- Added probe ID propagation into vendor originate actions.
- Added probe registry tracking and cleanup correlation by `probe_id`.
- Extended `telecom.verify_cleanup` to accept `probe_id`.

## Validation
- `pytest -q` passed after hardening updates.
