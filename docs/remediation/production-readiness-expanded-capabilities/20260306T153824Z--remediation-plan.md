# Remediation Plan

## finding: SH-MED-004
- source audit artifact: `20260306T152446Z--security-and-hardening-audit.md`
- impacted subsystem: server dispatch policy model
- files/modules:
  - `src/telecom_mcp/server.py`
  - `src/telecom_mcp/mcp_server/server.py`
  - `tests/test_mcp_server_stage10.py`
  - `tests/test_tools_contract_smoke.py`
- remediation approach:
  - add explicit per-tool capability-class metadata in dispatch
  - enforce optional runtime class allow-policy via env (`TELECOM_MCP_ALLOWED_CAPABILITY_CLASSES`)
  - surface allowed classes and class map in healthcheck policy output
- risk of change: low-medium (policy denials for newly constrained runtimes)
- required tests:
  - class policy denial for validation tool
  - healthcheck policy metadata assertions
- acceptance criteria:
  - capability classes are first-class server metadata
  - denied class emits fail-closed `NOT_ALLOWED` with policy details
- rollback consideration:
  - unset `TELECOM_MCP_ALLOWED_CAPABILITY_CLASSES` to restore default all-class allowance

## finding: OP-MED-001
- source audit artifact: `20260306T152446Z--operability-and-observability-audit.md`
- impacted subsystem: orchestration failure telemetry
- files/modules:
  - `src/telecom_mcp/tools/telecom.py`
  - `src/telecom_mcp/observability/metrics.py`
  - `tests/test_observability.py`
  - `tests/test_tools_contract_smoke.py`
- remediation approach:
  - classify delegated subcall failures into explicit taxonomy reason codes
  - record counters keyed by `caller->callee:reason`
  - annotate `failed_sources` with `contract_failure_reason`
- risk of change: low (additive observability fields)
- required tests:
  - metrics snapshot includes contract-failure counter family
  - orchestrated failures include reason annotation
- acceptance criteria:
  - telemetry exposes caller/callee/reason taxonomy
  - operator-facing evidence includes reason code per failed delegated source
- rollback consideration:
  - additive fields can be ignored by downstream consumers if needed

## finding: SH-MED-005
- source audit artifact: `20260306T152446Z--security-and-hardening-audit.md`
- impacted subsystem: orchestration integration tests
- files/modules:
  - `tests/test_tools_contract_smoke.py`
- remediation approach:
  - add non-mocked integration path through real `TelecomMCPServer.execute_tool`:
    - `telecom.run_probe` -> `telecom.run_registration_probe` -> delegated vendor write tool denial
  - assert resulting contract-failure taxonomy and metrics
- risk of change: low (test-only)
- required tests:
  - execute-safe integration test without replacing orchestration tool handlers
- acceptance criteria:
  - CI catches delegated contract regression through real dispatch path
- rollback consideration:
  - remove only new integration test if environment assumptions change
