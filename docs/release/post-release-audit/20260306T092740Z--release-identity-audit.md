# Release Identity Audit

- Timestamp (UTC): 2026-03-06T09:27:40Z

## Compared Identities

- `pyproject.toml`: `0.1.3`
- planned tag: `v0.1.3`
- execution publish result: not executed
- artifact filenames: `telecom_mcp-0.1.3-*`

## Finding

Identity is internally consistent for `0.1.3`, but unusable for a *new* publish cycle because the tag already exists.

## Severity

- Critical for current release execution attempt.
