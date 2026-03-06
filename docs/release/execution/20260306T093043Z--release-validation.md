# Release Validation

- Timestamp (UTC): 2026-03-06T09:30:43Z

## E0 Preparation Intake

Consumed latest preparation artifacts from `docs/release/preparation/20260306T093043Z--*`.
Preparation verdict: **READY WITH ADVISORIES**.

## E1 Workflow Review

Validated release workflow has:

- tag trigger `v*`
- tag/version validation gate
- artifact build
- `twine check`
- asset publish via `gh release create`

## E2 Version/Tag Enforcement

Local planned identity:

- `pyproject.toml`: `0.1.4`
- intended tag: `v0.1.4`

Local identity check: PASS.

## Critical Post-Publish Identity Finding

Remote tag `v0.1.4` currently points to source where `pyproject.toml` still reports `version = "0.1.3"`.

This is a release identity mismatch.
