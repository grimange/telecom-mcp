# Incident Playbooks

## Endpoint unreachable
1. Run `asterisk.pjsip_show_endpoint` for a failing endpoint.
2. Run `asterisk.pjsip_show_endpoints` to detect blast radius.
3. Capture evidence using `telecom.capture_snapshot` and escalate with `correlation_id`.

## Trunk down / registration rejected
1. Run `telecom.summary` and inspect `trunks` + `registrations` counters.
2. For FreeSWITCH run `freeswitch.sofia_status`; for Asterisk run `asterisk.pjsip_show_registration`.
3. Capture snapshot and attach envelope + audit log rows.

## Connector timeouts / disconnect storms
1. Run `asterisk.health` or `freeswitch.health` repeatedly with unique `correlation_id` values.
2. Check audit log for repeated `TIMEOUT` / `CONNECTION_FAILED` codes.
3. Validate connector timeout and retry bounds in config before escalation.

## Calls stuck / channel leak symptoms
1. Run `asterisk.active_channels` or `freeswitch.channels`.
2. Compare duration/state distributions and bridge/call counts.
3. Capture `telecom.capture_snapshot` and include active channel samples.
