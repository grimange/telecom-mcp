# Production Readiness Scorecard

Run folder: `docs/audit/production-readiness/20260304-215438`

## Phase Gates
- PRR-C1 Contract: **FAIL**
  - Missing spec tools in registry (`evidence/contract-tool-diff.json`).
  - Envelope/error-code shape checks pass via tests.
- PRR-Q1 Quality: **PASS (after remediation)**
  - `pytest`, `ruff`, `mypy` pass.
  - `black --check` reports no reformat needed but exits via timeout guard.
- PRR-S1 Security: **FAIL**
  - Secret regex scan passed.
  - Dependency vulnerability report contains unresolved findings.
- PRR-O1 Observability: **PASS**
  - Correlation IDs present in envelopes and audit logs.
  - Sample audit records generated.
- PRR-R1 Reliability: **PASS (limited scope)**
  - Connector failure mapping tests pass.
  - Cancellation/backpressure coverage remains limited.
- PRR-P1 Performance: **PASS (baseline only)**
  - Local dispatch benchmark generated; no prior baseline for regression gate.
- PRR-D1 Deployability: **PARTIAL / FAIL GATE**
  - Entrypoint starts with example config.
  - Missing-config startup UX still traceback-based.

## Weighted Score (Post-Remediation Re-run)
- Contract (25): 15
- Security (20): 10
- Observability (20): 17
- Reliability (20): 16
- Performance (5): 4
- Deployability (10): 6

**Total: 68 / 100**

Target threshold: 90
Result: **Below target**

## Remediation Loop Status
- Initial run detected failing quality gates.
- A remediation batch was executed and Phase 1-8 checks were re-run once.
- Quality gates improved, but overall score remains below threshold due unresolved contract/security/deployability gaps.
