# Docs and Rollout Updates

## files updated
- `README.md`
- `docs/security.md`
- `docs/runbook.md`
- `CHANGELOG.md`

## behavior clarified
- Non-lab default class-policy posture is fail-closed to `observability` when no explicit class env is configured.
- Caller authentication is default-on outside lab/test runtime profiles.

## rollout changes
- Deployments that need advanced classes must explicitly set `TELECOM_MCP_ALLOWED_CAPABILITY_CLASSES`.
- Lab/testing workflows requiring anonymous callers must explicitly set `TELECOM_MCP_REQUIRE_AUTHENTICATED_CALLER=0`.

## operator guidance added
- Runbook clarifies hardened deployment prerequisites and capability-class default behavior.
- Security docs now describe effective caller-auth/class-policy defaults and overrides.

## remaining documentation gaps
- Explicit evidence/state at-rest retention and permission policy remains a follow-on item.
- External observability sink/alert playbooks remain a post-pilot track.
