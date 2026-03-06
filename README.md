# telecom-mcp

Read-first MCP server for telecom observability and troubleshooting across Asterisk and FreeSWITCH.

## Installation

PyPI: https://pypi.org/project/telecom-mcp

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

For active probe tools, also set:

```bash
export TELECOM_MCP_ENABLE_ACTIVE_PROBES=1
```

Optional hardening knobs for probes:

```bash
export TELECOM_MCP_PROBE_MAX_PER_MINUTE=5
export TELECOM_MCP_PROBE_MAX_TIMEOUT_S=30
```

Optional module posture policy overrides:

```bash
export TELECOM_MCP_CRITICAL_MODULES="res_pjsip.so,chan_pjsip.so"
export TELECOM_MCP_RISKY_MODULE_PATTERNS="app_system.so,func_shell.so,mod_shell_stream"
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
- `telecom.endpoints`
- `telecom.registrations`
- `telecom.channels`
- `telecom.calls`
- `telecom.logs`
- `telecom.inventory`
- `telecom.diff_snapshots`
- `telecom.compare_targets`
- `telecom.run_smoke_test`
- `telecom.assert_state`
- `telecom.run_registration_probe` (mode-gated active probe)
- `telecom.run_trunk_probe` (mode-gated active probe)
- `telecom.verify_cleanup`
- `asterisk.health`
- `asterisk.pjsip_show_endpoint`
- `asterisk.pjsip_show_endpoints`
- `asterisk.pjsip_show_registration`
- `asterisk.pjsip_show_contacts`
- `asterisk.active_channels`
- `asterisk.bridges`
- `asterisk.channel_details`
- `asterisk.core_show_channel`
- `asterisk.version`
- `asterisk.modules`
- `asterisk.logs`
- `asterisk.cli` (read-only allowlist)
- `asterisk.originate_probe` (mode-gated active probe)
- `asterisk.reload_pjsip` (mode-gated write tool)
- `freeswitch.health`
- `freeswitch.sofia_status`
- `freeswitch.registrations`
- `freeswitch.gateway_status`
- `freeswitch.channels`
- `freeswitch.calls`
- `freeswitch.channel_details`
- `freeswitch.version`
- `freeswitch.modules`
- `freeswitch.logs`
- `freeswitch.api` (read-only allowlist)
- `freeswitch.originate_probe` (mode-gated active probe)
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
