# MCP Smoke Results (Stage-10)

## Environment
- Date: 2026-03-06
- Command: `.venv/bin/python scripts/mcp_sdk_smoke.py`
- Flags:
  - `TELECOM_MCP_FIXTURES=1`
  - `TELECOM_MCP_ENABLE_REAL_PBX=0`
  - `TELECOM_MCP_TRANSPORT=stdio`

## Results
- Server startup check (stdio): PASS
  - Process stayed alive in stdio mode for startup window.
- Tool discovery check: PASS
  - Required tools present:
    - `telecom.healthcheck`
    - `fixtures.load_scenario`
    - `state.list_calls`
    - `state.get_call`
- `telecom.healthcheck`: PASS
  - Returned `status=ok`
  - Mode flags showed fixtures enabled and real PBX disabled.
- `fixtures.load_scenario(originate_no_answer)`: PASS
- `state.list_calls`: PASS
  - Returned 1 call from loaded scenario.
- `state.get_call`: PASS
  - Returned call for `call-outbound-2002`.
- Resource check `contract://inbound-call/v0.1`: PASS
  - JSON contract parsed successfully.

## Raw Harness Output
```text
STARTUP: {"note": "process stayed alive in stdio mode for startup window", "ok": true}
FLOWS: {"call_count": 1, "first_call": {"call": {"call_id": "call-outbound-2002", "callee": "+12065550222", "caller": "2002", "direction": "outbound", "platform": "freeswitch", "state": "no_answer"}, "ok": true}, "health": {"mode": {"fixtures": true, "real_pbx": false, "transport": "stdio"}, "started_at": "2026-03-05T22:17:57Z", "status": "ok", "timestamp": "2026-03-05T22:17:57Z", "version": "0.1.3"}, "loaded": {"call_count": 1, "ok": true, "scenario": "originate_no_answer"}, "ok": true, "tools": ["asterisk.ami.send_action", "asterisk.ari.hangup", "asterisk.ari.originate", "fixtures.load_scenario", "state.get_call", "state.list_calls", "telecom.healthcheck"]}
SMOKE_OK
```
