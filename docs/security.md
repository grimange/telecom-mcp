# Security

## Core rules

- Secrets are loaded from environment variables.
- Secrets are never logged or returned in tool output.
- Default operating mode is `inspect`.
- Write operations are disabled unless explicitly implemented and gated.

## Redaction

Sensitive key patterns are redacted in audit logs:

- `password`, `token`, `secret`, `authorization`

Incident evidence export applies the same redaction policy at export time and bounds exported evidence volume.

## Modes

- `inspect`: read tools only
- `plan`: read + recommendation workflows
- `execute_safe`: allowlisted safe write tools only
- `execute_full`: maintenance-only mode

Active-flow eligibility (required for class C probes, lab chaos, and risk-class B/C self-healing):

- target `environment` must be `lab`
- target `safety_tier` must be `lab_safe`
- target `allow_active_validation` must be `true`

Direct active probe wrappers (`telecom.run_registration_probe`, `telecom.run_trunk_probe`) and platform originate tools (`asterisk.originate_probe`, `freeswitch.originate_probe`) enforce this eligibility fail-closed.

## Runtime persistence behavior

- State persistence is best-effort for runtime continuity.
- Persistence failures are non-fatal but emitted as warnings in tool output so operators can detect drift between in-memory and persisted state.
