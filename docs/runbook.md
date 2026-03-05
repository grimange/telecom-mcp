# Runbook

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
