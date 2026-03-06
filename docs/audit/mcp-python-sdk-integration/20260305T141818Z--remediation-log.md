# Stage-10 Remediation Log

## Run Metadata
- Prompt: `docs/prompts/stage--10-python-sdk-remediation-prompt.md`
- Run date: 2026-03-06
- Mode: remediation (code changes)

## Extracted Inputs
- Decision record: `docs/audit/mcp-python-sdk-integration/20260305T141818Z--decision-record.md`
- Integration plan: `docs/audit/mcp-python-sdk-integration/20260305T141818Z--integration-plan.md`

## Summary of Chosen Strategy
- Chosen strategy: **Option A** (`telecom-mcp` as MCP Server).
- Integration approach: add SDK adapter layer while keeping existing connectors/normalizers/tool logic intact.
- Transport order: stdio first, HTTP optional later.
- Safety baseline: deny-by-default real PBX actions, preserve sandbox-safe fixtures.

## Remediation Actions Completed
1. Added runtime dependency pin in `pyproject.toml`:
   - `mcp==1.26.0`
2. Added MCP SDK server package:
   - `src/telecom_mcp/mcp_server/__init__.py`
   - `src/telecom_mcp/mcp_server/__main__.py`
   - `src/telecom_mcp/mcp_server/runtime.py`
   - `src/telecom_mcp/mcp_server/fixtures.py`
   - `src/telecom_mcp/mcp_server/server.py`
3. Added required stage-10 tools:
   - `telecom.healthcheck`
   - `fixtures.load_scenario`
   - `state.list_calls`
   - `state.get_call`
4. Added gated real-PBX skeleton tools (default disabled):
   - `asterisk.ari.originate`
   - `asterisk.ari.hangup`
   - `asterisk.ami.send_action`
5. Added resources:
   - `contract://inbound-call/v0.1`
   - `audit://mcp-python-sdk-integration/latest`
6. Added prompts:
   - `investigate-originate-not-answered`
   - `generate-ari-integration-test-plan`
7. Added modernization docs:
   - `docs/modernization/state/inbound-call-v0.1.json`
   - `docs/modernization/mcp/README.md`
   - `docs/modernization/mcp/tool-catalog.md`
8. Added smoke harness:
   - `scripts/mcp_sdk_smoke.py`
9. Added tests for stage-10 behavior:
   - `tests/test_mcp_server_stage10.py`

## Notes
- The SDK client-based smoke path hung in this environment; remediation used the prompt-allowed subprocess harness path instead.
- The harness verifies stdio startup and deterministic tool/resource flows without PBX/network access.
- Verification rerun on 2026-03-06:
  - `pytest -q tests/test_mcp_server_stage10.py tests/test_tools_contract_smoke.py tests/test_authz.py`
  - `.venv/bin/python scripts/mcp_sdk_smoke.py`
