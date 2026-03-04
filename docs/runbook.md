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
