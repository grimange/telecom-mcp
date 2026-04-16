# FreeSWITCH ESL Real-Target Validation Summary

## Run Metadata
- Date (UTC): 2026-03-07
- Target: `fs-1` (`38.107.174.40:8021`)
- Prompt: `docs/prompts/freeswitch/03-esl-validation.md`
- Compared against previous run: `20260307T064824Z`

## Verdict
Partial pass, unchanged on core runtime failures.

## Passed Areas
- Real target reachable and API read commands execute successfully.
- Safe error mapping for blocked commands (`NOT_ALLOWED`) and missing channel (`NOT_FOUND`).
- Snapshot collection succeeded this run (previous run timed out).

## Failing / Degraded Areas
- `freeswitch.health` still fails with `UPSTREAM_ERROR` (`TypeError`).
- `freeswitch.version` still returns parsed `unknown` while raw contains `1.10.11-release`.
- `freeswitch.sofia_status` parser still under-parses real table output (subset only).
- `bgapi` contract validation blocked by read-only allowlist policy.

## Before/After Delta vs 20260307T064824Z
- Improved: `telecom.capture_snapshot` succeeded in this run.
- Unchanged: health failure, version parse mismatch, Sofia under-parse, BGAPI blocked.
