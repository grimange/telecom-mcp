# Findings

## Critical
1. Spec/implementation mismatch: 9 spec-listed tools are missing from the active tool registry.
- Evidence: `evidence/contract-tool-diff.json`
- Registry source: `src/telecom_mcp/server.py:51`
- Missing tools: `asterisk.bridges`, `asterisk.channel_details`, `asterisk.pjsip_show_registration`, `asterisk.reload_pjsip`, `freeswitch.calls`, `freeswitch.gateway_status`, `freeswitch.registrations`, `freeswitch.reloadxml`, `freeswitch.sofia_profile_rescan`
- Impact: Contract completeness gap vs documented tool catalog.

2. Dependency vulnerability exposure in runtime environment (31 known vulns across 11 packages).
- Evidence: `evidence/deps-vuln.txt`
- Impact: Security risk in production deployment environment.

## High
1. CLI startup error UX is not production-friendly for expected user/config errors.
- Evidence: `evidence/startup-missing-config.txt`
- Code path: `src/telecom_mcp/server.py:174`, `src/telecom_mcp/config.py:232`
- Impact: Expected configuration failures surface as Python traceback rather than clean user-facing error output.

2. Black check in this environment requires timeout guard (`exit_code=124`), despite reporting unchanged files.
- Evidence: `evidence/black.txt`
- Impact: Non-deterministic formatting gate behavior in CI-like runs.

## Medium
1. Write safety controls are not fully demonstrable yet because there are no active write tools.
- Evidence: tool registry is inspect-only at `src/telecom_mcp/server.py:51`; cooldown helper exists but is not integrated (`src/telecom_mcp/rate_limit.py:1`).
- Impact: Mode gating, allowlist, and cooldown policies are only partially exercised by current tool surface.

2. Performance regression gate cannot be evaluated this run due missing prior baseline.
- Evidence: `perf/benchmarks.md`
- Impact: PRR phase gate “regression vs previous scorecard” is currently N/A.

## Resolved During This Run
1. Failing tests fixed:
- `tests/test_connectors.py` ARIConfig constructor now provides `app`.
- `src/telecom_mcp/logging.py` logger handler binding updated for deterministic stderr capture.

2. Quality/type issues fixed:
- `tests/test_config.py` unused import removed.
- `src/telecom_mcp/tools/telecom.py` and `src/telecom_mcp/tools/asterisk.py` now use typed dict-arg parsing helpers.

3. Post-remediation gate status:
- `pytest`: pass (`evidence/pytest.txt`)
- `ruff`: pass (`evidence/ruff.txt`)
- `mypy`: pass (`evidence/mypy.txt`)
