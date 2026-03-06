# Release Failures

- Timestamp (UTC): 2026-03-06T09:30:43Z

## Failure Type

Release-content identity defect.

## Evidence

- Published tag: `v0.1.4`
- Published assets: `telecom_mcp-0.1.4-*`
- `pyproject.toml` fetched from GitHub at `ref=v0.1.4` contains `version = "0.1.3"`

## Root Cause

Release was created from remote repository state that did not include local version bump commit.

## Impact

Public release identity is inconsistent (tag/assets/versioned source mismatch).

## Immediate Remediation

1. Remove incorrect `v0.1.4` GitHub release and tag.
2. Push commit containing `project.version = 0.1.4` and changelog alignment.
3. Recreate tag/release from correct commit.
