# Testing and Validation Results

## tests added
- `tests/test_remediation_expansion_findings.py`
  - persistence across reload for scorecard history
  - persistence across reload for evidence pack store
- new negative-path coverage in existing suites:
  - `tests/test_stage03_probe_suite.py`
  - `tests/test_stage03_chaos_framework.py`
  - `tests/test_stage03_self_healing.py`
  - `tests/test_stage04_release_promotion_and_history.py`
  - `tests/test_stage03_resilience_scorecards.py`
  - `tests/test_stage03_incident_evidence_packs.py`
  - `tests/test_connectors.py`
  - `tests/test_config.py`

## tests updated
- stage-03/04 contexts updated to use canonical target metadata (`environment`, `safety_tier`, `allow_active_validation`).

## negative-path coverage added
- denied active probe on non-explicitly-eligible target
- denied lab chaos on non-explicitly-eligible target
- denied self-healing risk policy on non-explicitly-eligible target
- denied release promotion when member environment mismatches requested environment
- export redaction check for leaked token/authorization markers
- connector retry paths for AMI/ARI/ESL transient failures

## remaining blind spots
- no inter-process contention tests for JSON persistence backend
- no CI gate yet that fails release profile on MCP stdio skip

## validation summary
- Focused remediation tests: passed
- Full suite: passed (`pytest -q -ra`)
- Current run skip notes:
  - `tests/test_mcp_stdio_initialize.py` skipped twice because `mcp` package is not installed in current runtime
