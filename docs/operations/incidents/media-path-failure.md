# Incident Playbook: Media Path Failure

## Symptoms
- One-way audio, no audio, or abrupt media drops.
- Calls establish but media quality or continuity is broken.

## Detection Signals
- Bridge/channel anomalies in `asterisk.bridges`, `telecom.channels`, `freeswitch.calls`.
- `telecom.run_playbook(name="outbound_call_failure_triage")` indicates bridge/media stage issues.

## Impact
- Calls connect but are unusable or degraded.

## Diagnostic Commands
```json
{"tool":"asterisk.bridges","args":{"pbx_id":"pbx-1","limit":200}}
```
```json
{"tool":"telecom.channels","args":{"pbx_id":"pbx-1","limit":200}}
```
```json
{"tool":"freeswitch.calls","args":{"pbx_id":"fs-1","limit":200}}
```

## Recovery Actions
- Validate channel/bridge stabilization first.
- If linked to profile/signaling side, perform gated profile rescan/reload with change ticket.

## Safe Fallback Actions
- Route to known-good media path or backup PBX.
- De-rate non-critical call flows until stability returns.

## Escalation
- Network/media engineering, PBX platform team, infrastructure team.
