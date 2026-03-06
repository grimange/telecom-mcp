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
   - `TELECOM_MCP_REQUIRE_AUTHENTICATED_CALLER=1`
   - `TELECOM_MCP_AUTH_TOKEN` and optional `TELECOM_MCP_ALLOWED_CALLERS`
   - `TELECOM_MCP_STRICT_STATE_PERSISTENCE=1`
   - `TELECOM_MCP_ENFORCE_TARGET_POLICY=1`
8. Set `TELECOM_MCP_RUNTIME_PROFILE=production` to fail startup when hardened controls are not fully enabled.

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
