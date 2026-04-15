# Remediation Plan

## Batch A (production blockers)
- Finding: `PRR-SEC-001` / `PRR-RUN-001`
  - Source artifact: security/runtime audits (`20260306T140403Z`)
  - Subsystem: `src/telecom_mcp/tools/telecom.py`
  - Files/modules: direct wrappers `run_registration_probe`, `run_trunk_probe`
  - Approach: enforce lab-safe eligibility (`environment=lab`, `safety_tier=lab_safe`, `allow_active_validation=true`) before delegation
  - Risk: low-medium (intentional deny on previously permissive path)
  - Tests: negative-path denial tests for non-lab targets
  - Acceptance: direct wrappers deny non-lab-safe targets with `NOT_ALLOWED`
  - Rollback: revert helper enforcement block
- Finding: `PRR-VER-001`
  - Source artifact: testing-and-evidence audit (`20260306T140403Z`)
  - Subsystem: scorecard policy input tests
  - Files/modules: `tests/test_stage03_scorecard_policy_inputs.py`
  - Approach: remove time-fragile static timestamp assumption in tests and add regression assertions
  - Risk: low (test-only correctness)
  - Tests: full suite, targeted stage-03 scorecard tests
  - Acceptance: `pytest -q` green baseline
  - Rollback: restore prior static test helper if needed

## Batch B (hardening before pilot)
- Finding: `PRR-SEC-002`
  - Source artifact: security audit (`20260306T140403Z`)
  - Subsystem: platform tools
  - Files/modules: `src/telecom_mcp/tools/asterisk.py`, `src/telecom_mcp/tools/freeswitch.py`
  - Approach: enforce local lab-safe eligibility in `originate_probe` tools (defense in depth)
  - Risk: low-medium (intended safety denial for unsafe targets)
  - Tests: platform originate non-lab denial tests
  - Acceptance: both platform originate tools fail closed on non-lab-safe targets
  - Rollback: remove local checks (not recommended)
- Finding: `PRR-SEC-003`
  - Source artifact: security audit (`20260306T140403Z`)
  - Subsystem: scorecard policy mapping
  - Files/modules: `src/telecom_mcp/scorecard_policy_inputs/mapping.py`, `engine.py`
  - Approach: add deterministic mapping revision/schema/checksum fields
  - Risk: low (additive output metadata)
  - Tests: checksum format + field presence tests
  - Acceptance: policy input output includes deterministic mapping provenance
  - Rollback: remove metadata emission
- Finding: `PRR-SEC-005`
  - Source artifact: security/observability/testing audits (`20260306T140403Z`)
  - Subsystem: state persistence
  - Files/modules: `src/telecom_mcp/tools/telecom.py`
  - Approach: keep non-fatal save behavior but record and surface warnings in affected tool outputs
  - Risk: low (observability only)
  - Tests: persistence-failure warning visibility in scorecard output
  - Acceptance: state write failures visible in `warnings`
  - Rollback: restore silent persistence behavior (not recommended)
