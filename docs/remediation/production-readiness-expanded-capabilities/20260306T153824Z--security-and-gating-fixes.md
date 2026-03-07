# Security and Gating Fixes

## findings addressed
- `SH-MED-004`: addressed.
- `OP-MED-001`: addressed.
- `SH-MED-005`: addressed for delegated orchestration continuity via non-mocked integration path.

## code areas changed
- dispatch capability classes + policy enforcement:
  - `src/telecom_mcp/server.py`
- healthcheck policy surfacing for class model:
  - `src/telecom_mcp/mcp_server/server.py`
- internal subcall failure taxonomy + annotation:
  - `src/telecom_mcp/tools/telecom.py`
  - `src/telecom_mcp/observability/metrics.py`

## hardening improvements
- fail-closed capability-class policy in dispatch:
  - explicit classes: `observability`, `validation`, `chaos`, `remediation`, `export`
  - optional class allow policy: `TELECOM_MCP_ALLOWED_CAPABILITY_CLASSES`
- internal orchestration contract failures now produce deterministic reason codes and counters:
  - metric key shape: `caller_tool->delegated_tool:reason_code`
  - evidence annotation: `failed_sources[*].contract_failure_reason`

## residual risks
- class policy defaults to allow all classes when env is unset, by design for backward compatibility.
- non-mocked integration remains CI-local and does not include live PBX backend traffic.

## intentionally deferred issues
- none from the selected findings set.
