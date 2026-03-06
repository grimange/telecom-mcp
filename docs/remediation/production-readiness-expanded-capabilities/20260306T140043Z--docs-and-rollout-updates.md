# Docs and Rollout Updates

## files updated
- `README.md`
- `docs/tools.md`
- `docs/security.md`
- `docs/runbook.md`
- `docs/targets.example.yaml`
- `CHANGELOG.md`

## behavior clarified
- explicit active-flow eligibility metadata is now documented
- export-time evidence redaction and bounded scope are documented
- environment membership enforcement for rollups/promotion is documented

## rollout changes
- rollout remains gated by Batch A/B completion evidence from this run
- active frameworks require explicit lab-safe metadata and remain fail-closed by default

## operator guidance added
- added mode x environment safety matrix guidance
- added export and persistence hardening environment variables

## remaining documentation gaps
- release-profile policy for failing on MCP stdio skips is still pending
