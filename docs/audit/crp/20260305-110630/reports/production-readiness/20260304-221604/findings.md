# Findings

## High
1. None.

## Medium
1. `black --check` command stability issue in this host/runtime.
- Evidence: `evidence/black.txt` (reports unchanged files but exits by timeout guard)
- Impact: CI formatting gate may require command timeout workaround in this environment.

## Low
1. Dependency vulnerability scan is metadata-scoped due host limitation creating temporary venvs.
- Evidence: `evidence/deps-vuln.txt`
- Impact: Runtime risk posture is accurate for current project metadata (no runtime deps), but not a full transitive install-time audit.

## Resolved In This Run
1. Full tool contract parity achieved.
- Evidence: `evidence/contract-tool-diff.json` (`missing_from_registry` and `extra_in_registry` are empty).

2. Write safety gating implemented and tested.
- Code: `src/telecom_mcp/server.py`
- Tests: `tests/test_tools_contract_smoke.py`

3. Startup error UX improved.
- Code: `src/telecom_mcp/server.py`
- Evidence: `evidence/startup-missing-config.txt`.

4. Static and test quality gates pass.
- Evidence: `evidence/pytest.txt`, `evidence/ruff.txt`, `evidence/mypy.txt`.
