# Input Audit Selection

## Selected audit set
- Selected timestamp: `20260306T143958Z`
- Source folder: `docs/audit/production-readiness-expanded-capabilities/`
- Files consumed:
  - `20260306T143958Z--production-readiness-summary.md`
  - `20260306T143958Z--capability-surface-inventory.md`
  - `20260306T143958Z--security-and-hardening-audit.md`
  - `20260306T143958Z--runtime-safety-and-gating-audit.md`
  - `20260306T143958Z--operability-and-observability-audit.md`
  - `20260306T143958Z--testing-and-evidence-audit.md`
  - `20260306T143958Z--release-readiness-scorecard.md`
  - `20260306T143958Z--remediation-batches.md`
  - `20260306T143958Z--final-production-readiness-report.md`

## Normalized findings list
- `F-SEC-001` (critical, blocker): probe wrappers can return success while delegated write is denied.
- `F-RT-001` (critical, blocker): runtime signal integrity issue for delegated probe wrappers.
- `G-TEST-001` (high, blocker): no full server-dispatch test coverage for wrapper delegated-write behavior.
- `F-SEC-002` (high): authenticated caller control not mandatory by default.
- `F-SEC-003` (high): hardened target metadata policy not mandatory by default.
- `F-SEC-004` (high): strict critical-state persistence not mandatory by default.
- `F-SEC-005` (medium): redaction edge-case coverage needs expansion.
- `G-TEST-002` (medium): mocked-path test reliance in some active flows.

## Dependencies
- `F-SEC-001` + `F-RT-001` + `G-TEST-001` must be resolved before pilot rollout.
- `F-SEC-002/003/004` depend on a startup profile that enforces hardening controls.
- `F-SEC-005` and `G-TEST-002` can follow after A/B closure.

## Deferred findings
- Deferred to Batch C:
  - `F-SEC-005`
  - `G-TEST-002`
- Deferred by policy rationale: redaction pattern expansion and additional integration-style conversions are valuable but not required to close current critical blockers.

## Remediation assumptions
- Scope is hardening/remediation only, no unrelated capability expansion.
- Existing envelope/error contracts and tool names remain stable.
- Fail-closed behavior is preferred for active/delegated execution paths.
