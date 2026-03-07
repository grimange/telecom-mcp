# telecom-mcp

Read-first MCP server for telecom observability and troubleshooting across Asterisk and FreeSWITCH.

## Installation

```bash
pip install telecom-mcp
```

## Quick start

1. Copy `docs/targets.example.yaml` to `targets.yaml` and update hosts/env names.
2. Export credentials referenced in `targets.yaml`.
3. Run:

```bash
python -m telecom_mcp --targets-file targets.yaml --mode inspect
```

To enable safe write tools in maintenance windows:

```bash
python -m telecom_mcp \
  --targets-file targets.yaml \
  --mode execute_safe \
  --write-allowlist asterisk.reload_pjsip,freeswitch.reloadxml \
  --cooldown-seconds 60
```

By default, `python -m telecom_mcp` starts the MCP Python SDK server over STDIO using JSON-RPC (`initialize`, `tools/list`, `tools/call`).

To use the legacy line-oriented protocol, set:

```bash
TELECOM_MCP_LEGACY_LINE_PROTOCOL=1 python -m telecom_mcp --targets-file targets.yaml
```

Legacy mode accepts one JSON request per line:

```json
{"tool":"telecom.list_targets","args":{},"correlation_id":"c-123"}
```

## Modes

- `inspect` (default): read-only
- `plan`: read + planning-only behavior
- `execute_safe`: reserved for allowlisted safe write tools
- `execute_full`: reserved maintenance mode

## Current tool catalog (v1 read)

- `telecom.healthcheck`
- `telecom.list_targets`
- `telecom.summary`
- `telecom.capture_snapshot`
- `asterisk.health`
- `asterisk.pjsip_show_endpoint`
- `asterisk.pjsip_show_endpoints`
- `asterisk.pjsip_show_registration`
- `asterisk.active_channels`
- `asterisk.bridges`
- `asterisk.channel_details`
- `asterisk.reload_pjsip` (mode-gated write tool)
- `freeswitch.health`
- `freeswitch.sofia_status`
- `freeswitch.registrations`
- `freeswitch.gateway_status`
- `freeswitch.channels`
- `freeswitch.calls`
- `freeswitch.reloadxml` (mode-gated write tool)
- `freeswitch.sofia_profile_rescan` (mode-gated write tool)

## Production Readiness Artifacts

Production readiness reports are generated into timestamped folders:

`docs/audit/production-readiness/YYYYMMDD-HHMMSS/`

Latest run:

`docs/audit/production-readiness/20260306-063351/`

Each run contains:

- `scorecard.md`
- `findings.md`
- `evidence/` (test/lint/type/security outputs)
- `runbook/`, `perf/`, `sbom/`, `release/`, `task-batches/`

## Using telecom_mcp with AI agents

`telecom_mcp` can be connected to MCP-capable agents such as Codex CLI, Claude Code / Claude CLI, and Gemini CLI.

Quickstart launch pattern:

```bash
/absolute/path/to/venv/bin/python -m telecom_mcp \
  --targets-file /absolute/path/to/targets.yaml \
  --mode inspect
```

Full multi-agent setup guide:

`docs/setup/telecom-mcp-with-ai-agents.md`

Troubleshooting first checks: verify target-file absolute path, exported credential environment variables, and restart the agent after MCP config changes.

## Development Validation

Run tests through the project virtual environment to ensure MCP dependencies are resolved:

```bash
.venv/bin/python -m pytest
```
