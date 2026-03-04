# Telecom MCP Stack --- Tool Specification

This document defines the **tool contract** for the Telecom Operations
MCP Server that monitors and troubleshoots **Asterisk** and
**FreeSWITCH**.

Scope: - **Read-first** tools - Optional **safe** operational actions
(disabled by default) - Normalized response envelope across platforms

------------------------------------------------------------------------

## 1. Global Conventions

### 1.1 Tool Namespacing

Tools are grouped by domain:

-   `telecom.*` (cross-PBX, aggregated utilities)
-   `asterisk.*` (Asterisk-only)
-   `freeswitch.*` (FreeSWITCH-only)

### 1.2 Target Selection

All PBX-specific tools require:

-   `pbx_id: string` --- a stable identifier defined in `targets.yaml`
    (or equivalent config).

### 1.3 Normalized Response Envelope

All tools MUST return the envelope below:

``` json
{
  "ok": true,
  "timestamp": "2026-03-04T11:02:03Z",
  "target": { "type": "asterisk|freeswitch", "id": "pbx-1" },
  "duration_ms": 182,
  "correlation_id": "c-01HZY...",
  "data": {},
  "error": null
}
```

If `ok=false`, then `error` is populated and `data` may be empty.

### 1.4 Error Object (Standard)

``` json
{
  "code": "TIMEOUT|AUTH_FAILED|CONNECTION_FAILED|NOT_FOUND|NOT_ALLOWED|UPSTREAM_ERROR|VALIDATION_ERROR",
  "message": "Human-readable summary",
  "details": { "optional": "structured data for debugging" }
}
```

### 1.5 Modes and Authorization

The server MUST implement an authorization gate with at least these
modes:

-   `inspect` (default): read-only tools only
-   `plan`: read tools + generate recommendations (no mutations)
-   `execute_safe`: allow a small, explicit allowlist of safe actions
-   `execute_full`: maintenance-only (optional; discouraged)

Any tool marked **(Write)** below MUST require `execute_safe` or higher.

### 1.6 Timeouts and Retries

-   Default tool timeout: **3--5 seconds** (configurable per tool)
-   Backoff retry: **1 retry** for transient connection errors
    (optional)
-   All tools MUST be cancellation-safe.

### 1.7 Audit Logging

Every tool invocation MUST be audit-logged:

-   timestamp, correlation_id
-   tool name + args (redacted secrets)
-   caller identity (if available)
-   target pbx_id
-   outcome + duration

------------------------------------------------------------------------

## 2. Configuration Schema (Targets)

Recommended `targets.yaml` structure:

``` yaml
targets:
  - id: pbx-1
    type: asterisk
    host: 10.0.0.10
    ari:
      url: http://10.0.0.10:8088
      username_env: AST_ARI_USER_PBX1
      password_env: AST_ARI_PASS_PBX1
      app: telecom_mcp
    ami:
      host: 10.0.0.10
      port: 5038
      username_env: AST_AMI_USER_PBX1
      password_env: AST_AMI_PASS_PBX1

  - id: fs-1
    type: freeswitch
    host: 10.0.0.20
    esl:
      host: 10.0.0.20
      port: 8021
      password_env: FS_ESL_PASS_FS1
```

Notes: - Secrets are referenced by env var name and loaded at runtime. -
No secrets are stored in the repo.

------------------------------------------------------------------------

# 3. Tool Catalog

## 3.1 telecom.\* (Cross-PBX)

### 3.1.1 `telecom.list_targets`

**Purpose:** List configured targets and their high-level metadata.

**Args:** none

**Returns (`data`):**

``` json
{
  "targets": [
    {"id":"pbx-1","type":"asterisk","host":"10.0.0.10"},
    {"id":"fs-1","type":"freeswitch","host":"10.0.0.20"}
  ]
}
```

------------------------------------------------------------------------

### 3.1.2 `telecom.summary`

**Purpose:** One-call summary for dashboards and quick checks.

**Args:** - `pbx_id: string`

**Returns (`data`):**

``` json
{
  "version": "string",
  "uptime_seconds": 123456,
  "channels_active": 12,
  "registrations": {
    "endpoints_registered": 100,
    "endpoints_unreachable": 2
  },
  "trunks": {
    "up": 3,
    "down": 1
  },
  "notes": ["optional human-friendly notes"]
}
```

**Implementation Notes:** - Asterisk: combine AMI + ARI if present -
FreeSWITCH: ESL calls (sofia status, show calls/channels)

------------------------------------------------------------------------

### 3.1.3 `telecom.capture_snapshot`

**Purpose:** Collect an evidence bundle suitable for troubleshooting and
reports.

**Args:** - `pbx_id: string` - `include: object (optional)` -
`endpoints: boolean = true` - `trunks: boolean = true` -
`calls: boolean = true` - `registrations: boolean = true` -
`limits: object (optional)` - `max_items: int = 200`

