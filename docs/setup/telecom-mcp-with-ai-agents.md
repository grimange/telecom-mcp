# telecom_mcp With AI Agents (MCP)

## Overview
`telecom_mcp` is a read-first MCP server for telecom observability and troubleshooting (Asterisk + FreeSWITCH).

MCP matters because it gives coding agents a standard way to discover and call telecom tools (`telecom.summary`, `asterisk.health`, `freeswitch.sofia_status`, etc.) with structured outputs.

This guide covers:
- Codex CLI
- Claude Code / Claude CLI
- Gemini CLI

## Prerequisites
- Python 3.11+ and a virtual environment.
- `telecom-mcp` installed in the same interpreter you will launch from.
- A targets file (for example `/absolute/path/to/targets.yaml`).
- Required credential environment variables referenced by your targets config.
- Network reachability from the agent runtime to your PBX infrastructure.

Safety baseline:
- Start in `--mode inspect` (read-only).
- Use mutating tools only in controlled maintenance windows with explicit allowlisting.

## Common Launch Pattern
Canonical launch:

```bash
/absolute/path/to/venv/bin/python -m telecom_mcp \
  --targets-file /absolute/path/to/targets.yaml \
  --mode inspect
```

Flag notes:
- `--targets-file`: path to target catalog YAML.
- `--mode`: `inspect`, `plan`, `execute_safe`, `execute_full`.
- Optional hardening flags: `--strict-startup`, `--tool-timeout-seconds`, `--cooldown-seconds`, `--write-allowlist`.

Environment notes:
- `TELECOM_MCP_TARGETS_FILE` can provide default target path.
- Secrets should be provided through environment variables only (never committed in plaintext config).

Use absolute paths for `python`, `targets.yaml`, and working directories in MCP config.

After changing MCP configuration files, restart the agent/CLI session.

## Codex CLI Setup
Primary docs:
- https://developers.openai.com/codex/config-basic
- https://developers.openai.com/codex/config-reference
- https://platform.openai.com/docs/docs-mcp

### Where config lives
- User: `~/.codex/config.toml`
- Project: `.codex/config.toml`

Codex config precedence (high to low) is documented in Config Basics (CLI flags, profiles, project config, user config, system config, defaults).

### Register `telecom_mcp` (stdio)
Add this to `~/.codex/config.toml` or `.codex/config.toml`:

```toml
[mcp_servers.telecom_mcp]
command = "/absolute/path/to/venv/bin/python"
args = [
  "-m",
  "telecom_mcp",
  "--targets-file",
  "/absolute/path/to/targets.yaml",
  "--mode",
  "inspect"
]
cwd = "/absolute/path/to/repo"
env = {
  AST_AMI_USER_PBX1 = "${AST_AMI_USER_PBX1}",
  AST_AMI_PASS_PBX1 = "${AST_AMI_PASS_PBX1}",
  AST_ARI_USER_PBX1 = "${AST_ARI_USER_PBX1}",
  AST_ARI_PASS_PBX1 = "${AST_ARI_PASS_PBX1}",
  FS_ESL_PASS_FS1 = "${FS_ESL_PASS_FS1}"
}
startup_timeout_sec = 20
tool_timeout_sec = 30
required = false
```

### Verify discovery
```bash
codex mcp list
```

Then ask Codex to run `telecom.healthcheck`.

### Example prompts
- `Run telecom.healthcheck and summarize startup warnings by code.`
- `For pbx-1, run telecom.summary and explain registrations vs channels.`
- `Capture a bounded troubleshooting snapshot for pbx-1 including endpoints and calls.`

### Common failure modes
- Target file not found: use absolute `--targets-file` path.
- Missing credentials: check env vars referenced in `targets.yaml`.
- No tools listed: validate TOML section name and restart Codex.

## Claude Code / Claude CLI Setup
Primary docs:
- https://docs.anthropic.com/en/docs/claude-code/mcp

### Official MCP configuration approach
Claude supports scoped MCP configuration (`local`, `project`, `user`) and project `.mcp.json` files.

Project-scope example via CLI:

```bash
claude mcp add telecom_mcp --scope project \
  /absolute/path/to/venv/bin/python -- \
  -m telecom_mcp \
  --targets-file /absolute/path/to/targets.yaml \
  --mode inspect
```

Equivalent `.mcp.json` format:

```json
{
  "mcpServers": {
    "telecom_mcp": {
      "command": "/absolute/path/to/venv/bin/python",
      "args": [
        "-m",
        "telecom_mcp",
        "--targets-file",
        "/absolute/path/to/targets.yaml",
        "--mode",
        "inspect"
      ],
      "env": {
        "AST_AMI_USER_PBX1": "${AST_AMI_USER_PBX1}",
        "AST_AMI_PASS_PBX1": "${AST_AMI_PASS_PBX1}",
        "AST_ARI_USER_PBX1": "${AST_ARI_USER_PBX1}",
        "AST_ARI_PASS_PBX1": "${AST_ARI_PASS_PBX1}"
      }
    }
  }
}
```

