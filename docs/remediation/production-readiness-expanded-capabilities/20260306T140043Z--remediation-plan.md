# Remediation Plan

## Batch A — production blockers
- Finding ID: `SEC-01` / `RSG-01`
  - source audit artifact: `20260306T134250Z--security-and-hardening-audit.md`
  - impacted subsystem: incident evidence export
  - files: `src/telecom_mcp/tools/telecom.py`, `tests/test_stage03_incident_evidence_packs.py`
  - remediation approach: add export-time redaction + evidence/timeline bounds + sensitivity labels; remove raw export path
  - risk of change: medium (export payload shape hardening)
  - required tests: export negative-path leakage checks for json/zip
  - acceptance criteria: secret markers redacted, payload bounded, no raw sensitive echo
  - rollback consideration: revert export sanitizer helpers only

- Finding ID: `SEC-02` / `RSG-02`
  - source audit artifact: `20260306T134250Z--runtime-safety-and-gating-audit.md`
  - impacted subsystem: probe/chaos/self-healing gating
  - files: `src/telecom_mcp/config.py`, `src/telecom_mcp/tools/telecom.py`, `tests/test_stage03_probe_suite.py`, `tests/test_stage03_chaos_framework.py`, `tests/test_stage03_self_healing.py`
  - remediation approach: canonicalize explicit eligibility metadata (`environment`, `safety_tier`, `allow_active_validation`); remove permissive tag fallback and untagged bypass semantics
  - risk of change: medium-high (stricter gating)
  - required tests: deny active paths unless explicit lab-safe metadata
  - acceptance criteria: class C/lab/risk-B-C paths fail closed without explicit eligibility
  - rollback consideration: preserve metadata schema if reverting gating messages

## Batch B — hardening before pilot
- Finding ID: `SEC-03`
  - source audit artifact: `20260306T134250Z--security-and-hardening-audit.md`
  - impacted subsystem: environment scorecards and promotion decisions
  - files: `src/telecom_mcp/tools/telecom.py`, `tests/test_stage03_resilience_scorecards.py`, `tests/test_stage04_release_promotion_and_history.py`
  - remediation approach: enforce environment membership checks for explicit and implicit member resolution
  - risk of change: medium (rejects mixed environment inputs)
  - required tests: mismatch failures + environment-filtered default member selection
  - acceptance criteria: mismatched target environments rejected with `VALIDATION_ERROR`
  - rollback consideration: revert only membership guard helper

- Finding ID: `SEC-04`
  - source audit artifact: `20260306T134250Z--security-and-hardening-audit.md`
  - impacted subsystem: AMI/ARI/ESL connector reliability
  - files: `src/telecom_mcp/connectors/asterisk_ami.py`, `src/telecom_mcp/connectors/asterisk_ari.py`, `src/telecom_mcp/connectors/freeswitch_esl.py`, `tests/test_connectors.py`
  - remediation approach: bounded retry/backoff (single retry) for transient connect/request I/O failures
  - risk of change: low-medium
  - required tests: flaky-first-attempt succeeds on retry
  - acceptance criteria: transient faults retried once, permanent faults still map to standard error codes
  - rollback consideration: remove retry loops while keeping error mapping

- Finding ID: `SEC-05`
  - source audit artifact: `20260306T134250Z--security-and-hardening-audit.md`
  - impacted subsystem: governance/evidence durability
  - files: `src/telecom_mcp/tools/telecom.py`, `tests/test_remediation_expansion_findings.py`
  - remediation approach: persist scorecard history, release-gate history, evidence packs to JSON state store
  - risk of change: medium (state lifecycle)
  - required tests: reload module and verify persisted state survives
  - acceptance criteria: state reload restores recorded history/packs
  - rollback consideration: fallback to in-memory only if storage unavailable
