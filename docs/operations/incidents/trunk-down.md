# Incident Playbook: Trunk Down

## Symptoms
- Outbound/inbound carrier calls fail.
- Gateway status reports down/unreachable.

## Detection Signals
- `telecom.summary` trunk counters degraded.
- `freeswitch.gateway_status` or provider-facing registration checks fail.

## Impact
- External call connectivity is partially or fully unavailable.

## Diagnostic Commands
```json
{"tool":"telecom.summary","args":{"pbx_id":"fs-1"}}
```
```json
{"tool":"freeswitch.sofia_status","args":{"pbx_id":"fs-1"}}
```
```json
{"tool":"freeswitch.gateway_status","args":{"pbx_id":"fs-1","gateway":"carrier-a"}}
```

## Recovery Actions
- Run `freeswitch.sofia_profile_rescan` for affected profile (mode-gated).
- Run controlled `telecom.run_trunk_probe` only in eligible environments.

## Safe Fallback Actions
- Failover route to standby carrier trunk.
- Apply temporary outbound policy to preserve emergency traffic.

## Escalation
- Carrier/provider NOC, network team, PBX platform team.
