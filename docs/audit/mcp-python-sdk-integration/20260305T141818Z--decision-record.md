# Decision Record: MCP Python SDK Integration

## Decision
**Option A selected:** `telecom-mcp` becomes an MCP Server (recommended default).

## Context
- `telecom-mcp` already exposes a robust tool catalog with strict telecom safety controls.
- Current runtime is custom stdio JSON dispatch, not official SDK MCP server registration.
- Python SDK (`modelcontextprotocol/python-sdk`) provides server primitives and transports aligned with target architecture.
- Existing connector/normalization layers should remain unchanged to reduce migration risk.

Evidence:
- Local server dispatch: `/home/ramjf/python-projects/telecom-mcp/src/telecom_mcp/server.py`
- SDK server primitives: `https://github.com/modelcontextprotocol/python-sdk/blob/b33c81167572096baeb7f7cff35987fc1168b28d/src/mcp/server/__init__.py`
- SDK quickstart server pattern: `https://github.com/modelcontextprotocol/python-sdk/blob/b33c81167572096baeb7f7cff35987fc1168b28d/examples/snippets/servers/mcpserver_quickstart.py`

## Alternatives Considered
### Option B: telecom-mcp as MCP Client
- Pros:
  - Could orchestrate external MCP services (simulators, inventory, runbooks).
- Cons:
  - Does not directly solve core need: exposing telecom tooling as MCP tools for upstream agents.
  - Adds dependency chain before server compatibility is fixed.

### Option C: Hybrid (server + client) now
- Pros:
  - Max flexibility in one phase.
- Cons:
  - Higher delivery risk and scope expansion.
  - Harder to preserve deterministic safety envelope in first migration step.

## Consequences
Positive:
- Fastest path to protocol-compliant MCP exposure for existing telecom tools.
- Minimal churn in business logic and safety controls.
- Clear incremental upgrade path to Streamable HTTP and client-side integrations later.

Negative/Tradeoffs:
- Initial phase remains server-only; client orchestration postponed.
- Adapter work required to preserve existing envelope semantics under SDK call results.

## Rollout Plan
1. Build SDK server adapter layer with 1-2 tools and existing envelope contract.
2. Validate mode gating/redaction/audit parity against current behavior.
3. Migrate full v1 tool catalog.
4. Add MCP resources/prompts for docs/runbooks.
5. Add optional MCP client integrations (GitHub MCP, PBX simulator MCP) in follow-up phase.
