# BGAPI Validation

## Attempt
- Command: `bgapi status`
- Correlation: `c-661416c02659`

## Result
- Rejected as `NOT_ALLOWED` by read-only API allowlist.

## Interpretation
BGAPI correlation behavior (`Job-UUID` + `BACKGROUND_JOB`) remains untestable in current runtime policy.
