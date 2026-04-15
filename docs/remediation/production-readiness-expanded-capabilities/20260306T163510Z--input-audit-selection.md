# Input Audit Selection

## selected audit set
- selected timestamp: `20260306T155037Z`
- source root: `docs/audit/production-readiness-expanded-capabilities/`
- consumed artifacts:
  - `20260306T155037Z--production-readiness-summary.md`
  - `20260306T155037Z--capability-surface-inventory.md`
  - `20260306T155037Z--security-and-hardening-audit.md`
  - `20260306T155037Z--runtime-safety-and-gating-audit.md`
  - `20260306T155037Z--operability-and-observability-audit.md`
  - `20260306T155037Z--testing-and-evidence-audit.md`
  - `20260306T155037Z--release-readiness-scorecard.md`
  - `20260306T155037Z--remediation-batches.md`
  - `20260306T155037Z--final-production-readiness-report.md`

## normalized findings list
- `PRX-001`
  - severity: critical
  - subsystem: dispatch capability-class policy
  - production-blocker status: blocker
  - impacts: code + tests + docs
  - required validation: negative-path dispatch tests + full regression
- `PRX-002`
  - severity: critical
  - subsystem: caller/auth boundary
  - production-blocker status: blocker
  - impacts: code + tests + docs
  - required validation: request auth boundary tests + healthcheck policy reporting
- `PRX-003`
  - severity: high
  - subsystem: governance state persistence
  - production-blocker status: no (Batch B)
  - impacts: already remediated; revalidated
  - required validation: strict-persistence tests rerun
- `PRX-004`
  - severity: high
  - subsystem: active-operation concurrency
  - production-blocker status: no (Batch B)
  - impacts: already remediated; revalidated
  - required validation: concurrency saturation tests rerun
- `PRX-005`, `PRX-006`
  - severity: medium
  - subsystem: fixture semantics, at-rest evidence governance
  - production-blocker status: no (Batch C)
  - impacts: docs/process
  - required validation: documented as deferred
- `PRX-007`, `PRX-008`
  - severity: improvement
  - subsystem: external observability, multi-process race testing
  - production-blocker status: no (Batch D)
  - impacts: deferred track
  - required validation: follow-on pipeline

## dependencies
- `PRX-001` and `PRX-002` must be closed before any rollout-class promotion beyond internal pilot.
- `PRX-003` and `PRX-004` remain required before pilot expansion; current run revalidates their controls.
- Docs/runbook updates depend on finalized runtime behavior for auth/class policy defaults.

## deferred findings
- `PRX-005`: deferred (Batch C, operator-facing fixture/live semantics hardening).
- `PRX-006`: deferred (Batch C, at-rest evidence/state governance policy hardening).
- `PRX-007`, `PRX-008`: deferred (Batch D post-pilot improvements).

## remediation assumptions
- Existing Batch B code paths (`strict state persistence`, `shared active concurrency`) are already present and in scope for revalidation, not net-new implementation.
- Safety-first behavior changes are allowed to be breaking when they remove unsafe default-open paths.
