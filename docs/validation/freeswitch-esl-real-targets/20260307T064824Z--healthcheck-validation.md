# Healthcheck Validation

## Health Tool Result
- `freeswitch.health(fs-1)` failed twice:
  - `c-07567a08050f`
  - `c-899ec50afd59`
- Error: `UPSTREAM_ERROR`, details: `TypeError`

## Cross-check Impact
- `telecom.summary(fs-1)` (`c-51d44eaefdf6`) marked degraded and lists failed source `freeswitch.health`.

## Assessment
Health contract is currently failing on real target in this runtime and is not production-trustworthy until the deployed runtime picks up the remediation fixset.
