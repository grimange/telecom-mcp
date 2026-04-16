# Implementation Plan (Staged)

Timestamp: `20260306T095113Z`

## Batch 1 (implemented)

Tools:
- `telecom.logs`, `telecom.inventory`, `telecom.endpoints`, `telecom.registrations`, `telecom.channels`, `telecom.calls`
- `asterisk.logs`, `asterisk.pjsip_show_contacts`, `asterisk.version`
- `freeswitch.logs`, `freeswitch.version`

Files/modules modified:
- `src/telecom_mcp/tools/telecom.py`
- `src/telecom_mcp/tools/asterisk.py`
- `src/telecom_mcp/tools/freeswitch.py`
- `src/telecom_mcp/server.py`
- `src/telecom_mcp/mcp_server/server.py`
- `src/telecom_mcp/config.py`
- `src/telecom_mcp/normalize/asterisk.py`
- `tests/test_expansion_batch1_tools.py`
- `tests/test_mcp_server_stage10.py`
- `tests/test_tools_contract_smoke.py`

Dependencies:
- Existing AMI/ARI/ESL connectors.
- Optional log-file configuration (`targets.yaml` -> `logs.path`).

Risk level:
- Low to medium (read-only additions; no new write operations).

Acceptance criteria:
- Tools registered in core + SDK wrapper.
- Envelope/error contracts preserved.
- Full test suite passes.
- Docs updated.

Rollback:
- Remove additive registry entries and tool functions; no schema migration required.

## Batch 2 (deferred)

Tools:
- allowlisted `asterisk.cli`, allowlisted `freeswitch.api`
- `asterisk.core_show_channel` deep wrapper
- `freeswitch.channel_details`
- `telecom.diff_snapshots`

Dependencies:
- strict command allowlists, parser coverage, enhanced redaction.

Risk level:
- Medium to high (command execution surface).

## Batch 3 (deferred)

Tools:
- `telecom.compare_targets`
- richer module/version/config posture auditing

Dependencies:
- normalized inventory schema expansion and diff model.

Risk level:
- Medium.

## Batch 4 (deferred)

Tools:
- smoke/assert/probe/cleanup verification tools requiring stronger execution gating.

Dependencies:
- explicit execute-safe policy and probe sandboxing.

Risk level:
- High.
