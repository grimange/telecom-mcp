# Docs And Rollout Updates

## Files updated
- `README.md`
- `docs/security.md`
- `docs/runbook.md`
- `CHANGELOG.md`

## Behavior clarified
- Active probe wrappers and platform originate tools are explicitly fail-closed unless targets are lab-safe.
- Scorecard policy input outputs now include deterministic mapping provenance fields.
- Persistence failures are documented as non-fatal but visible warnings.

## Rollout changes
- Rollout posture shifts from blocker state toward pilot-readiness with conditions once rerun validation is green.
- Production rollout still requires Batch C/D governance maturity items and operational telemetry refinements.

## Operator guidance added
- Runbook now calls out denial diagnostics (`required` vs `actual` eligibility details).
- Security docs now state direct-wrapper and platform defense-in-depth enforcement behavior.

## Remaining documentation gaps
- Dedicated denial-reason troubleshooting matrix doc remains pending (Batch C).
- Consolidated guardrail telemetry report guidance remains pending (Batch C).
