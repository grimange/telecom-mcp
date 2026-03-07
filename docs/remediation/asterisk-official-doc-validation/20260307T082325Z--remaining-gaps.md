# Remaining Gaps

## Unresolved Findings

### DR-005
- Status: `deferred`
- Severity: Medium
- Issue: `Dial()` / `Stasis()` dialplan and ARI lifecycle semantics remain unverified due missing target dialplan and websocket evidence in this repo run.
- Why unresolved: remediation scope focused on code-level doc drift; no new dialplan artifacts were introduced.
- Recommended next pipeline: real-PBX docs-contract validation with dialplan and ARI websocket capture.

## Environment Gaps

- Live MCP endpoint not running updated code, so runtime proof for resolved items is pending deployment.
