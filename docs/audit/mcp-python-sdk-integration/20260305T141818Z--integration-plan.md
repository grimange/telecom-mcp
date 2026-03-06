# Integration Plan: telecom-mcp + MCP Python SDK

## Scope
Read-only planning output for remediation pipeline. No code changes executed in this stage.

## 8.1 Target Architecture
### Layered architecture
- **MCP server adapter layer (new):** registers tools/resources/prompts via Python SDK.
- **Core telecom logic (existing, unchanged initially):** current `tools/`, `connectors/`, `normalize/`, `authz/`, `envelope/`.
- **Optional MCP client integrations (later):** GitHub MCP and PBX simulator MCP as external dependencies.

### Data flow
1. MCP SDK receives request.
2. Adapter validates/normalizes input.
3. Existing telecom tool function executes (connector + normalization path).
4. Existing envelope returned as tool payload.
5. Audit + metrics preserved.

Evidence:
- Existing layered logic: `/home/ramjf/python-projects/telecom-mcp/src/telecom_mcp/tools/asterisk.py`
- SDK registration model: `https://github.com/modelcontextprotocol/python-sdk/blob/b33c81167572096baeb7f7cff35987fc1168b28d/examples/snippets/servers/mcpserver_quickstart.py`

## 8.2 Proposed MCP Surface
### Tools (initial)
- `telecom.list_targets(args={})`
- `telecom.summary({pbx_id})`
- `telecom.capture_snapshot({pbx_id, include?, limits?})`
- `asterisk.health({pbx_id})`
- `asterisk.pjsip_show_endpoint({pbx_id, endpoint})`
- `asterisk.pjsip_show_endpoints({pbx_id, filter?, limit?})`
- `freeswitch.health({pbx_id})`
- `freeswitch.sofia_status({pbx_id, profile?})`

Output contract for all tools:
- existing deterministic telecom envelope (`ok/timestamp/target/duration_ms/correlation_id/data/error`).

### Resources (initial)
- `telecom://targets` -> sanitized targets inventory from config (no secrets).
- `telecom://catalog` -> tool catalog metadata and argument docs.
- `telecom://modes` -> operational mode policy and write-gating summary.

### Prompts (initial)
- `telecom.triage.incident` -> generic telecom outage triage sequence.
- `asterisk.debug.endpoint_unreachable` -> endpoint state diagnosis checklist.
- `freeswitch.debug.registration_failure` -> registration/gateway failure checklist.

## 8.3 Project Layout Changes (planned)
Proposed additions:
- `src/telecom_mcp/mcp_server/server.py`
- `src/telecom_mcp/mcp_server/tools/telecom.py`
- `src/telecom_mcp/mcp_server/tools/asterisk.py`
- `src/telecom_mcp/mcp_server/tools/freeswitch.py`
- `src/telecom_mcp/mcp_server/resources/targets.py`
- `src/telecom_mcp/mcp_server/resources/catalog.py`
- `src/telecom_mcp/mcp_server/prompts/triage.py`
- `src/telecom_mcp/mcp_server/adapters.py` (translate SDK request args -> existing tool calls)

Compatibility note:
- keep existing `src/telecom_mcp/server.py` temporarily as compatibility runtime shim until cutover.

## 8.4 Transport Phases
### Phase 1: stdio
- Use SDK stdio server transport for local dev and CI.
- Keep existing command-line startup contract (`python -m telecom_mcp ...`) via new adapter entrypoint.

### Phase 2: Streamable HTTP
- Add optional HTTP server mode for remote/Kubernetes use.
- Apply strict bind, auth, TLS termination, and CORS policy.
- Keep disabled-by-default outside controlled env.

## 8.5 Security & Policy
- **Allowlist by environment:** write tools disabled by default, explicit env-based enablement only.
- **Redaction rules:** never emit secrets from target config or connector auth payloads.
- **Credential contract:** continue using `*_env` variables in targets file; never store plaintext secrets.
- **Deny by default:** in sandbox/inspect mode, only read tools; no write path accessible.
- **Audit continuity:** preserve correlation_id, tool args (redacted), mode, duration, result.

## 8.6 Milestones + Task Batches
### Batch 1: Skeleton server + 1 tool
- Add SDK dependency and `mcp_server/server.py` bootstrapping.
- Register one tool (`telecom.list_targets`) via adapter.
- Add contract tests for envelope parity.

### Batch 2: Resources + prompts
- Add `telecom://targets`, `telecom://catalog`, initial triage prompts.
- Add tests for resource reads and prompt retrieval.

### Batch 3: ARI/AMI toolset
- Register all Asterisk and telecom tools listed in v1 catalog.
- Ensure mode gating/write policy preserved.
- Add parity tests vs existing tool outputs.

### Batch 4: PBX simulator MCP for sandbox
- Add optional simulator integration path for deterministic CI without real PBX.
- Add scenario tests for failure modes and error-code mapping.

### Batch 5: Packaging + docs + examples
- Update packaging entrypoints and README run instructions.
- Provide minimal server and client examples.
- Add migration notes from legacy json-line protocol.

## Exit Criteria for Remediation
- SDK server starts and exposes v1 tool catalog.
- Existing envelope and error contracts preserved.
- Mode gating and redaction verified by tests.
- CI passes for contract smoke tests and authz tests.
