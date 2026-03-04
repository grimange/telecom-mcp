# Tools

## telecom.*

- `telecom.list_targets()`
- `telecom.summary(pbx_id)`
- `telecom.capture_snapshot(pbx_id, include?, limits?)`

## asterisk.*

- `asterisk.health(pbx_id)`
- `asterisk.pjsip_show_endpoint(pbx_id, endpoint)`
- `asterisk.pjsip_show_endpoints(pbx_id, filter?, limit?)`
- `asterisk.active_channels(pbx_id, filter?, limit?)`

## freeswitch.*

- `freeswitch.health(pbx_id)`
- `freeswitch.sofia_status(pbx_id)`
- `freeswitch.channels(pbx_id, limit?)`
