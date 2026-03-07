# Runbook

## Audit Runtime Parity

Use one interpreter for MCP runtime and tests so transport checks are not skipped due to missing dependencies.

1. Create/update environment: `.venv/bin/python -m pip install -e ".[dev]"`
2. Run tests from the same interpreter: `.venv/bin/python -m pytest -q -ra`
3. If `tests/test_mcp_stdio_initialize.py` is skipped for missing `mcp`, the active test interpreter is not aligned with project dependencies.

## Mode x Environment Safety Matrix

1. `inspect`/`plan`: read-only workflows only.
2. `execute_safe`/`execute_full`: write allowlist still required.
3. Active validation (class C probes), lab chaos mode, and risk-class B/C self-healing require target metadata:
   - `environment: lab`
   - `safety_tier: lab_safe`
   - `allow_active_validation: true`
4. Direct active probe wrappers and platform originate tools are fail-closed on non-lab-safe targets; check denial details (`required` vs `actual`) in error output.
5. Runtime persistence is best-effort; if state writes fail, tool responses include warnings like `State persistence warning for ...`.
6. Environment rollups/promotion decisions require every member target to match `environment_id`.
7. For hardened deployments, enable:
   - authenticated caller policy (default on outside lab/test; override only with explicit risk acceptance)
   - `TELECOM_MCP_AUTH_TOKEN` and optional `TELECOM_MCP_ALLOWED_CALLERS`
   - `TELECOM_MCP_STRICT_STATE_PERSISTENCE=1`
   - `TELECOM_MCP_ENFORCE_TARGET_POLICY=1`
   - explicit capability-class policy via `TELECOM_MCP_ALLOWED_CAPABILITY_CLASSES`
   - if capability classes include `chaos` or `remediation`, also set `TELECOM_MCP_ENABLE_HIGH_RISK_CAPABILITY_CLASSES=1`
8. Without explicit class policy, non-lab profiles allow only `observability` capability class.
9. Set `TELECOM_MCP_RUNTIME_PROFILE=production|prod|pilot` to fail startup when hardened controls are not fully enabled.
10. Configure active-operation concurrency in pilot/prod:
   - `TELECOM_MCP_ACTIVE_MAX_GLOBAL`
   - `TELECOM_MCP_ACTIVE_MAX_PER_TARGET`

## Tier 2 Live Validation Window (Asterisk)

Use this checklist when live Tier 2 validation requires controlled call generation (`Local/97888@telecom-mcp-test`) and probe execution.

1. Confirm target metadata in `targets.yaml` for the Asterisk target:
   - `environment: lab`
   - `safety_tier: lab_safe`
   - `allow_active_validation: true`
2. Start runtime in `execute_safe` or `execute_full`.
3. Set capability policy to include validation tooling:
   - `TELECOM_MCP_ALLOWED_CAPABILITY_CLASSES=observability,validation`
4. Allowlist only the intended active tool for the validation window:
   - `--write-allowlist asterisk.originate_probe`
5. Keep write intent fields required on every active call:
   - `reason`
   - `change_ticket`
6. After the run, remove temporary write allowlist entries and return class policy to the baseline profile.

## Internal Contract Failure Triage

Use `failed_sources[*].contract_failure_reason` for delegated orchestration failures.

