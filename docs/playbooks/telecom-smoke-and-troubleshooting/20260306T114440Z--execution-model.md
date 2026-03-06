# Telecom Playbook and Smoke Execution Model

## Current Building Blocks
- Existing read-first telecom tools across `telecom.*`, `asterisk.*`, `freeswitch.*` provide health, endpoint/registration, channel/call, logs, inventory, and drift primitives.
- Existing envelope and error mapping layers already provide deterministic error handling.
- Existing active probe tooling is present but mode-gated.

## Gaps Blocking Playbooks (Pre-Implementation)
- No generic playbook runner and no shared deterministic step model.
- No playbook result schema with `status/bucket/steps/evidence`.
- No vendor-branching helper layer for reusable troubleshooting flows.

## Gaps Blocking Smoke Suites (Pre-Implementation)
- Only one fixed smoke tool (`telecom.run_smoke_test`) with limited check model.
- No discoverable suite catalog with stable names and reusable check rollup logic.
- No first-class suite envelope with `checks` and `counts`.

## Priority Missing Dependencies
- Generic `run_playbook` dispatcher.
- Generic `run_smoke_suite` dispatcher.
- Shared status rollup/check helpers.
- Consistent workflow output contracts.

## Recommended Implementation Assumptions
- Keep workflows read-only by default.
- Keep active validation gated behind mode + active-probe controls.
- Use existing telecom abstractions before vendor-specific tools.

## Playbook Model
Each playbook is implemented as a deterministic ordered sequence of steps with these modeled fields:
- `id`
- `title`
- `intent`
- `tool`
- `arguments_template`
- `required_inputs`
- `optional_inputs`
- `success_conditions`
- `warning_conditions`
- `failure_conditions`
- `evidence_fields`
- `fallback_steps`
- `human_guidance`

Runtime output for each step is normalized to:
- `id`
- `tool`
- `status` (`passed|warning|failed`)
- `summary`

## Playbook Result Envelope
Implemented result shape:
- `playbook`
- `pbx_id`
- `platform`
- `status`
- `bucket`
- `summary`
- `steps`
- `evidence`
- `warnings`
- `failed_sources`
- `captured_at`

## Smoke Suite Result Envelope
Implemented result shape:
- `suite`
- `pbx_id`
- `platform`
- `status`
- `summary`
- `checks`
- `counts` (`passed|warning|failed`)
- `warnings`
- `failed_sources`
- `captured_at`

## Framework Implementation Notes
- Added reusable helpers in `src/telecom_mcp/tools/telecom.py` for:
  - deterministic subcall execution
  - step/check status rollup
  - envelope assembly
  - vendor-aware branching
- Exposed workflows through:
  - `telecom.run_playbook`
  - `telecom.run_smoke_suite`
- Preserved backward compatibility by keeping `telecom.run_smoke_test` unchanged.
