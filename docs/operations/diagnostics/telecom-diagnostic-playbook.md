# Telecom Diagnostic Playbook

## Purpose
Provide a deterministic troubleshooting flow for telecom MCP operators using read-first tools, with gated safe remediation only when needed.

## Safety and Mode Rules
- Default to `inspect` mode and read-only tools.
- Use `execute_safe` only for allowlisted remediation tools.
- Never run destructive PBX actions.
- For active probes and remediation writes, include `reason` and `change_ticket`, and follow lab-safe gating rules.

## Core Workflow
1. Confirm target and severity with `telecom.list_targets` and incident context.
2. Run `telecom.summary` for immediate health posture.
3. Run platform diagnostics:
- Asterisk: `asterisk.health`, `asterisk.pjsip_show_endpoints`, `asterisk.active_channels`, `asterisk.bridges`.
- FreeSWITCH: `freeswitch.health`, `freeswitch.sofia_status`, `freeswitch.registrations`, `freeswitch.channels`, `freeswitch.calls`.
4. Capture bounded evidence with `telecom.capture_snapshot`.
5. If unresolved, run read-only automation:
- `telecom.run_smoke_suite(name="baseline_read_only_smoke", pbx_id=...)`
- `telecom.run_playbook(name=..., pbx_id=...)`
6. If policy allows and incident warrants, attempt safe remediation.
7. Verify outcome and cleanup, then escalate if still degraded.

## Failure Signal Mapping
| Failure Signal | Primary Detection Tools | Secondary Diagnostics | Safe Remediation | Rollback / Safety |
|---|---|---|---|---|
| SIP endpoint unreachable | `asterisk.pjsip_show_endpoint`, `asterisk.pjsip_show_endpoints` | `asterisk.pjsip_show_contacts`, `telecom.logs` | `asterisk.reload_pjsip` (gated) | Verify endpoint status returns to reachable; stop remediation if error rate rises |
| Registrations drop to zero | `telecom.registrations`, `freeswitch.registrations` | `telecom.summary`, `freeswitch.sofia_status` | `freeswitch.sofia_profile_rescan` or `freeswitch.reloadxml` (gated) | Confirm registration recovery in two consecutive checks |
| Trunk outage | `freeswitch.gateway_status`, `telecom.summary` | `freeswitch.sofia_status`, `telecom.logs` | `freeswitch.sofia_profile_rescan` (gated) | Revert to prior profile state or standby route |
| High call failure rate | `telecom.calls`, `telecom.channels`, `telecom.summary` | `telecom.run_playbook(outbound_call_failure_triage)` | No immediate write by default; use safe reload only with change control | Validate with smoke suite before further change |
| Media / bridge instability | `asterisk.bridges`, `telecom.channels`, `freeswitch.calls` | `telecom.run_playbook(orphan_channel_triage)` | Platform-specific safe rescan/reload only with approved ticket | Verify bridge/channel counts normalize |
| ARI event stall / observability degradation | `asterisk.health`, `telecom.run_smoke_suite(call_state_visibility_smoke)` | `telecom.audit_target`, `telecom.logs` | No direct restart command exposed; use escalation path | Switch to fallback PBX and preserve evidence |

## Tool Usage Examples

### `telecom.summary`
- Purpose: one-call health summary for quick triage.
- Example:
```json
{"tool":"telecom.summary","args":{"pbx_id":"pbx-1"}}
```
- Interpretation: check registrations, channel load, trunk counts, and notes for immediate anomalies.

### `asterisk.active_channels`
- Purpose: inspect in-flight channel state in Asterisk.
- Example:
```json
{"tool":"asterisk.active_channels","args":{"pbx_id":"pbx-1","limit":200}}
```
- Interpretation: rising long-duration channels can indicate stuck media or bridge cleanup lag.

### `asterisk.bridges`
- Purpose: inspect bridge inventory for leaks and stalled bridges.
- Example:
```json
{"tool":"asterisk.bridges","args":{"pbx_id":"pbx-1","limit":200}}
```
- Interpretation: sustained bridge growth with no matching call growth suggests leak risk.

### `freeswitch.sofia_status`
- Purpose: inspect FreeSWITCH Sofia profile and gateway posture.
- Example:
```json
{"tool":"freeswitch.sofia_status","args":{"pbx_id":"fs-1"}}
```
- Interpretation: profile/gateway down states are direct indicators for registration and trunk incidents.

### `telecom.capture_snapshot`
- Purpose: collect bounded multi-signal evidence for on-call and escalation.
- Example:
```json
{"tool":"telecom.capture_snapshot","args":{"pbx_id":"pbx-1","limits":{"max_items":200}}}
```
- Interpretation: use `failed_sources` and warnings to detect partial observability gaps.

### `telecom.run_playbook`
- Purpose: execute deterministic read-only diagnosis flow.
- Example:
```json
{"tool":"telecom.run_playbook","args":{"name":"sip_registration_triage","pbx_id":"pbx-1","endpoint":"1001"}}
```
- Interpretation: use playbook buckets to classify incident state and pick the right runbook.

## Escalation Triggers
- P1 outage unresolved after initial diagnostic pass and one safe remediation attempt.
- Repeated failures after rollback validation.
- Suspected provider/network dependency failure.
- Observability degradation preventing confident diagnosis.
