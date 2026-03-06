# Version and Tag Plan

- Timestamp (UTC): 2026-03-06T09:27:40Z

## Current Identity

- `project.version`: `0.1.3`
- Derived tag: `v0.1.3`
- Existing local tags include: `v0.1.3`

## Assessment

Attempting a new release from current identity is invalid/ambiguous because `v0.1.3` is already present.

## Required Plan

1. Bump `project.version` to a new version (e.g., `0.1.4`).
2. Add a matching changelog section for the new version.
3. Create and push only the new tag (`v0.1.4`).

## Gate

**BLOCK** until version/tag identity is unique and consistent.