| `contract_failure_reason` | Typical meaning | First response action |
|---|---|---|
| `missing_required_fields` | Delegated tool call missed required args | Verify caller propagated required fields (`reason`, `change_ticket`, etc.). |
| `invalid_delegated_arguments` | Delegated args are present but invalid | Check delegated argument schema and value ranges/patterns. |
| `delegated_not_allowlisted` | Delegated write tool blocked by allowlist | Update runtime `write_allowlist` only if approved for environment and window. |
| `delegated_cooldown_active` | Delegated tool currently under cooldown | Wait for cooldown expiry or investigate repeated-trigger loops. |
| `delegated_mode_denied` | Delegated call denied by mode gate | Confirm runtime mode (`execute_safe`/`execute_full`) and intended workflow. |
| `delegated_policy_denied` | Delegated call denied by policy/env/eligibility | Inspect denial details (`required` vs `actual`) and target metadata posture. |
| `delegated_unsupported_operation` | Delegated tool unavailable or unsupported | Verify platform compatibility and tool registry/class-policy coverage. |
| `delegated_timeout` | Delegated call exceeded timeout budget | Check connector health/reachability and timeout settings. |
| `delegated_<ERROR_CODE>` | Other mapped delegated error code | Triage by mapped error code and associated `details`. |
| `unknown_contract_error` | Missing/unknown delegated failure classification | Escalate with correlation ID and raw error payload for taxonomy extension. |

## Active Concurrency Triage

When a tool returns `NOT_ALLOWED` with message `Active operation concurrency limit reached`:

1. Confirm active workload pressure for the same PBX and globally.
2. Validate expected window activity (probe/chaos/self-healing operations).
3. Adjust `TELECOM_MCP_ACTIVE_MAX_GLOBAL` / `TELECOM_MCP_ACTIVE_MAX_PER_TARGET` only via approved change control.
4. Re-run active validations after current active operations drain.

## Endpoint unreachable

1. Run `asterisk.pjsip_show_endpoint` for endpoint state and contacts.
2. Run `asterisk.pjsip_show_endpoints` with filter for broader impact.
3. Capture evidence using `telecom.capture_snapshot`.

## Registration flapping

1. Check `telecom.summary` registrations/trunks.
2. Use `freeswitch.sofia_status` or Asterisk endpoint tooling.
3. Capture snapshot and compare over time.

## Trunk down

1. Run `telecom.summary` for trunk counters.
2. For FreeSWITCH, inspect `freeswitch.sofia_status`.
3. Capture snapshot and escalate with `correlation_id`.

## Calls stuck

1. Run `asterisk.active_channels` or `freeswitch.channels`.
2. Compare durations and state patterns.
3. Attach `telecom.capture_snapshot` output to incident.

## Asterisk logs path drift (`OB-002`)

1. Run `telecom.healthcheck` and confirm `effective_targets_file`; if it is non-canonical, update that runtime file first.
2. Run `asterisk.logs` for the target and inspect `error.details.path` when `NOT_FOUND` is returned.
3. Align `targets.yaml -> targets[*].logs.path` to the real Asterisk log file on that host, then re-run `asterisk.logs` and `telecom.logs`.
4. Keep this as a target-ops configuration action; do not remediate by broadening read scope in code.

## Fixture capture (lab only)

Use this workflow to capture real PBX responses and convert them into sanitized CI fixtures.

Prerequisites:

1. Targets must have `environment: lab` in `targets.yaml`.
2. `FIXTURE_CAPTURE=true` must be set.
3. Required secret env vars for selected targets must be present.

Run:

1. `FIXTURE_CAPTURE=true python scripts/capture_fixtures.py --targets-file targets.yaml`
2. Optional single target: `--pbx-id pbx-1`
3. Optional endpoint for `PJSIPShowEndpoint`: `--endpoint 1001`

Phases executed:

1. F0 readiness: validates lab-only targets, capture flag, redaction rules.
2. F1 raw capture: AMI/ARI/ESL responses stored under `raw/`.
3. F2 sanitization: credentials, IPs, phone-like values, SIP identities redacted to aliases.
4. F3 normalization: versioned `*_v1.json` and `*_v1.yaml` fixtures generated.
5. F4 test generation: replay smoke tests emitted under `tests/`.
6. F5/F6 validation: replay schema checks and fixture version checks.

Artifacts:

1. `docs/fixtures/YYYYMMDD-HHMMSS/raw/`
2. `docs/fixtures/YYYYMMDD-HHMMSS/sanitized/`
3. `docs/fixtures/YYYYMMDD-HHMMSS/tests/`
4. `docs/fixtures/YYYYMMDD-HHMMSS/report.md`
