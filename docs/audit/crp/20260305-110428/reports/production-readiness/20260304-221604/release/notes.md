# Release Notes (Draft)

## Completed
- Implemented missing v1 spec tools across Asterisk and FreeSWITCH domains.
- Enforced write safety policy: mode gate + explicit allowlist + cooldown.
- Added CLI startup error handling for config failures without traceback.
- Added/updated tests for contract, write policy, and startup behavior.
- Pinned dev dependency versions in `pyproject.toml`.

## Validation
- Contract diff: exact tool parity (`evidence/contract-tool-diff.json`).
- Tests: `20 passed` (`evidence/pytest.txt`).
- Lint/type: pass (`evidence/ruff.txt`, `evidence/mypy.txt`).

## Residual Risk
- `black --check` process behavior in this environment may require timeout guard.
