# Remediation Plan

## Batch A (production blockers)
- Finding: `F-SEC-001` / `F-RT-001`
  - Source artifact: `20260306T143958Z--security-and-hardening-audit.md`, `20260306T143958Z--runtime-safety-and-gating-audit.md`
  - Impacted subsystem: probe wrappers and delegated execution path
  - Files/modules: `src/telecom_mcp/tools/telecom.py`
  - Approach: make wrappers fail closed when delegated originate fails; include delegated failure details and propagate error
  - Risk: medium (changes active wrapper behavior from permissive to strict)
  - Required tests: wrapper denial propagation tests and success path validation
  - Acceptance criteria: wrapper success implies delegated action executed successfully
  - Rollback: revert wrapper fail-closed checks
- Finding: `G-TEST-001`
  - Source artifact: `20260306T143958Z--testing-and-evidence-audit.md`
  - Impacted subsystem: server dispatch integration testing
  - Files/modules: `tests/test_tools_contract_smoke.py`, `tests/test_expansion_batch4_tools.py`
  - Approach: add tests that run wrapper tools through full dispatch with allowlist/intent/confirm-token chain
  - Risk: low
  - Required tests: delegated deny and delegated success integration tests
  - Acceptance criteria: old false-success path is test-detectable and now fails
  - Rollback: remove added tests

## Batch B (hardening before pilot)
- Finding: `F-SEC-002` / `F-SEC-003` / `F-SEC-004`
  - Source artifact: `20260306T143958Z--security-and-hardening-audit.md`, `20260306T143958Z--remediation-batches.md`
  - Impacted subsystem: startup policy/hardening profile
  - Files/modules: `src/telecom_mcp/config.py`, `tests/test_config.py`, `README.md`, `docs/security.md`, `docs/runbook.md`
  - Approach: add `TELECOM_MCP_RUNTIME_PROFILE=production` bootstrap validator requiring caller auth, target-policy enforcement, strict persistence, and configured auth token
  - Risk: low-medium (intentional startup failures for misconfigured production profile)
  - Required tests: profile denial when controls missing; startup success when controls present
  - Acceptance criteria: production-profile bootstrap fails when mandatory hardening controls are absent
  - Rollback: unset `TELECOM_MCP_RUNTIME_PROFILE` or revert profile check

## Batch C (deferred)
- `F-SEC-005`, `G-TEST-002`
  - Deferred to follow-up expansion of redaction edge cases and deeper integration conversion of mocked paths.