**Returns (`data`):**

``` json
{
  "snapshot_id": "snap-...",
  "captured_at": "ISO8601",
  "summary": { "...": "see telecom.summary" },
  "endpoints": [],
  "trunks": [],
  "calls": [],
  "raw": {
    "asterisk": { "ami": {}, "ari": {} },
    "freeswitch": { "esl": {} }
  }
}
```

**Requirements:** - Must be bounded by limits to avoid huge payloads. -
Must include correlation_id for cross-linking logs/metrics.

------------------------------------------------------------------------

## 3.2 asterisk.\*

> Notes: - Prefer ARI for structured call objects and events. - Use AMI
> for PJSIPShow\* and operational visibility. - No arbitrary CLI command
> tool in v1.

### 3.2.1 `asterisk.health`

**Purpose:** Basic connectivity + service health.

**Args:** - `pbx_id: string`

**Returns (`data`):**

``` json
{
  "ari": {"ok": true, "latency_ms": 45},
  "ami": {"ok": true, "latency_ms": 30},
  "asterisk_version": "string",
  "pjsip_loaded": true
}
```

------------------------------------------------------------------------

### 3.2.2 `asterisk.pjsip_show_endpoint`

**Purpose:** Inspect a PJSIP endpoint.

**Args:** - `pbx_id: string` - `endpoint: string`

**Returns (`data`):**

``` json
{
  "endpoint": "1001",
  "exists": true,
  "state": "Available|Unavailable|Unknown",
  "contacts": [
    {"uri":"sip:1001@1.2.3.4:5060","status":"Avail","rtt_ms":12}
  ],
  "aor": "1001",
  "raw": { "ami_action": "PJSIPShowEndpoint", "ami_response": {} }
}
```

**Errors:** - `NOT_FOUND` if endpoint absent (or return `exists=false`
--- pick one approach and keep consistent)

------------------------------------------------------------------------

### 3.2.3 `asterisk.pjsip_show_endpoints`

**Purpose:** List endpoints and high-level state.

**Args:** - `pbx_id: string` - `filter: object (optional)` -
`starts_with: string` - `contains: string` -
`limit: int (optional) = 200`

**Returns (`data`):**

``` json
{
  "items": [
    {"endpoint":"1001","state":"Available","contacts":1},
    {"endpoint":"1002","state":"Unavailable","contacts":0}
  ],
  "next_cursor": "optional"
}
```

------------------------------------------------------------------------

### 3.2.4 `asterisk.pjsip_show_registration`

**Purpose:** Inspect outbound registration objects (trunks).

**Args:** - `pbx_id: string` - `registration: string`

**Returns (`data`):**

``` json
{
  "registration": "trunk-1",
  "state": "Registered|Rejected|Unregistered|Unknown",
  "last_error": "string|null",
  "raw": {}
}
```

------------------------------------------------------------------------

### 3.2.5 `asterisk.active_channels`

**Purpose:** List active channels.

**Args:** - `pbx_id: string` - `filter: object (optional)` -
`state: string` - `caller: string` - `callee: string` -
`limit: int (optional) = 200`

**Returns (`data`):**

``` json
{
  "channels": [
    {"channel_id":"...","name":"PJSIP/1001-0000001a","state":"Up","caller":"1001","callee":"1800...","duration_s":42}
  ]
}
```

Implementation: ARI preferred; AMI fallback acceptable.

------------------------------------------------------------------------

### 3.2.6 `asterisk.bridges`

**Purpose:** List active bridges (mixing, holding, etc.).

**Args:** - `pbx_id: string` - `limit: int (optional) = 200`

**Returns (`data`):**

``` json
{
  "bridges": [
    {"bridge_id":"...","type":"mixing","channels":2}
  ]
}
```

------------------------------------------------------------------------

### 3.2.7 `asterisk.channel_details`

**Purpose:** Inspect one channel.

**Args:** - `pbx_id: string` - `channel_id: string`

**Returns (`data`):**

``` json
{
  "channel_id":"...",
  "name":"PJSIP/1001-0000001a",
  "state":"Up",
  "caller":"1001",
  "callee":"1800...",
  "bridge_id":"...|null",
  "raw": {}
}
```

------------------------------------------------------------------------

### 3.2.8 `asterisk.reload_pjsip` **(Write)**

**Purpose:** Reload PJSIP module (safe action for troubleshooting).

**Mode:** requires `execute_safe`

**Args:** - `pbx_id: string`

**Returns (`data`):**

``` json
{"reloaded": true}
```

**Guardrails:** - Must be explicitly enabled in config allowlist. - Must
include a cooldown window (e.g., do not allow more than once per 60s).

------------------------------------------------------------------------

## 3.3 freeswitch.\*

### 3.3.1 `freeswitch.health`

**Purpose:** Basic connectivity + version.

