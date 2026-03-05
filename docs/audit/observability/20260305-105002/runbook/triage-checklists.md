# Triage Checklists

## First 5 minutes
- Confirm incident scope (single endpoint, trunk, or full PBX impact).
- Run `telecom.summary` for impacted `pbx_id` and preserve `correlation_id`.
- Capture `telecom.capture_snapshot` and attach to incident timeline.
- Verify current mode (`inspect` expected during triage).

## Error-driven checklist
- `TIMEOUT`: confirm PBX load/channel pressure and transport latency.
- `AUTH_FAILED`: verify secret env vars and remote auth policy changes.
- `CONNECTION_FAILED`: confirm reachability and protocol listener health.
- `UPSTREAM_ERROR`: collect raw sanitized evidence and compare fixture versions.
- `NOT_ALLOWED`: verify mode gating / write allowlist / rate limit settings.

## Escalation package
- Include affected `pbx_id`, tool names, and correlation IDs.
- Include timestamps (UTC), error code frequencies, and latest health result.
- Include sanitized audit snippets and snapshot summary.

