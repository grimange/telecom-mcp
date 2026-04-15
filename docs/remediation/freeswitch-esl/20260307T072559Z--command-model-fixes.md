# Command Model Fixes

## Status
No command-surface expansion in this run.

## Current Position
- `bgapi` remains intentionally blocked in v1 read-first model.
- API allowlist remains enforced for read paths.

## Rationale
The latest audit identified this as a scope decision rather than a protocol bug in the implemented v1 contract.

## Follow-up
If BGAPI validation is required, implement a gated validation-only pathway with explicit safety/authorization controls.
