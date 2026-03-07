# Telecom Escalation Matrix

| Issue | Escalate To | Trigger Condition |
|---|---|---|
| SIP registration failure | PBX admin, SBC/network team | Registrations remain degraded after first safe remediation |
| Trunk down | Carrier/provider NOC, network team | Gateway/trunk unavailable for more than 10 minutes |
| High call failure rate | PBX admin, carrier, service owner | Failure rate sustained across multiple routes |
| Media path failure | Network/media engineering, PBX admin | One-way/no-audio widespread or severe |
| Bridge leak / stuck channels | PBX engineering, infrastructure | Resource growth threatens capacity |
| ARI/AMI event stall | PBX platform + app owner | Control-plane lag blocks automation |
| PBX crash/unreachable | Infrastructure, PBX admin, incident commander | Health checks fail and service is unavailable |

## Escalation Policy
- P1 incidents page primary and secondary owners immediately.
- Escalate to incident commander if unresolved after first mitigation attempt.
- Include evidence: `correlation_id`, snapshots, smoke/playbook outcomes, and timeline.
