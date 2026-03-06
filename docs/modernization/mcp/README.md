# MCP Python SDK Server (telecom-mcp)

This package adds an MCP Python SDK server entrypoint at:

- `python -m telecom_mcp.mcp_server`

Default runtime behavior is sandbox-safe:

- `TELECOM_MCP_ENABLE_REAL_PBX=0`
- `TELECOM_MCP_FIXTURES=1`
- `TELECOM_MCP_TRANSPORT=stdio`

## Run

```bash
TELECOM_MCP_FIXTURES=1 TELECOM_MCP_ENABLE_REAL_PBX=0 python -m telecom_mcp.mcp_server
```

## Transport

- Default: `stdio`
- Optional: `http` (set `TELECOM_MCP_TRANSPORT=http`)

## Guardrails

- Fixture/state tools are deterministic and require no PBX network.
- Real-PBX tools are present as stubs and return `REAL_PBX_DISABLED` unless explicitly enabled.

## Tools

- `telecom.healthcheck`
- `fixtures.load_scenario`
- `state.list_calls`
- `state.get_call`
- `asterisk.ari.originate` (stub, gated)
- `asterisk.ari.hangup` (stub, gated)
- `asterisk.ami.send_action` (stub, gated)

## Resources

- `contract://inbound-call/v0.1`
- `audit://mcp-python-sdk-integration/latest`

## Prompts

- `investigate-originate-not-answered`
- `generate-ari-integration-test-plan`
