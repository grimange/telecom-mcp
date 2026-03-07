# FreeSWITCH Operations Runbook

## Purpose
Operate and troubleshoot FreeSWITCH targets with read-first diagnostics and tightly gated safe recovery actions.

## Symptoms
- Gateway/trunk down
- Sofia profile or registration failures
- Stuck channels/calls
- Media session degradation

## Detection
- `freeswitch.health`
- `freeswitch.sofia_status`
- `freeswitch.registrations`
- `freeswitch.gateway_status`
- `freeswitch.channels`
- `freeswitch.calls`
- `telecom.summary`

## Initial Checks
1. Run `telecom.summary` for system posture.
2. Run `freeswitch.health`.
3. Check Sofia profiles and gateways with `freeswitch.sofia_status`.
4. Check registrations for endpoint/provider impact.
5. Check channels/calls and capture evidence snapshot.

## Step-by-Step Troubleshooting
1. Registration and profile triage:
- `freeswitch.sofia_status`
- `freeswitch.registrations`
- `telecom.run_playbook(name="sip_registration_triage")`
2. Trunk triage:
- `freeswitch.gateway_status`
- `telecom.run_probe(name="outbound_trunk_probe")` when policy permits.
3. Call/media triage:
- `freeswitch.channels`
- `freeswitch.calls`
- `freeswitch.channel_details` for targeted inspection
4. Observability and consistency triage:
- `telecom.run_smoke_suite(name="call_state_visibility_smoke")`
- `telecom.logs` / `freeswitch.logs`

## Safe Remediation
- Mode-gated, change-controlled options:
- `freeswitch.sofia_profile_rescan`
- `freeswitch.reloadxml`
- Example:
```json
{"tool":"freeswitch.sofia_profile_rescan","args":{"pbx_id":"fs-1","profile":"external","reason":"recover trunk registration","change_ticket":"CHG-1234"}}
```

## Rollback
1. Validate Sofia and registrations with two consecutive checks.
2. Run `telecom.run_smoke_suite(name="registration_visibility_smoke")`.
3. If status worsens, halt further write actions and fail over traffic according to escalation matrix.
4. Preserve pre/post snapshots via `telecom.capture_snapshot`.

## Escalation
- PBX platform team: persistent Sofia/profile faults.
- Carrier/provider: gateway/trunk outages.
- Network team: packet loss, latency, transport anomalies.
- Infrastructure team: host/process availability issues.

## Common FreeSWITCH Scenarios
- Gateway down
- Sofia profile failure
- Call channel stuck
- Media session issue
