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
- `telecom.run_playbook`
- `telecom.run_smoke_suite`
- `telecom.baseline_create`
- `telecom.baseline_show`
- `telecom.audit_target`
- `telecom.drift_target_vs_baseline`
- `telecom.drift_compare_targets`
- `telecom.audit_report`
- `telecom.audit_export`
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

## Troubleshooting Playbooks and Smoke Suites

Playbooks are deterministic multi-step troubleshooting workflows. Smoke suites are short repeatable health validations.

Safe by default:
- `telecom.run_playbook` is read-only.
- `telecom.run_smoke_suite` defaults to read-only suites.
- `active_validation_smoke` remains mode-gated and probe-gated.

Examples:
- Run SIP registration triage for endpoint 1001:
  - `{"tool":"telecom.run_playbook","args":{"name":"sip_registration_triage","pbx_id":"pbx-1","endpoint":"1001"}}`
- Run baseline smoke on PBX target:
  - `{"tool":"telecom.run_smoke_suite","args":{"name":"baseline_read_only_smoke","pbx_id":"pbx-1"}}`
- Compare PBX-A and PBX-B for drift:
  - `{"tool":"telecom.run_playbook","args":{"name":"pbx_drift_comparison","pbx_a":"pbx-1","pbx_b":"fs-1"}}`
- Run outbound failure triage after a failed test call:
  - `{"tool":"telecom.run_playbook","args":{"name":"outbound_call_failure_triage","pbx_id":"pbx-1","endpoint":"1001","destination_hint":"18005550199"}}`
- Interpret playbook/smoke results:
  - Playbooks return `status`, `bucket`, `steps`, `evidence`, `warnings`, `failed_sources`.
  - Smoke suites return `status`, `checks`, `counts`, `warnings`, `failed_sources`.

Audit examples:
- `{"tool":"telecom.baseline_create","args":{"pbx_id":"pbx-1","baseline_id":"prod-asterisk-v1"}}`
- `{"tool":"telecom.audit_target","args":{"pbx_id":"pbx-1","baseline_id":"prod-asterisk-v1"}}`
- `{"tool":"telecom.drift_compare_targets","args":{"pbx_a":"pbx-1","pbx_b":"fs-1"}}`
- `{"tool":"telecom.audit_report","args":{"pbx_id":"pbx-1"}}`

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
