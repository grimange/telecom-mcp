# Docs and Rollout Updates

## Files updated

- `README.md`
- `docs/tools.md`
- `docs/security.md`
- `CHANGELOG.md`

## Behavior clarified

- `active_validation_smoke` now documented as requiring `params.reason` and `params.change_ticket`.
- Active class C probe example now includes explicit write intent.
- Security docs now state delegated active orchestration intent requirements and direct originate destination validation.
- Changelog documents Batch A/B remediation hardening changes.

## Rollout changes

- Active orchestration remains lab-only but now has contract-complete write-intent propagation.
- Pilot readiness gate now depends on medium-findings completion and rerun score improvement, not unresolved Batch A/B defects.

## Operator guidance added

- Operators must provide explicit change tickets for write-capable self-healing policies.
- Operators should expect fail-closed validation errors when active intent fields are missing or destination format is unsafe.

## Remaining documentation gaps

- Capability-class policy model documentation for deferred `SH-MED-004` is not yet added.
- Additional observability taxonomy docs for `OP-MED-001` are pending.
