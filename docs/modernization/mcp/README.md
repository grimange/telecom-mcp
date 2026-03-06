# MCP Python SDK Server (telecom-mcp)

Current runtime entrypoints:

- `python -m telecom_mcp` (default MCP SDK path)
- `python -m telecom_mcp.mcp_server` (explicit MCP SDK path)

Legacy compatibility entrypoint:

- `TELECOM_MCP_LEGACY_LINE_PROTOCOL=1 python -m telecom_mcp`

## Run

```bash
python -m telecom_mcp --targets-file targets.yaml --mode inspect
```

## Transport

- Default: `stdio`
- Optional: `http` via `TELECOM_MCP_TRANSPORT=http` or `--transport http`

## Tool Surface (Current)

- `telecom.healthcheck`
- `telecom.list_targets`
- `telecom.summary`
- `telecom.capture_snapshot`
- `asterisk.health`
- `asterisk.pjsip_show_endpoint`
- `asterisk.pjsip_show_endpoints`
- `asterisk.pjsip_show_registration`
- `asterisk.active_channels`
- `asterisk.bridges`
- `asterisk.channel_details`
- `asterisk.reload_pjsip` (mode-gated write tool)
- `freeswitch.health`
- `freeswitch.sofia_status`
- `freeswitch.registrations`
- `freeswitch.gateway_status`
- `freeswitch.channels`
- `freeswitch.calls`
- `freeswitch.reloadxml` (mode-gated write tool)
- `freeswitch.sofia_profile_rescan` (mode-gated write tool)

## Resources

- `contract://inbound-call/v0.1`
- `audit://mcp-python-sdk-integration/latest`

## Prompts

- `investigate-target-health`
