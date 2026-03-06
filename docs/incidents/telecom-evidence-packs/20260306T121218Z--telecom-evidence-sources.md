# Telecom Evidence Sources

## Runtime State Sources
- `telecom.summary`
- `telecom.capture_snapshot`
- `telecom.endpoints`
- `telecom.registrations`
- `telecom.channels`
- `telecom.calls`
- `telecom.logs`

## Vendor Sources
Asterisk:
- `asterisk.version`
- `asterisk.modules`
- `asterisk.pjsip_show_endpoints`
- `asterisk.pjsip_show_contacts`

FreeSWITCH:
- `freeswitch.version`
- `freeswitch.modules`
- `freeswitch.channels`
- `freeswitch.calls`
- `freeswitch.sofia_status`

## Validation/Audit Integrations
- smoke suite output (`telecom.run_smoke_suite`)
- playbook output (`telecom.run_playbook`)
- cleanup/probe output (`telecom.verify_cleanup`)
- audit/drift output (`telecom.audit_target`, `telecom.drift_target_vs_baseline`)

## Gaps / Limitations
- chaos and incident burden integrations are placeholders in this stage
- bridge-specific normalized source currently depends on platform-specific availability
