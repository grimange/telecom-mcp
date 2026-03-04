# Telecom MCP Stack --- Implementation Plan

## Overview

This document defines the implementation plan for a **Telecom Operations
MCP Server** designed to monitor and troubleshoot **Asterisk and
FreeSWITCH** systems.

The MCP server will expose a unified set of tools that AI agents (such
as Codex) can use to inspect telephony infrastructure safely.

The system is **read-first**, with optional safe operational actions.

Primary goals:

-   Unified monitoring interface for Asterisk and FreeSWITCH
-   Safe troubleshooting capabilities
-   Normalized output format for automation
-   Production‑grade observability and auditing
-   Compatibility with AI agent workflows

------------------------------------------------------------------------

# 1. Project Goals

The Telecom MCP Stack provides:

-   Monitoring of PBX nodes
-   Endpoint and trunk diagnostics
-   Active call inspection
-   Evidence capture for troubleshooting
-   Optional safe operational actions

Design philosophy:

-   **Read-first**
-   **Safe by default**
-   **Normalized outputs**
-   **Async-first networking**
-   **Auditable operations**

------------------------------------------------------------------------

# 2. High Level Architecture

The MCP server exposes tools while connectors communicate with telephony
systems.

Architecture:

Agent / Codex \| v Telecom MCP Server \| +---- Asterisk Connector \| -
ARI (HTTP/WebSocket) \| - AMI (TCP) \| +---- FreeSWITCH Connector \| -
ESL (TCP) \| - Optional SSH CLI \| +---- Optional Future Connectors -
Kamailio RPC - Prometheus metrics - Log aggregation

------------------------------------------------------------------------

# 3. Response Envelope Standard

All tool responses must follow a unified envelope format.

Example:

``` json
{
  "ok": true,
  "timestamp": "2026-03-04T11:02:03Z",
  "target": {"type": "asterisk", "id": "pbx-1"},
  "duration_ms": 182,
  "correlation_id": "c-01HZY...",
  "data": {},
  "error": null
}
```

Benefits:

-   Machine readable
-   Easy correlation across logs
-   Works well for AI reasoning
-   Enables auditability

------------------------------------------------------------------------

# 4. Tool Surface

## 4.1 Inventory and Health

Tools:

-   telecom.list_targets()
-   telecom.summary(pbx_id)
-   asterisk.health(pbx_id)
-   freeswitch.health(pbx_id)

Returns:

-   version
-   uptime
-   channel count
-   endpoint count
-   alarms

------------------------------------------------------------------------

## 4.2 SIP Endpoint Visibility

### Asterisk

Tools:

-   asterisk.pjsip_show_endpoint(pbx_id, endpoint)
-   asterisk.pjsip_show_endpoints(pbx_id)
-   asterisk.pjsip_show_registration(pbx_id)
-   asterisk.sip_peers(pbx_id)

### FreeSWITCH

Tools:

-   freeswitch.sofia_status(pbx_id)
-   freeswitch.registrations(pbx_id)
-   freeswitch.gateway_status(pbx_id)

------------------------------------------------------------------------

## 4.3 Call / Channel Troubleshooting

### Asterisk

Tools:

-   asterisk.active_channels(pbx_id)
-   asterisk.bridges(pbx_id)
-   asterisk.channel_details(pbx_id, channel_id)
-   asterisk.ari_app_status(pbx_id, app)

### FreeSWITCH

Tools:

-   freeswitch.channels(pbx_id)
-   freeswitch.calls(pbx_id)
-   freeswitch.show_calls(pbx_id)

All results should be normalized across platforms.

------------------------------------------------------------------------

## 4.4 Evidence Collection

Tool:

telecom.capture_snapshot(pbx_id)

The snapshot gathers:

-   system version
-   trunk registration status
-   endpoint summary
-   active call statistics
-   recent error indicators

Result:

A structured diagnostic bundle usable for automated troubleshooting.

------------------------------------------------------------------------

## 4.5 Safe Troubleshooting Actions (Optional)

Disabled by default.

Examples:

-   asterisk.reload_pjsip(pbx_id)
-   freeswitch.reloadxml(pbx_id)
-   freeswitch.sofia_profile_rescan(pbx_id, profile)

Dangerous commands must never be exposed.

------------------------------------------------------------------------

# 5. Security Requirements

Production safety rules:

1.  Per-target credentials
2.  Strict action allowlist
3.  Read-only default mode
4.  Global command timeout
5.  Full audit logging
6.  Rate limiting
7.  Environment isolation

Operational modes:

Inspect Mode (default) Plan Mode Execute Safe Mode Execute Full Mode

------------------------------------------------------------------------

# 6. Connectivity Design

## Asterisk

Protocols:

-   ARI (HTTP + WebSocket)
-   AMI (TCP)

Recommended usage:

ARI: Event streaming and structured state

AMI: Operational visibility commands

------------------------------------------------------------------------

## FreeSWITCH

Primary protocol:

ESL (Event Socket Library)

Capabilities:

-   show channels
-   show calls
-   sofia status
-   registration visibility

Optional fallback:

Read-only SSH command execution.

------------------------------------------------------------------------

# 7. Repository Structure

Suggested project layout:

    telecom-mcp/
      pyproject.toml
      README.md
      docs/
        security.md
        tools.md
        targets.example.yaml
      src/telecom_mcp/
        server.py
        config.py
        envelope.py
        authz.py
        connectors/
          asterisk_ami.py
          asterisk_ari.py
          freeswitch_esl.py
          ssh_exec.py
        tools/
          telecom.py
          asterisk.py
          freeswitch.py
        normalize/
          asterisk.py
          freeswitch.py
        logging.py

------------------------------------------------------------------------

# 8. Python Technology Stack

Recommended libraries:

-   asyncio
-   httpx
-   websockets
-   pydantic
-   pydantic-settings
-   redis (optional future state integration)

Custom clients recommended for:

-   AMI protocol
-   ESL protocol

Avoid heavy dependencies.

------------------------------------------------------------------------

# 9. Phase 1 Minimum Viable Implementation

Initial milestone:

1.  Target configuration loader
2.  Asterisk AMI connector
3.  FreeSWITCH ESL connector
4.  Endpoint inspection tools
5.  Channel listing tools
6.  Snapshot capture tool
7.  Response normalization
8.  Audit logging

This phase provides full monitoring capability.

------------------------------------------------------------------------

# 10. Future Extensions

Planned improvements:

-   Kamailio RPC connector
-   Prometheus metrics MCP
-   Log aggregation tools
-   SIP diagnostics (OPTIONS probing)
-   RTP diagnostics
-   Chaos simulation tools
-   Redis dialer state inspection

------------------------------------------------------------------------

# 11. Expected Benefits

A completed Telecom MCP Stack enables:

-   Automated PBX diagnostics
-   AI-driven telecom troubleshooting
-   Production readiness auditing
-   Consistent monitoring across platforms
-   Safe operational tooling

This MCP server becomes the **foundation layer for an AI‑assisted
telecom platform**.
