# Docs and Rollout Updates

## files updated
- `README.md`
- `docs/security.md`
- `docs/runbook.md`
- `CHANGELOG.md`

## behavior clarified
- production profile now requires explicit `TELECOM_MCP_ALLOWED_CAPABILITY_CLASSES` including `observability`.
- delegated contract-failure triage now has explicit runbook mapping.

## rollout changes
- CI includes explicit MCP initialize transport test execution step.
- hardened deployments should now treat class-policy env as mandatory production configuration.

## operator guidance added
- runbook `Internal Contract Failure Triage` table maps `contract_failure_reason` to first-response actions.
- README/security link operators to this table.

## remaining documentation gaps
- post-pilot governance reporting for taxonomy trend analytics remains open under deferred `GOV-LOW-001`.
