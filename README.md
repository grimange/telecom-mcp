# telecom-mcp

Read-first MCP server for telecom observability and troubleshooting across Asterisk and FreeSWITCH.

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

The server runs over STDIO and accepts one JSON request per line:

```json
{"tool":"telecom.list_targets","args":{},"correlation_id":"c-123"}
```

## Modes

- `inspect` (default): read-only
- `plan`: read + planning-only behavior
- `execute_safe`: reserved for allowlisted safe write tools
- `execute_full`: reserved maintenance mode

## Current tool catalog (v1 read)

- `telecom.list_targets`
- `telecom.summary`
- `telecom.capture_snapshot`
- `asterisk.health`
- `asterisk.pjsip_show_endpoint`
- `asterisk.pjsip_show_endpoints`
- `asterisk.active_channels`
- `freeswitch.health`
- `freeswitch.sofia_status`
- `freeswitch.channels`

## Production Readiness Artifacts

Production readiness reports are generated into timestamped folders:

`docs/audit/production-readiness/YYYYMMDD-HHMMSS/`

Each run contains:

- `scorecard.md`
- `findings.md`
- `evidence/` (test/lint/type/security outputs)
- `runbook/`, `perf/`, `sbom/`, `release/`, `task-batches/`
