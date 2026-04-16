# Docs and Rollout Updates

## files updated
- `README.md`
- `docs/security.md`
- `CHANGELOG.md`

## behavior clarified
- capability classes are explicit dispatch metadata and can be constrained by policy env.
- delegated internal subcall contract failures now expose reason taxonomy in evidence.

## rollout changes
- optional control for runtime hardening:
  - `TELECOM_MCP_ALLOWED_CAPABILITY_CLASSES`
- default runtime behavior remains backward compatible (all capability classes allowed unless constrained).

## operator guidance added
- triage can now key off `failed_sources[*].contract_failure_reason` for faster root-cause mapping.
- healthcheck policy now exposes class-level posture for runtime verification.

## remaining documentation gaps
- no dedicated runbook table yet mapping each reason code to specific operator playbook steps.
