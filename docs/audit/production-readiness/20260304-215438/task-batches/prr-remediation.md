# PRR Remediation Batch

## Executed In This Run
- [x] Fix failing unit tests (`tests/test_connectors.py`, `src/telecom_mcp/logging.py`).
- [x] Remove lint error (`tests/test_config.py`).
- [x] Fix mypy errors in tool argument parsing (`src/telecom_mcp/tools/telecom.py`, `src/telecom_mcp/tools/asterisk.py`).
- [x] Re-run Phase 1-8 quality/security/perf checks once.

## Remaining Tasks
- [ ] Implement missing spec tools from `docs/telecom-mcp-tool-specification.md`.
- [ ] Add CLI-friendly startup error handling (no traceback for expected config/user errors).
- [ ] Add explicit tests for cooldown/allowlist path once write tools are introduced.
- [ ] Introduce pinned dependency policy for non-empty runtime/dev dependency sets.
- [ ] Address `pip-audit` vulnerability findings in target runtime image/base environment.
