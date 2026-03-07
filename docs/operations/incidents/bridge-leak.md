# Incident Playbook: Bridge Leak

## Symptoms
- Bridge count grows without corresponding active call demand.
- Old bridge records persist after calls end.

## Detection Signals
- `asterisk.bridges` shows sustained growth.
- `telecom.run_playbook(name="orphan_channel_triage")` returns orphan/leak buckets.

## Impact
- Resource exhaustion risk and degraded call handling.

## Diagnostic Commands
```json
{"tool":"asterisk.bridges","args":{"pbx_id":"pbx-1","limit":500}}
```
```json
{"tool":"asterisk.active_channels","args":{"pbx_id":"pbx-1","limit":500}}
```
```json
{"tool":"telecom.run_playbook","args":{"name":"orphan_channel_triage","pbx_id":"pbx-1"}}
```

## Recovery Actions
- Confirm leak pattern across repeated samples.
- Apply safe SIP/profile refresh only if leak correlates with signaling instability and change control is approved.

## Safe Fallback Actions
- Reduce intake on affected queues.
- Shift load to alternate PBX while preserving evidence.

## Escalation
- PBX engineering, platform reliability owner, infrastructure team.
