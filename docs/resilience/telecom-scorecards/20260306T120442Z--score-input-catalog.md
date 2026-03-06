# Score Input Catalog

## Mandatory Inputs (implemented)
- audit posture: `telecom.audit_target`
- runtime smoke health: `telecom.run_smoke_suite` (baseline/registration/call-state/audit)
- troubleshooting readiness: `telecom.run_playbook` (outbound triage signal)
- validation signal: `telecom.verify_cleanup`

## Optional/Advisory Inputs (deferred integration)
- chaos execution evidence
- incident burden and recurrence feeds
- active probe pass-rate history

## Normalized vs Vendor-Specific
- normalized: audit score/violations, smoke counts, playbook status, cleanup signal
- vendor-specific details stay in nested evidence fields consumed by upstream tools

## Dependency Mapping
- scorecard engine consumes outputs from audit, smoke, playbook, and validation tools
- PBX scorecards feed cluster/environment rollups and comparison/trend outputs
