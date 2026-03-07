# Telecom Operations Quick Reference

## Global First Checks
- Health summary
```json
{"tool":"telecom.summary","args":{"pbx_id":"pbx-1"}}
```
- Capture evidence
```json
{"tool":"telecom.capture_snapshot","args":{"pbx_id":"pbx-1"}}
```

## Asterisk
- Check endpoints
```json
{"tool":"asterisk.pjsip_show_endpoints","args":{"pbx_id":"pbx-1","limit":200}}
```
- Check active channels
```json
{"tool":"asterisk.active_channels","args":{"pbx_id":"pbx-1","limit":200}}
```
- Check bridges
```json
{"tool":"asterisk.bridges","args":{"pbx_id":"pbx-1","limit":200}}
```
- Safe remediation (mode-gated)
```json
{"tool":"asterisk.reload_pjsip","args":{"pbx_id":"pbx-1","reason":"incident mitigation","change_ticket":"CHG-1234"}}
```

## FreeSWITCH
- Check Sofia posture
```json
{"tool":"freeswitch.sofia_status","args":{"pbx_id":"fs-1"}}
```
- Check registrations
```json
{"tool":"freeswitch.registrations","args":{"pbx_id":"fs-1","limit":200}}
```
- Check channels/calls
```json
{"tool":"freeswitch.channels","args":{"pbx_id":"fs-1","limit":200}}
```
```json
{"tool":"freeswitch.calls","args":{"pbx_id":"fs-1","limit":200}}
```
- Safe remediation (mode-gated)
```json
{"tool":"freeswitch.sofia_profile_rescan","args":{"pbx_id":"fs-1","profile":"external","reason":"incident mitigation","change_ticket":"CHG-1234"}}
```

## Automated Validation
- Read-only smoke
```json
{"tool":"telecom.run_smoke_suite","args":{"name":"baseline_read_only_smoke","pbx_id":"pbx-1"}}
```
- Incident triage playbook
```json
{"tool":"telecom.run_playbook","args":{"name":"outbound_call_failure_triage","pbx_id":"pbx-1"}}
```
- Probe list
```json
{"tool":"telecom.list_probes","args":{}}
```
