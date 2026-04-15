# Incident Playbook: SIP Registration Failure

## Symptoms
- Endpoints unreachable/unavailable.
- Registrations missing or sharply reduced.

## Detection Signals
- `telecom.summary` shows registration drop.
- `asterisk.pjsip_show_endpoints` or `freeswitch.registrations` shows missing contacts/entries.

## Impact
- Agents cannot receive or place SIP-based calls reliably.

## Diagnostic Commands
```json
{"tool":"telecom.summary","args":{"pbx_id":"pbx-1"}}
```
```json
{"tool":"asterisk.pjsip_show_endpoints","args":{"pbx_id":"pbx-1","limit":200}}
```
```json
{"tool":"freeswitch.registrations","args":{"pbx_id":"fs-1","limit":200}}
```

## Recovery Actions
- Asterisk: `asterisk.reload_pjsip` (mode-gated, ticket required).
- FreeSWITCH: `freeswitch.sofia_profile_rescan` or `freeswitch.reloadxml` (mode-gated).

## Safe Fallback Actions
- Route impacted queues to backup PBX.
- Disable non-critical SIP workloads to reduce churn.

## Escalation
- PBX admin, SBC/network team, carrier/provider if registration dependency is external.
