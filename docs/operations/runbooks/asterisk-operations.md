# Asterisk Operations Runbook

## Purpose
Operate and troubleshoot Asterisk targets with deterministic read-first diagnostics and gated safe actions.

## Symptoms
- SIP endpoint unavailable or unreachable
- Registration/contact visibility degradation
- High call failure or stalled channels
- Bridge growth or leak indicators
- ARI event or AMI observability stall

## Detection
- `asterisk.health`
- `asterisk.pjsip_show_endpoints`
- `asterisk.pjsip_show_contacts`
- `asterisk.active_channels`
- `asterisk.bridges`
- `telecom.summary`

## Initial Checks
1. Run `telecom.summary` for baseline posture.
2. Confirm plane health with `asterisk.health`.
3. Check endpoint/contact state for impacted users.
4. Inspect channels and bridges for stuck resources.
5. Capture snapshot before remediation.

## Step-by-Step Troubleshooting
1. Endpoint and registration triage:
- Run `asterisk.pjsip_show_endpoint` for impacted endpoint.
- Run `asterisk.pjsip_show_endpoints` to assess blast radius.
- Run `asterisk.pjsip_show_contacts` for contact churn.
2. Call-path triage:
- Run `asterisk.active_channels` and inspect long-running channels.
- Run `asterisk.channel_details` or `asterisk.core_show_channel` for specific channel evidence.
3. Bridge triage:
- Run `asterisk.bridges` and correlate with active channels.
- Use `telecom.run_playbook(name="orphan_channel_triage")` for structured classification.
4. Observability triage:
- Run `telecom.run_smoke_suite(name="call_state_visibility_smoke")`.
- Run `telecom.logs` / `asterisk.logs` for recent warning/error lines.

## Safe Remediation
- Allowed with change control and `execute_safe` mode:
- `asterisk.reload_pjsip`
- Use only after evidence capture and after verifying impact scope.
- Example:
```json
{"tool":"asterisk.reload_pjsip","args":{"pbx_id":"pbx-1","reason":"recover SIP registration path","change_ticket":"CHG-1234"}}
```

## Rollback
1. Re-run `asterisk.pjsip_show_endpoints` and `asterisk.active_channels` immediately after remediation.
2. Run `telecom.run_smoke_suite(name="baseline_read_only_smoke")`.
3. If error rate worsens, stop further write actions and switch traffic to standby target per escalation matrix.
4. Attach `telecom.capture_snapshot` before/after to incident record.

## Escalation
- PBX admin: persistent endpoint or module issues.
- Network/SBC team: transport failures, NAT/contact instability.
- Carrier/provider: upstream trunk delivery anomalies.
- Infrastructure team: host-level health degradation.

## Common Asterisk Scenarios
- SIP registration issues
- Endpoint unavailable
- Call failure
- Bridge leak
- ARI event stall
- AMI event backlog
