# telecom-mcp MCP Tool Catalog (Stage 10)

## Tools

- `telecom.healthcheck`: Returns server status, start timestamp, and runtime flags.
- `fixtures.load_scenario`: Loads one of `inbound_ring`, `originate_success`, `originate_no_answer`.
- `state.list_calls`: Lists call objects from loaded fixture scenario.
- `state.get_call`: Returns one call by `call_id`.
- `asterisk.ari.originate`: Real-PBX stub with explicit mode guard.
- `asterisk.ari.hangup`: Real-PBX stub with explicit mode guard.
- `asterisk.ami.send_action`: Real-PBX stub with explicit mode guard.

## Resources

- `contract://inbound-call/v0.1`: Golden inbound-call object schema.
- `audit://mcp-python-sdk-integration/latest`: Latest integration decision record.

## Prompts

- `investigate-originate-not-answered`
- `generate-ari-integration-test-plan`
