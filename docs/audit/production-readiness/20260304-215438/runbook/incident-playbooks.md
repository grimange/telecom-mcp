# Incident Playbooks

## Endpoint Unreachable
1. Run `asterisk.pjsip_show_endpoint` for the affected endpoint.
2. Run `asterisk.pjsip_show_endpoints` with a filter to detect blast radius.
3. Capture `telecom.capture_snapshot` and escalate with `correlation_id`.

## Trunk Down / Registration Rejected
1. Run `telecom.summary` for registration and trunk counters.
2. For FreeSWITCH targets, run `freeswitch.sofia_status`.
3. Capture a snapshot and compare with previous incident evidence.

## Connector Timeout / Disconnect Storm
1. Run `asterisk.health` or `freeswitch.health` repeatedly with correlation IDs.
2. Inspect audit logs for timeout/error bursts and target concentration.
3. Validate network path, credentials env vars, and connector timeout settings.

## Calls Stuck / Channel Leak Symptoms
1. Run `asterisk.active_channels` or `freeswitch.channels`.
2. Identify long-lived channels and repeated caller/callee patterns.
3. Capture `telecom.capture_snapshot` to preserve active state for postmortem.
