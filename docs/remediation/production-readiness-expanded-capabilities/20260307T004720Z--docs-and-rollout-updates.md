# Docs and Rollout Updates

Timestamp (UTC): 20260307T004720Z

## Files updated
- `README.md`
- `docs/security.md`
- `docs/runbook.md`
- `CHANGELOG.md`

## Behavior clarified
- Hardened runtime profiles are now documented as `production|prod|pilot`.
- High-risk capability classes (`chaos`, `remediation`) require explicit approval env in hardened profiles.

## Rollout changes
- Pilot rollouts now require the same startup hardening posture as production/prod-like runs.
- Operators must explicitly opt in before enabling high-risk capability classes.

## Operator guidance added
- Runbook now includes the explicit high-risk capability-class approval requirement.

## Remaining documentation gaps
- CI/runtime parity steps for ensuring MCP dependency availability can be made more explicit in release/runbook docs.
