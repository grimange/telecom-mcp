# Safety and Gating Model

## Workflow Safety Classes
- Read-only:
  - all mandatory playbooks
  - `baseline_read_only_smoke`
  - `registration_visibility_smoke`
  - `call_state_visibility_smoke`
  - `audit_baseline_smoke`
- Gated-write:
  - `active_validation_smoke`

## Mode Gating Matrix
- `inspect`:
  - allow all read-only playbooks/suites
  - block `active_validation_smoke`
- `plan`:
  - allow read-only diagnostics
  - block active validation
- `execute_safe` / `execute_full`:
  - allow read-only workflows
  - active validation allowed only if active-probe gates are enabled

## Failure Handling
- Every subcall failure is captured under `failed_sources`.
- Workflow still returns structured output when possible.
- Hard validation errors (unknown workflow names, missing required args) return `VALIDATION_ERROR`.
- Gated blocked actions return `NOT_ALLOWED`.

## Partial Execution Rules
- Workflow continues on non-critical read failures.
- Status rolls up to `warning` if any non-fatal checks fail.
- Status rolls up to `failed` when required steps/checks fail.

## Prohibited Behaviors
- No unrestricted shell execution tools are introduced.
- No restart/shutdown/destructive PBX actions in playbooks/smokes.
- Active probes remain explicit opt-in and mode-gated.
