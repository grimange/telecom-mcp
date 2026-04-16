# Root Cause Inputs

Run timestamp (UTC): `20260306T161805Z`
Input sources:
- `docs/audit/progress-vs-circular-hardening/20260306T160914Z--normalized-findings-ledger.md`
- `docs/audit/progress-vs-circular-hardening/20260306T160914Z--repeated-findings-analysis.md`
- `docs/audit/progress-vs-circular-hardening/20260306T160914Z--closure-quality-analysis.md`
- `docs/audit/progress-vs-circular-hardening/20260306T160914Z--circularity-vs-progress-assessment.md`
- `docs/audit/progress-vs-circular-hardening/20260306T160914Z--recommended-next-actions.md`
- latest expanded-capability audits/remediations (`20260306T155037Z` / `20260306T154819Z`)

## Recurring classes selected
- `RC-A` fragmented active gating/eligibility checks across telecom + vendor tools.
- `RC-B` recurring default-open and inconsistent active execution controls (especially concurrency).
- `RC-C` weak shared test contracts allowing divergence across probe/chaos/self-healing/vendor active paths.

## Recurrence evidence
- `RC-A` appears as `PRX-RUN-001`, `PRR-SEC-001`, `F-SEC-001`, `RB-001`, `SH-CRIT-001` across 5+ audit generations; impacts telecom wrappers + vendor originate tools + active frameworks.
- `RC-B` appears as `PRX-004` (concurrency), plus repeated policy-control recurrence classes in latest audit (`PRX-001/002/003`) where hardening remains profile-dependent.
- `RC-C` appears as `PRR-VER-001`, `G-TEST-001`, `G-TEST-002`, `TV-MED-001`, `PRX-008` with repeated remediation follow-ups.
- Meta-audit classified overall state: `Partial Progress with Structural Recurrence`.

## Leverage ranking
1. Shared safety policy abstraction (highest leverage): eliminates duplicated target-eligibility and destination-validation logic in telecom/asterisk/freeswitch.
2. Shared active-operation concurrency control: prevents ad-hoc per-subsystem concurrency behavior and closes repeated active-control gaps.
3. Shared recurrence tests for safety/control-plane contracts: blocks reintroduction during future expansion.

## Assumptions about structural causes
- Historical fixes were mostly local-path patches; cross-subsystem policy contracts were not centralized enough.
- Active systems (probe/chaos/self-healing/vendor originate) share the same risk envelope but lacked one execution-control boundary.
- Test suites were broad, but not all recurrence classes had shared contract tests tied to control-plane modules.

## Out-of-scope root causes
- Distributed multi-process/global lock coordination beyond process-local guardrails.
- External metrics sink + long-term observability platform integration.
- Net-new telecom capability expansion.
