# Incident Playbook: ARI Event Stall

## Symptoms
- ARI-driven automations appear frozen.
- Call state updates lag or stop while PBX remains partially responsive.

## Detection Signals
- `asterisk.health` degrades or shows control-plane issue.
- `telecom.run_smoke_suite(name="call_state_visibility_smoke")` warns/fails.
- Observability degradation indicated by logs and audit drift.

## Impact
- Automation and routing workflows lose state synchronization.

## Diagnostic Commands
```json
{"tool":"asterisk.health","args":{"pbx_id":"pbx-1"}}
```
```json
{"tool":"telecom.run_smoke_suite","args":{"name":"call_state_visibility_smoke","pbx_id":"pbx-1"}}
```
```json
{"tool":"telecom.audit_target","args":{"pbx_id":"pbx-1"}}
```

## Recovery Actions
- Confirm AMI/ARI visibility mismatch and preserve evidence.
- Run safe signaling refresh only if explicitly approved and incident commander agrees.

## Safe Fallback Actions
- Switch automation to degraded/manual handling mode.
- Route critical traffic to stable control-plane target.

## Escalation
- PBX platform team, application owners consuming ARI events, infrastructure team.
