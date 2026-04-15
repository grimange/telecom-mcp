# Telecom On-Call Guide

## System Overview
- PBX architecture: mixed Asterisk (AMI/ARI) and FreeSWITCH (ESL) targets behind telecom MCP tooling.
- SIP flow: endpoints register to PBX profiles; trunks connect provider networks.
- Media flow: RTP/media bridges formed after signaling success.
- Control flow: MCP tools query normalized status and execute guarded workflows.

## Key Signals
- Registrations: `telecom.registrations`
- Active calls/channels: `telecom.calls`, `telecom.channels`
- Call failure posture: `telecom.summary` and triage playbooks
- Media sessions/bridges: `asterisk.bridges`, `freeswitch.calls`
- ARI/AMI signals: `asterisk.health`, `telecom.run_smoke_suite`

## Core Troubleshooting Workflow
1. Check `telecom.summary`.
2. Check registrations (`telecom.registrations` plus platform-specific registration tools).
3. Check active channels (`telecom.channels` / platform channels tool).
4. Check bridges or equivalent media state (`asterisk.bridges`, `freeswitch.calls`).
5. Capture snapshot (`telecom.capture_snapshot`) and tag with incident ID.

## Common First Steps
- Inspect SIP endpoints and contacts.
- Check trunk/gateway status.
- Verify PBX health by platform.
- Run read-only smoke suite and relevant playbook.
- Apply gated remediation only with approved ticket and rollback plan.

## Evidence Discipline
- Always capture pre-remediation and post-remediation snapshots.
- Record `correlation_id`, `pbx_id`, incident severity, and escalations made.