### Verify Claude sees tools
- Start Claude Code and run `/mcp`.
- Confirm `telecom_mcp` appears and exposes tools.

### Example prompts
- `Use telecom.list_targets and then run telecom.healthcheck.`
- `Inspect SIP endpoint inventory for pbx-1 and summarize unavailable endpoints.`
- `Run telecom.capture_snapshot for pbx-1 and list data_quality issues.`

### Known differences from Codex
- Claude uses `.mcp.json` JSON format for project-scoped sharing.
- Claude scope hierarchy and approval flow differ from Codex TOML layering.

## Gemini CLI Setup
Primary docs:
- https://github.com/google-gemini/gemini-cli/blob/main/docs/tools/mcp-server.md

### Where Gemini MCP config lives
Gemini MCP config uses `settings.json` with `mcpServers`.

CLI-managed scopes:
- User config: `~/.gemini/settings.json`
- Project config: `.gemini/settings.json`

### Example `mcpServers` config

```json
{
  "mcpServers": {
    "telecom_mcp": {
      "command": "/absolute/path/to/venv/bin/python",
      "args": [
        "-m",
        "telecom_mcp",
        "--targets-file",
        "/absolute/path/to/targets.yaml",
        "--mode",
        "inspect"
      ],
      "cwd": "/absolute/path/to/repo",
      "env": {
        "AST_AMI_USER_PBX1": "${AST_AMI_USER_PBX1}",
        "AST_AMI_PASS_PBX1": "${AST_AMI_PASS_PBX1}",
        "AST_ARI_USER_PBX1": "${AST_ARI_USER_PBX1}",
        "AST_ARI_PASS_PBX1": "${AST_ARI_PASS_PBX1}"
      },
      "timeout": 30000,
      "trust": false
    }
  }
}
```

You can also add with CLI (scope-aware):

```bash
gemini mcp add --scope project telecom_mcp /absolute/path/to/venv/bin/python -- \
  -m telecom_mcp --targets-file /absolute/path/to/targets.yaml --mode inspect
```

### Verify discovery
- Run `/mcp` in Gemini CLI and confirm server/tool status.
- Ask for `telecom.healthcheck` and verify output envelope.

### Known differences from Codex/Claude
- Gemini uses `settings.json` (`mcpServers`) and supports `command`, `url`, and `httpUrl` transports.
- Gemini exposes MCP management commands (`gemini mcp ...`) for add/list/enable/disable.

## Troubleshooting
- `AUTH_FAILED`: verify AMI/ARI/ESL credential env vars and PBX auth settings.
- Missing ARI/AMI credentials: healthcheck warnings and tool errors will indicate missing env names/capabilities.
- Target file not found: use absolute path and validate file exists in agent runtime context.
- No tools discovered: check MCP config file syntax and restart the agent.
- Weak SIP inventory output: endpoint state may be real telecom state, permission limits, or network reachability; confirm with `telecom.capture_snapshot`.
- Sandbox vs runtime limitation: skipped transport tests often indicate wrong interpreter/dependency environment.
- Network reachability: verify host/port/firewall from the agent runtime, not just local shell assumptions.

## Operational Guidance
- Start with read-only inspections and snapshots before any execute-safe operation.
- Never commit secrets in MCP config files.
- Separate audit runs and remediation runs as distinct tasks.
- Add a short AGENTS.md policy note in your own repos requiring read-first telecom workflows and explicit approval for mutating calls.

## Copy-Paste Prompts (All Agents)
- `Run telecom.healthcheck and summarize startup_warnings by code and impact.`
- `For pbx-1, run telecom.summary and explain registrations/endpoints_unreachable.`
- `Capture telecom.capture_snapshot for pbx-1 with include endpoints,calls and report data_quality/degraded signals.`

## Appendix
### A) Config template (stdio launch)
```text
command: /absolute/path/to/venv/bin/python
args: -m telecom_mcp --targets-file /absolute/path/to/targets.yaml --mode inspect
cwd: /absolute/path/to/repo
```

### B) Environment template
```bash
export AST_AMI_USER_PBX1='...'
export AST_AMI_PASS_PBX1='...'
export AST_ARI_USER_PBX1='...'
export AST_ARI_PASS_PBX1='...'
export FS_ESL_PASS_FS1='...'
```

### C) New-user checklist
- [ ] `telecom-mcp` installed in selected interpreter
- [ ] targets file exists and is readable
- [ ] required env vars exported
- [ ] agent MCP config added and saved
- [ ] agent restarted
- [ ] `telecom.healthcheck` works
