# On-Call Incident Handling Guide

## Incident Priorities
- P1: service down.
- P2: severe degradation.
- P3: partial failure with workaround.
- P4: investigation or low-impact anomaly.

## Incident Flow
1. Alert received.
2. Confirm issue and classify priority.
3. Run diagnostics using runbook sequence.
4. Attempt safe remediation if approved.
5. Escalate if unresolved or high-risk.
6. Record evidence, timeline, and decisions.

## MTTR Guidelines
- P1 response: under 5 minutes.
- P1 mitigation target: under 30 minutes.
- P2 mitigation target: under 60 minutes.

## Standard Diagnostic Set
```json
{"tool":"telecom.summary","args":{"pbx_id":"pbx-1"}}
```
```json
{"tool":"telecom.capture_snapshot","args":{"pbx_id":"pbx-1"}}
```
```json
{"tool":"telecom.run_smoke_suite","args":{"name":"baseline_read_only_smoke","pbx_id":"pbx-1"}}
```

## Safe Remediation Rules
- Only in `execute_safe` or higher.
- Only allowlisted tools with explicit `reason` and `change_ticket`.
- One change at a time, verify, then continue.

## Post-Incident Closeout
- Confirm service restoration with smoke suite and targeted checks.
- Export evidence pack if incident severity requires audit trail.
- Update handover notes with unresolved risks and next actions.
