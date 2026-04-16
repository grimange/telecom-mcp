# Shared Control-Plane Design

Run timestamp (UTC): `20260306T161805Z`

## Design principles
- Fail-closed by default for active-capable paths.
- One safety policy contract reused across telecom and vendor tool modules.
- One active execution control boundary reused across probe/chaos/self-healing/vendor originate operations.
- Keep local subsystem logic focused on platform protocol specifics.

## Proposed shared modules
- `src/telecom_mcp/safety/policy.py`
  - `target_policy_actual(target)`
  - `target_allows_active_validation(target)`
  - `require_active_target_lab_safe(target, tool_name)`
  - `validate_probe_destination(destination)`
- `src/telecom_mcp/execution/active_control.py`
  - `ActiveOperationController.guard(operation, pbx_id)`
  - global singleton: `active_operation_controller`

## Contract interfaces
- Safety contract:
  - Input: target object with `environment`, `safety_tier`, `allow_active_validation`.
  - Output: boolean or `ToolError(NOT_ALLOWED)` with `required` vs `actual` details.
- Destination contract:
  - Input: raw destination string.
  - Output: normalized destination or `ToolError(VALIDATION_ERROR)`.
- Active concurrency contract:
  - Input: operation name + pbx id.
  - Output: execution guard or `ToolError(NOT_ALLOWED)` with active/limit metadata.
  - Policy envs: `TELECOM_MCP_ACTIVE_MAX_GLOBAL`, `TELECOM_MCP_ACTIVE_MAX_PER_TARGET`.

## Migration strategy
- Replace duplicated target eligibility functions in `tools/telecom.py`, `tools/asterisk.py`, `tools/freeswitch.py` with shared safety module calls.
- Replace duplicated probe destination validators in same modules with shared validator.
- Wrap active execution sections in shared concurrency guard:
  - `telecom.run_registration_probe`
  - `telecom.run_trunk_probe`
  - `telecom.run_probe` for class C probes
  - `telecom.run_chaos_scenario` for lab mode
  - `telecom.run_self_healing_policy` for remediation/active policies
  - `asterisk.originate_probe`
  - `freeswitch.originate_probe`

## Backward-compatibility strategy
- Preserve error codes and deny semantics (`NOT_ALLOWED`, `VALIDATION_ERROR`).
- Preserve existing message and details shape for lab-safe eligibility denials.
- Add only additive error detail fields for concurrency denials.

## Risks and tradeoffs
- In-process guard does not solve multi-process global coordination by itself.
- Concurrency limits can surface denials in overloaded active windows; operator runbook must include tuning/triage guidance.
- Centralized policy reduces divergence risk but raises blast radius if shared module regresses; mitigated with dedicated tests.
