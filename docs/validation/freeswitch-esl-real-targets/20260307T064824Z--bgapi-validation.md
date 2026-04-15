# BGAPI Validation

## Attempt
- Command attempted: `bgapi status`
- Tool: `freeswitch.api`
- Correlation: `c-0ce9334915a8`

## Result
- Rejected with `NOT_ALLOWED`
- Reason: command not in read-only allowlist.

## Contract Interpretation
Current v1 runtime intentionally blocks `bgapi` through tool policy, so real-target BGAPI correlation (`Job-UUID` + `BACKGROUND_JOB`) cannot be validated in this mode.

## Follow-up
If BGAPI validation is required, add a gated validation-only path that is explicitly allowed in `execute_safe` with strict safety controls.