**Args:** - `pbx_id: string`

**Returns (`data`):**

``` json
{
  "esl": {"ok": true, "latency_ms": 40},
  "freeswitch_version": "string",
  "profiles": ["internal","external"]
}
```

------------------------------------------------------------------------

### 3.3.2 `freeswitch.sofia_status`

**Purpose:** SIP profile status overview.

**Args:** - `pbx_id: string` - `profile: string (optional)`

**Returns (`data`):**

``` json
{
  "profiles": [
    {"name":"internal","state":"RUNNING","registrations":50,"gateways":3},
    {"name":"external","state":"RUNNING","registrations":0,"gateways":2}
  ],
  "raw": {}
}
```

------------------------------------------------------------------------

### 3.3.3 `freeswitch.registrations`

**Purpose:** List SIP registrations.

**Args:** - `pbx_id: string` - `profile: string (optional)` -
`limit: int (optional) = 200`

**Returns (`data`):**

``` json
{
  "items": [
    {"user":"1001","contact":"sip:1001@1.2.3.4:5060","status":"Registered","expires_in_s":120}
  ],
  "raw": {}
}
```

------------------------------------------------------------------------

### 3.3.4 `freeswitch.gateway_status`

**Purpose:** Inspect a gateway status.

**Args:** - `pbx_id: string` - `gateway: string`

**Returns (`data`):**

``` json
{
  "gateway":"gw-1",
  "state":"UP|DOWN|UNKNOWN",
  "last_error":"string|null",
  "raw": {}
}
```

------------------------------------------------------------------------

### 3.3.5 `freeswitch.channels`

**Purpose:** List active channels.

**Args:** - `pbx_id: string` - `filter: object (optional)` -
`caller: string` - `callee: string` - `limit: int (optional) = 200`

**Returns (`data`):**

``` json
{
  "channels": [
    {"uuid":"...","caller":"1001","callee":"1800...","state":"CS_EXECUTE","duration_s":17}
  ],
  "raw": {}
}
```

------------------------------------------------------------------------

### 3.3.6 `freeswitch.calls`

**Purpose:** High-level calls listing (normalized).

**Args:** - `pbx_id: string` - `limit: int (optional) = 200`

**Returns (`data`):**

``` json
{
  "calls": [
    {"call_id":"...","legs":2,"state":"ACTIVE","duration_s":55}
  ],
  "raw": {}
}
```

------------------------------------------------------------------------

### 3.3.7 `freeswitch.reloadxml` **(Write)**

**Purpose:** Reload FreeSWITCH XML config.

**Mode:** requires `execute_safe`

**Args:** - `pbx_id: string`

**Returns (`data`):**

``` json
{"reloaded": true}
```

**Guardrails:** allowlist + cooldown.

------------------------------------------------------------------------

### 3.3.8 `freeswitch.sofia_profile_rescan` **(Write)**

**Purpose:** Rescan a Sofia profile.

**Mode:** requires `execute_safe`

**Args:** - `pbx_id: string` - `profile: string`

**Returns (`data`):**

``` json
{"rescanned": true, "profile":"internal"}
```

------------------------------------------------------------------------

# 4. Normalization Requirements

To support unified troubleshooting, normalize these fields across PBXs:

-   `version`
-   `uptime_seconds`
-   `channels_active`
-   `endpoints_registered`
-   `trunks_up`, `trunks_down`
-   `calls[]` with consistent:
    -   `call_id`
    -   `caller`
    -   `callee`
    -   `state`
    -   `duration_s`

Each tool may additionally include `raw` for upstream protocol output.

------------------------------------------------------------------------

# 5. Operational Guardrails

## 5.1 Denylist

The following must never be exposed as tools in v1:

-   Asterisk: `core stop now`, arbitrary `Command`, module unload
-   FreeSWITCH: `shutdown`, arbitrary `bgapi` without allowlist

## 5.2 Rate Limiting

-   per-target: e.g., 10 requests/second burst, 2 requests/second
    sustained (configurable)
-   per-write-tool: strict cooldown

## 5.3 Redaction

Never log or return: - passwords - auth headers - tokens

------------------------------------------------------------------------

# 6. v1 Acceptance Criteria

v1 is complete when:

-   Tools listed in Sections 3.1--3.3 are implemented (read tools
    required; write tools optional)
-   Normalized envelope + error model is consistent
-   Configured targets load correctly with env-secrets
-   Audit logs include correlation IDs
-   Timeouts and failures are handled predictably
-   Asterisk and FreeSWITCH connectors are stable under reconnects

------------------------------------------------------------------------

# 7. Next Documents

Recommended companion docs in the repo:

-   `docs/security.md` (RBAC, allowlists, mode gating)
-   `docs/runbook.md` (how to add targets, common troubleshooting flows)
-   `docs/examples.md` (example tool invocations + expected outputs)
