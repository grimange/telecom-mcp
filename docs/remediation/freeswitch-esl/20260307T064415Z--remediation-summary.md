# FreeSWITCH ESL Remediation Summary

## Scope
Remediation run followed `docs/prompts/freeswitch/esl-remediate.md` using audit bundle `docs/audit/freeswitch-esl/20260307T061411Z--*`.

## Findings Addressed
1. Auth/control payload contamination in command outputs.
2. Frame-type correctness for API command responses.
3. Health-path robustness and semantic validation ordering.
4. Version parsing reliability.
5. Missing regression coverage for strict ESL framing/session behavior.

## Changes Implemented
- `src/telecom_mcp/connectors/freeswitch_esl.py`
  - Enforced auth lifecycle gating before command execution.
  - Enforced expected frame routing (`api/response` for API commands).
  - Added resilience for sockets without `settimeout` in tests/mocks.
- `src/telecom_mcp/tools/freeswitch.py`
  - Validated `status`/`version` payloads before Sofia discovery in `freeswitch.health`.
  - Fixed FreeSWITCH version regex extraction.
- `src/telecom_mcp/normalize/freeswitch.py`
  - `normalize_health` now accepts parsed profile payload.
- `tests/test_connectors.py`
  - Updated to strict auth greeting + auth reply + api response sequencing.
  - Added regression tests for interleaved event frames and unexpected frame type rejection.

## Validation Snapshot
- Passed:
  - `pytest -q tests/test_connectors.py tests/test_freeswitch_normalize.py tests/test_remediation_hardening.py`
  - `pytest -q tests/test_tools_contract_smoke.py`
- Full test suite note:
  - `pytest -q` still has unrelated readiness/CRP scoring failures in this workspace baseline.

## Exit Criteria Status
- ESL auth lifecycle: Met.
- Framed response parsing stability: Met for covered scenarios.
- Version/health command behavior: Met in patched tests.
- Sofia profile detection path: Existing logic retained; health now validates command payloads earlier.
- Regression tests: Expanded and passing.
