# telecom-mcp MCP Tool Catalog (Current)

## Tools

- `telecom.healthcheck`: Returns server status, start timestamp, and runtime flags.
- `telecom.list_targets`: Lists configured telecom targets.
- `telecom.summary`: Returns one-call normalized summary for a target.
- `telecom.capture_snapshot`: Captures bounded troubleshooting evidence.
- `asterisk.health`: Checks AMI/ARI health for one Asterisk target.
- `asterisk.pjsip_show_endpoint`: Shows one PJSIP endpoint.
- `asterisk.pjsip_show_endpoints`: Lists PJSIP endpoints with optional filters.
- `asterisk.pjsip_show_registration`: Shows one outbound registration.
- `asterisk.active_channels`: Lists active channels.
- `asterisk.bridges`: Lists active bridges.
- `asterisk.channel_details`: Returns details for one channel.
- `asterisk.reload_pjsip`: Mode-gated safe action.
- `freeswitch.health`: Checks ESL health for one FreeSWITCH target.
- `freeswitch.sofia_status`: Returns Sofia status.
- `freeswitch.registrations`: Lists registrations.
- `freeswitch.gateway_status`: Returns one gateway status.
- `freeswitch.channels`: Lists channels.
- `freeswitch.calls`: Lists calls.
- `freeswitch.reloadxml`: Mode-gated safe action.
- `freeswitch.sofia_profile_rescan`: Mode-gated safe action.

## Resources

- `contract://inbound-call/v0.1`: Golden inbound-call object schema.
- `audit://mcp-python-sdk-integration/latest`: Latest integration decision record.

## Prompts

- `investigate-target-health`
