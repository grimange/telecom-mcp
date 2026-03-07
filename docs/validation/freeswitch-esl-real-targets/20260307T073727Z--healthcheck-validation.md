# Healthcheck Validation

## Health Tool Result
- `freeswitch.health(fs-1)` failed:
  - Correlation: `c-f54a586af47f`
  - Error: `UPSTREAM_ERROR`, details type `TypeError`

## Cross-check
- `telecom.summary(fs-1)` degraded due `freeswitch.health` internal failure.
  - Correlation: `c-608796099661`

## Outcome
Health contract remains failing on this runtime and is not yet trustworthy for automated gating.
