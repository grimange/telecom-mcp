# Incident Playbooks

## Endpoint Unreachable
1. Run `asterisk.pjsip_show_endpoint` for endpoint state.
2. Run `asterisk.pjsip_show_endpoints` to identify scope.
3. Capture `telecom.capture_snapshot` and escalate with `correlation_id`.

## Trunk Down / Registration Rejected
1. Run `telecom.summary` for trunk/registration counters.
2. Run `asterisk.pjsip_show_registration` or `freeswitch.gateway_status`.
3. Capture snapshot and compare against previous incidents.

## Connector Timeout / Disconnect Storm
1. Run `asterisk.health` / `freeswitch.health` repeatedly and track correlation IDs.
2. Review audit logs for timeout/error bursts by `pbx_id`.
3. Validate target reachability and secret env vars.

## Calls Stuck / Channel Leak Symptoms
1. Run `asterisk.active_channels` / `freeswitch.channels` and `freeswitch.calls`.
2. Inspect `asterisk.channel_details` for suspicious long-lived channels.
3. Capture `telecom.capture_snapshot` for postmortem evidence.
