# Post-Release Audit Summary

- Timestamp (UTC): 2026-03-06T09:30:43Z

## Intake

- Preparation verdict: READY WITH ADVISORIES
- Execution verdict: FAILED PARTIAL
- Release result: created and assets attached

## Key Finding

Published release `v0.1.4` is identity-inconsistent:

- tag/assets imply `0.1.4`
- tagged source `pyproject.toml` reports `0.1.3`

## Final Verdict

**FAIL CRITICAL**
