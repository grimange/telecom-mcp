# FreeSWITCH ESL Remediation Summary

## Input Audit Set
- `docs/audit/freeswitch-esl/20260307T072302Z--*`

## Remediation Scope This Run
Focused on unresolved gaps from latest audit:
1. Sofia table parsing completeness.
2. Missing malformed-frame regression coverage.

## Code Changes
- `src/telecom_mcp/normalize/freeswitch.py`
  - Added canonical tabular Sofia row parsing (`profile`, `alias`, `gateway`) and alias-aware gateway-profile association.
- `tests/test_freeswitch_normalize.py`
  - Added regression test for real-style tabular `sofia status` output.
- `tests/test_connectors.py`
  - Added malformed `Content-Length` regression test expecting `UPSTREAM_ERROR`.

## Validation
- Passed:
  - `pytest -q tests/test_freeswitch_normalize.py tests/test_connectors.py tests/test_remediation_hardening.py tests/test_tools_contract_smoke.py`
  - `pytest -q tests/test_expansion_batch1_tools.py::test_version_tools_parse_backend_output`

## Outcome
Repository-level ESL readiness improved for Sofia discovery completeness and parser resilience. Runtime deployment drift remains an operational follow-up.
