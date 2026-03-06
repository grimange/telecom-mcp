# Tools

## telecom.*

- `telecom.healthcheck()`
- `telecom.list_targets()`
- `telecom.summary(pbx_id)`
- `telecom.capture_snapshot(pbx_id, include?, limits?)`

## asterisk.*

- `asterisk.health(pbx_id)`
- `asterisk.pjsip_show_endpoint(pbx_id, endpoint)`
- `asterisk.pjsip_show_endpoints(pbx_id, filter?, limit?)`
- `asterisk.pjsip_show_registration(pbx_id, registration)`
- `asterisk.active_channels(pbx_id, filter?, limit?)`
- `asterisk.bridges(pbx_id, limit?)`
- `asterisk.channel_details(pbx_id, channel_id)`
- `asterisk.reload_pjsip(pbx_id)` (mode-gated write)

## freeswitch.*

- `freeswitch.health(pbx_id)`
- `freeswitch.sofia_status(pbx_id, profile?)`
- `freeswitch.registrations(pbx_id, profile?, limit?)`
- `freeswitch.gateway_status(pbx_id, gateway)`
- `freeswitch.channels(pbx_id, limit?)`
- `freeswitch.calls(pbx_id, limit?)`
- `freeswitch.reloadxml(pbx_id)` (mode-gated write)
- `freeswitch.sofia_profile_rescan(pbx_id, profile)` (mode-gated write)
