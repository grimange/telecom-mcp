# Docs and Rollout Updates

- Timestamp (UTC): `20260306T150039Z`

## Files updated
- `README.md`
- `docs/security.md`
- `docs/runbook.md`
- `CHANGELOG.md`

## Behavior clarified
- active wrapper probes are explicitly fail-closed on delegated denial
- authenticated caller boundary options and required request fields
- production profile startup requirements and hardening env matrix
- strict state persistence and target policy enforcement behavior

## Rollout changes
- production hardening baseline now documented as explicit env profile:
  - `TELECOM_MCP_RUNTIME_PROFILE=production`
  - `TELECOM_MCP_REQUIRE_AUTHENTICATED_CALLER=1`
  - `TELECOM_MCP_AUTH_TOKEN=<value>`
  - `TELECOM_MCP_ENFORCE_TARGET_POLICY=1`
  - `TELECOM_MCP_STRICT_STATE_PERSISTENCE=1`
- SDK caller/token envs documented for authenticated dispatch.

## Operator guidance added
- how to interpret delegated wrapper failures (`failed_sources`)
- how to configure caller identity and allowlist
- how to enforce fail-closed state persistence for governance artifacts

## Remaining documentation gaps
- deeper examples for redaction edge-cases (Batch C)
- broader runbook coverage for chaos/incident score integration (Batch D)
