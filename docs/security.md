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
Active smoke/probe orchestration that triggers delegated originate paths also requires explicit write intent (`reason`, `change_ticket`), and write-capable self-healing policies require explicit `change_ticket`.
Direct platform originate tools enforce strict destination allow-pattern validation and reject unsupported characters fail-closed.
Eligibility and destination validation are centralized in `src/telecom_mcp/safety/policy.py` to reduce subsystem drift.
Capability classes are enforced as dispatch metadata (`observability`, `validation`, `chaos`, `remediation`, `export`) and can be constrained with `TELECOM_MCP_ALLOWED_CAPABILITY_CLASSES`.
If `TELECOM_MCP_ALLOWED_CAPABILITY_CLASSES` is unset, non-lab profiles fail closed to `observability` only.
Internal delegated-call denials/validation mismatches are classified with contract-failure reason codes and exposed on `failed_sources[*].contract_failure_reason` for triage.

## Active concurrency controls

- Shared active-operation concurrency guards are enforced for active probe wrappers, class C probe runs, lab chaos execution, self-healing remediation policies, and direct vendor originate tools.
- Limits are controlled by:
  - `TELECOM_MCP_ACTIVE_MAX_GLOBAL` (default `4`)
  - `TELECOM_MCP_ACTIVE_MAX_PER_TARGET` (default `2`)
- Limit exhaustion fails closed with `NOT_ALLOWED` and returns active/limit details in error `details`.

## Caller identity boundary

- Caller authentication is required by default outside explicit lab/test profiles.
- Use `TELECOM_MCP_REQUIRE_AUTHENTICATED_CALLER=0` only for controlled lab/testing workflows.
- Use shared token auth with `TELECOM_MCP_AUTH_TOKEN` and pass request `auth.token`.
- Optional caller allowlist: `TELECOM_MCP_ALLOWED_CALLERS=caller-a,caller-b`.
- Audit records include `principal`, `principal_authenticated`, and `auth_scheme`.

## Production profile

- Set `TELECOM_MCP_RUNTIME_PROFILE=production` for strict startup validation.
- In hardened profiles (`production`, `prod`, `pilot`), startup fails unless:
  - `TELECOM_MCP_REQUIRE_AUTHENTICATED_CALLER=1`
  - `TELECOM_MCP_ENFORCE_TARGET_POLICY=1`
  - `TELECOM_MCP_STRICT_STATE_PERSISTENCE=1`
  - `TELECOM_MCP_ALLOWED_CAPABILITY_CLASSES` is explicitly set and includes `observability`
  - `TELECOM_MCP_AUTH_TOKEN` is non-empty
- If `TELECOM_MCP_ALLOWED_CAPABILITY_CLASSES` includes `chaos` or `remediation` in a hardened profile, startup also requires:
  - `TELECOM_MCP_ENABLE_HIGH_RISK_CAPABILITY_CLASSES=1`

Operator triage for delegated orchestration reasons is documented in `docs/runbook.md` (`Internal Contract Failure Triage`).

## Runtime persistence behavior

- State persistence is best-effort for runtime continuity.
- Persistence failures are non-fatal but emitted as warnings in tool output so operators can detect drift between in-memory and persisted state.
- Set `TELECOM_MCP_STRICT_STATE_PERSISTENCE=1` to fail closed when critical governance state artifacts cannot be persisted/read.
- Set `TELECOM_MCP_ENFORCE_TARGET_POLICY=1` to reject ambiguous/unsafe target metadata at startup.
