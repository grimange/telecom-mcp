# Incident Playbook: High Call Failure Rate

## Symptoms
- Elevated failed-call metrics across multiple routes.
- Increased short-duration channels and failed setup attempts.

## Detection Signals
- `telecom.summary` notes degraded posture.
- `telecom.calls` and `telecom.channels` show failure patterns.
- `telecom.run_playbook(name="outbound_call_failure_triage")` returns failure bucket.

## Impact
- Significant customer-facing call setup failures.

## Diagnostic Commands
```json
{"tool":"telecom.calls","args":{"pbx_id":"pbx-1","limit":200}}
```
```json
{"tool":"telecom.channels","args":{"pbx_id":"pbx-1","limit":200}}
```
```json
{"tool":"telecom.run_playbook","args":{"name":"outbound_call_failure_triage","pbx_id":"pbx-1"}}
```

## Recovery Actions
- Identify whether failure is endpoint, trunk, or media related from playbook bucket.
- Apply only targeted safe remediation for the implicated subsystem.

## Safe Fallback Actions
- Shift low-priority traffic to alternate routes.
- Trigger incident communications and reduce optional workloads.

## Escalation
- PBX admin, carrier/provider, network team, service owner/on-call lead.
