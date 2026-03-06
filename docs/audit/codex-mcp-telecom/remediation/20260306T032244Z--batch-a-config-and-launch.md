# Batch A — Configuration and Launch

## Applied
- Added explicit development validation command in top-level docs:
  - `.venv/bin/python -m pytest`
- Clarified default launch behavior in README:
  - `python -m telecom_mcp` starts MCP SDK JSON-RPC stdio server.
  - legacy line protocol requires `TELECOM_MCP_LEGACY_LINE_PROTOCOL=1`.

## Files changed
- `README.md`

## Rationale
- Resolves operational-assumption/config usage drift from audit findings without changing server behavior.

## Expected effect
- Fewer false-negative local audits caused by wrong test runner path or wrong protocol assumption.

## Risk
- LOW (documentation-only).
