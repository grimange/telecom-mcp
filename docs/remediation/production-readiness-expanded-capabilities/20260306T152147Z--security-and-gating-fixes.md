# Security and Gating Fixes

## Findings addressed

- Closed in this run:
  - `RB-001`
  - `SH-CRIT-001`
  - `SH-HIGH-002`
  - `SH-HIGH-003`

## Code areas changed

- `src/telecom_mcp/tools/telecom.py`
  - Added `_require_write_intent_fields(...)`.
  - `active_validation_smoke` now requires and propagates delegated write intent.
  - Class C probe active route now requires and propagates delegated write intent.
  - Removed synthetic `AUTO-SH-LAB` fallback.
  - Added explicit `change_ticket` requirement for write-capable self-healing policies.
- `src/telecom_mcp/tools/asterisk.py`
  - Added strict destination validation helper and allow-pattern enforcement in `originate_probe`.
- `src/telecom_mcp/tools/freeswitch.py`
  - Added strict destination validation helper and allow-pattern enforcement in `originate_probe`.

## Hardening improvements

- Delegated active operations now preserve caller write intent end-to-end.
- Active orchestration fails closed before subcall when write intent is incomplete.
- Direct vendor originate tools now reject overscoped destination strings.
- Write-governance traces no longer accept synthesized self-healing ticket IDs.

## Residual risks

- `SH-MED-004`: capability-class metadata not yet first-class in authz model.
- `SH-MED-005`: deeper non-mocked integration profile still pending.
- `OP-MED-001`: explicit internal orchestration failure telemetry taxonomy still pending.

## Intentionally deferred issues

- Deferred per source batch policy: `SH-MED-004`, `SH-MED-005`, `OP-MED-001`.
