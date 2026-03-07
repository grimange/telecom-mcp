# Shift Handover Guide

## Active Incidents
- Incident ID and severity.
- Affected `pbx_id` and customer impact.
- Current status: investigating, mitigating, monitoring.

## Recent Alerts
- Top alerts from the last 8-12 hours.
- Repeating alerts and suppression decisions.

## Ongoing Remediation
- Actions already attempted and outcomes.
- Any mode-gated actions executed with `change_ticket`.
- Next approved remediation step.

## System Health Summary
- Latest `telecom.summary` posture per active PBX.
- Snapshot IDs and correlation IDs collected.
- Smoke/playbook results that define current confidence.

## Known Risks
- Open escalations and owners.
- Deferred remediations awaiting maintenance window.
- Observability gaps or degraded data sources.

## Handover Checklist
1. Confirm incident timeline is up to date.
2. Confirm evidence links and snapshots are attached.
3. Confirm escalation contacts and paging status.
4. Confirm next checkpoint time and owner.
