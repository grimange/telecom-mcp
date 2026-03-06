# Post-Release Recommendations

- Timestamp (UTC): 2026-03-06T09:30:43Z

## Immediate Fix

1. Delete erroneous release `v0.1.4` and corresponding tag.
2. Push local release-prepared commits (`pyproject.toml`, `CHANGELOG.md`, workflow/docs updates).
3. Recreate `v0.1.4` from correct commit and republish.

## Hardening Next

1. Require a preflight check that reads `pyproject.toml` from remote target ref before publish.
2. Keep post-release identity audit mandatory for every release.

## Corrective Hotfix Release Needed?

Yes. A corrective release action is required because current public `v0.1.4` identity is inconsistent.
