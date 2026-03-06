# Deferred Items and Environment Notes

## Deferred findings

1. Network-restricted backend failures
- classification: `DEFER_ENVIRONMENTAL_ONLY`
- why not fixed: failures are caused by blocked socket/DNS access in current runtime.
- additional evidence needed: out-of-sandbox run with backend reachability.
- owner: ops/environment.

2. Telecom-backed scenario validation (reconnect, stale connection, backend latency)
- classification: `DEFER_ENVIRONMENTAL_ONLY`
- why not fixed: cannot be executed without network and reachable PBX endpoints.
- additional evidence needed: integration environment with allowed outbound connectivity.
- owner: ops/integration testing.

3. Schema/registration change requests not supported by deterministic defect evidence
- classification: `DEFER_INSUFFICIENT_EVIDENCE`
- why not fixed: no confirmed mismatch in tool registration or schema contract.
- additional evidence needed: reproducible failing case with concrete trace.

## Environment notes
- Current session indicates sandboxed network disablement (`CODEX_SANDBOX_NETWORK_DISABLED=1`).
- Interpret `CONNECTION_FAILED` for live telecom calls in this runtime as environment-limited evidence unless contradicted by out-of-sandbox traces.
