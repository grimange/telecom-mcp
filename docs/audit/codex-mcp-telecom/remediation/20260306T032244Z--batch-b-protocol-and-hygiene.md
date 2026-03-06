# Batch B — Protocol and STDIO Hygiene

## Applied
- Hardened stdio startup path for closed/unavailable stdin in MCP SDK server:
  - catches stdin pipe registration failures (`PermissionError`, `OSError`, `ValueError`)
  - emits structured warning to `stderr`
  - exits cleanly without traceback noise
- Added regression test for `stdin=DEVNULL` startup behavior to ensure no traceback contamination.

## Files changed
- `src/telecom_mcp/mcp_server/server.py`
- `tests/test_mcp_stdio_initialize.py`

## Rationale
- Fixes deterministic lifecycle edge case (F-04) while preserving normal Codex piped stdio behavior.

## Expected effect
- Cleaner failure semantics in restricted runtime edge cases.
- No stdout protocol contamination introduced.

## Risk
- LOW (guarded branch only; normal path unchanged).
