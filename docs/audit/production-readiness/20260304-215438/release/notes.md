# Release Notes (Draft)

## Highlights
- Added production-readiness audit artifacts under a timestamped PRR run directory.
- Resolved local CI gate failures in this run:
  - connector test constructor mismatch fixed
  - audit logger capture reliability fixed
  - mypy issues in tool argument parsing fixed
  - lint issues fixed

## Known Gaps
- Tool registry still lacks several spec-listed tools.
- CLI startup currently raises traceback on config errors; user-friendly startup error UX is incomplete.
- `pip-audit` reports vulnerabilities in base environment dependencies.

## Evidence
- Scorecard: `scorecard.md`
- Findings: `findings.md`
- Contract diff: `evidence/contract-tool-diff.json`
