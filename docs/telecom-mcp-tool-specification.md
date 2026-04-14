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

### 3.1.0 `telecom.healthcheck` (Additive Extension)

**Purpose:** Return server runtime diagnostics and configuration preflight signals.

**Args:** none

**Returns (`data`):**

``` json
{
  "server": "telecom-mcp",
  "mode": "inspect",
  "transport": "stdio",
  "targets_count": 1,
  "startup_warnings": [],
  "preflight": {
    "platform_coverage": {"configured": ["asterisk"], "missing": ["freeswitch"]},
    "targets": [
      {"pbx_id":"pbx-1","type":"asterisk","secrets_ready":true,"missing_env":[]}
    ]
  }
}
```

------------------------------------------------------------------------

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
  "ami": {
    "ok": true,
    "latency_ms": 30,
    "connectivity_ok": true,
    "capability_ok": true,
    "capabilities": {
      "pjsip_show_endpoints": {"ok": true},
      "core_show_channels": {"ok": true}
    }
  },
  "asterisk_version": "string",
  "pjsip_loaded": true,
  "degraded": false,
  "warnings": [],
  "data_quality": {"degraded": false, "issues": []}
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

**Args:** - `pbx_id: string` - `reason: string` - `change_ticket: string` - `confirm_token: string (optional, required when TELECOM_MCP_CONFIRM_TOKEN is configured)`

**Returns (`data`):**

``` json
{"reloaded": true}
```

**Guardrails:** - Must be explicitly enabled in config allowlist. - Must
include a cooldown window (e.g., do not allow more than once per 60s).

------------------------------------------------------------------------

## 3.3 freeswitch.\*

### 3.3.1 `freeswitch.health`

**Purpose:** Read-only FreeSWITCH health witness covering ESL reachability, auth-backed reads, version, and Sofia profile discovery.

**Args:** - `pbx_id: string` - `include_raw: bool (optional, default false)`

**Returns (`data`):**

``` json
{
  "ok": true,
  "target": {"type":"freeswitch","id":"fs-1"},
  "observed_at": "2026-03-07T07:37:27Z",
  "transport": {"kind":"esl","ok":true,"status":"reachable"},
  "auth": {"ok":true,"status":"authenticated"},
  "command": {"name":["status","version","sofia status"],"ok":true,"status":"ok"},
  "payload": {
    "esl": {"ok": true, "latency_ms": 40},
    "freeswitch_version": "1.10.11-release",
    "profiles": [{"name":"internal","state":"RUNNING","registrations":2,"gateways":1}],
    "data_quality": {"completeness":"full","issues":[],"result_kind":"ok"}
  },
  "warnings": [],
  "error": null,
  "degraded": false,
  "esl": {"ok": true, "latency_ms": 40},
  "freeswitch_version": "string",
  "profiles": [{"name":"internal","state":"RUNNING","registrations":2,"gateways":1}]
}
```

------------------------------------------------------------------------

### 3.3.2 `freeswitch.capabilities`

**Purpose:** Machine-readable target capability and posture diagnostics for FreeSWITCH inspect-mode observability.

**Args:** - `pbx_id: string` - `include_raw: bool (optional, default false)`

**Returns (`data`):**

``` json
{
  "ok": true,
  "target": {"type":"freeswitch","id":"fs-1"},
  "observed_at": "2026-03-07T07:37:27Z",
  "transport": {"kind":"esl","ok":true,"status":"reachable"},
  "auth": {"ok":true,"status":"authenticated"},
  "command": {"name":"version","ok":true,"status":"ok"},
  "payload": {
    "mode": "inspect",
    "freeswitch_version": "1.10.11-release",
    "capabilities": {
      "target_reachability": {"supported":true,"available":true},
      "esl_socket_reachability": {"supported":true,"available":true},
      "auth_usability": {"supported":true,"available":true},
      "read_command_execution": {"supported":true,"available":true},
      "raw_evidence_mode": {"supported":true,"available":true},
      "passive_event_readback": {"supported":true,"available":true},
      "snapshot_support": {"supported":true,"available":true},
      "write_actions": {"supported":true,"available":false,"reason":"mode_blocked"}
    },
    "event_readback": {
      "state":"available|degraded|unavailable|starting",
      "monitor_state":"available|degraded|unavailable|starting",
      "buffer_capacity":128,
      "buffered_events":2,
      "dropped_events":0,
      "monitor_started_at":"2026-04-14T00:00:00Z",
      "last_event_at":"2026-04-14T00:00:00Z",
      "last_healthy_at":"2026-04-14T00:00:00Z",
      "idle_duration_ms":10,
      "is_stale":false,
      "staleness_reason":null,
      "session_id":"fs-events-fs-1-1234abcd"
    }
  }
}
```

**Freshness semantics:** `available` with no recent events is healthy-but-idle; `is_stale=true` indicates stale buffered posture or a degraded/unavailable monitor; `staleness_reason` distinguishes `event_stream_idle`, `monitor_degraded`, and `monitor_unavailable`.

------------------------------------------------------------------------

### 3.3.3 `freeswitch.recent_events`

**Purpose:** Read recent passive FreeSWITCH events from the internal bounded in-memory inspect-mode monitor.

**Args:** - `pbx_id: string` - `limit: int (optional, default 20, max 50)` - `event_names: string[] (optional)` - `event_family: string (optional)` - `include_raw: bool (optional, default false)`

**Returns (`data`):**

``` json
{
  "ok": true,
  "target": {"type":"freeswitch","id":"fs-1"},
  "observed_at": "2026-04-14T00:00:00Z",
  "transport": {"kind":"esl","ok":true,"status":"available"},
  "auth": {"ok":true,"status":"authenticated"},
  "command": {"name":"internal passive event buffer","ok":true,"status":"ok|empty_valid|degraded|unavailable"},
  "payload": {
    "events": [
      {
        "observed_at":"2026-04-14T00:00:00Z",
        "event_name":"CHANNEL_CREATE",
        "event_family":"channel",
        "identifiers":{"unique_id":"uuid-1"},
        "content_type":"text/event-plain",
        "session_id":"fs-events-fs-1-1234abcd",
        "target_id":"fs-1"
      }
    ],
    "counts":{"returned":1,"buffered":2},
    "filters":{"event_names":["CHANNEL_CREATE"],"event_family":"channel"},
    "event_buffer":{
      "capacity":128,
      "buffered_events":2,
      "dropped_events":0,
      "overflowed":false,
      "monitor_state":"available",
      "monitor_started_at":"2026-04-14T00:00:00Z",
      "last_event_at":"2026-04-14T00:00:00Z",
      "last_healthy_at":"2026-04-14T00:00:00Z",
      "idle_duration_ms":10,
      "is_stale":false,
      "staleness_reason":null,
      "session_id":"fs-events-fs-1-1234abcd"
    },
    "freshness":{
      "monitor_started_at":"2026-04-14T00:00:00Z",
      "last_event_at":"2026-04-14T00:00:00Z",
      "last_healthy_at":"2026-04-14T00:00:00Z",
      "idle_duration_ms":10,
      "monitor_age_ms":10,
      "is_stale":false,
      "staleness_reason":null,
      "stale_after_ms":60000,
      "monitor_state":"available"
    },
    "data_quality":{"completeness":"full","issues":[],"result_kind":"ok|empty_valid|degraded"}
  }
}
```

**Derivation / Filtering:** event names come from frame headers first, then from header-like lines in the raw body when needed; filters apply to those same derived values.

**Safety / Bounds:** internal subscription only, no persistent storage, no user session control, 128-event buffer cap, 50-event return cap, raw payload included only when `include_raw=true`.

------------------------------------------------------------------------

### 3.3.4 `freeswitch.sofia_status`

**Purpose:** SIP profile status overview.

**Args:** - `pbx_id: string` - `profile: string (optional)` - `include_raw: bool (optional, default false)`

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

### 3.3.5 `freeswitch.registrations`

**Purpose:** List SIP registrations.

**Args:** - `pbx_id: string` - `profile: string (optional)` -
`limit: int (optional) = 200` - `include_raw: bool (optional, default false)`

**Returns (`data`):**

``` json
{
  "ok": true,
  "command": {"status":"ok|empty_valid|parse_failed"},
  "items": [
    {"user":"1001","contact":"sip:1001@1.2.3.4:5060","status":"Registered","expires_in_s":120}
  ]
}
```

------------------------------------------------------------------------

### 3.3.6 `freeswitch.gateway_status`

**Purpose:** Inspect a gateway status.

**Args:** - `pbx_id: string` - `gateway: string` - `include_raw: bool (optional, default false)`

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

### 3.3.7 `freeswitch.route_check`

**Purpose:** Conservatively check whether a FreeSWITCH destination plausibly routes, using read-only evidence only.

**Mode:** `inspect`

**Args:** - `pbx_id: string` - `destination: string` - `context: string (optional, strongly encouraged)` - `caller_id_number: string (optional)` - `caller_context: string (optional)` - `profile: string (optional)` - `gateway: string (optional)` - `include_evidence: bool (optional, default false)`

**Returns (`data`):**

``` json
{
  "ok": true,
  "target": {"type":"freeswitch","id":"fs-1"},
  "observed_at":"2026-04-14T00:00:00Z",
  "route_status":"route_found|no_route|ambiguous|degraded|unsupported",
  "confidence":"high|medium|low",
  "matched_context":"default",
  "matched_extension":"local-1001",
  "matched_conditions":[
    {"field":"destination_number","expression":"^1001$","destination":"1001"}
  ],
  "required_dependencies":{
    "context":"default",
    "profile":"internal",
    "gateway":null,
    "caller_id_number":"1000",
    "caller_context":"default"
  },
  "blocking_findings":[],
  "warnings":[],
  "evidence":{
    "profiles":[{"name":"internal","state":"RUNNING","registrations":2,"gateways":1}],
    "gateways":[],
    "registrations":{"total":2,"matched_users":["1001"]}
  },
  "error":null
}
```

**Status meanings:** `route_found` means a static destination-number rule matched the supplied destination; `no_route` means bounded static evidence found the context but no matching rule, or found no requested context; `ambiguous` means evidence is partial or dynamic behavior may apply; `degraded` means required evidence collection failed or visible dependencies are unavailable; `unsupported` is reserved for unsupported future evidence modes.

**Confidence meanings:** `high` requires exact bounded static evidence; `medium` indicates a match or no-route with dependency uncertainty; `low` indicates incomplete, degraded, or dynamic evidence.

**Blocking findings:** expected codes include `NO_MATCHING_CONTEXT`, `NO_MATCHING_EXTENSION`, `PROFILE_UNAVAILABLE`, `GATEWAY_UNAVAILABLE`, `REGISTRATION_MISSING`, `TARGET_DEGRADED`, `ROUTE_EVIDENCE_INCOMPLETE`, and `DYNAMIC_DIALPLAN_UNSUPPORTED`.

**Limits:** This tool does not execute the dialplan, originate calls, mutate state, or prove dynamic dialplan behavior. `include_evidence=true` returns bounded raw readback evidence only.

------------------------------------------------------------------------

### 3.3.8 `freeswitch.channels`

**Purpose:** List active channels.

**Args:** - `pbx_id: string` - `limit: int (optional) = 200` - `include_raw: bool (optional, default false)`

**Returns (`data`):**

``` json
{
  "ok": true,
  "command": {"status":"ok|empty_valid|parse_failed"},
  "channels": [
    {"channel_id":"...","uuid":"...","caller":"1001","callee":"1800...","state":"CS_EXECUTE","duration_s":17}
  ]
}
```

------------------------------------------------------------------------

### 3.3.9 `freeswitch.calls`

**Purpose:** High-level calls listing (normalized).

**Args:** - `pbx_id: string` - `limit: int (optional) = 200` - `include_raw: bool (optional, default false)`

**Returns (`data`):**

``` json
{
  "ok": true,
  "command": {"status":"ok|empty_valid|parse_failed"},
  "calls": [
    {"call_id":"...","legs":2,"state":"ACTIVE","duration_s":55}
  ]
}
```

------------------------------------------------------------------------

### 3.3.10 `freeswitch.reloadxml` **(Write)**

**Purpose:** Reload FreeSWITCH XML config.

**Mode:** requires `execute_safe`

**Args:** - `pbx_id: string`

**Returns (`data`):**

``` json
{"reloaded": true}
```

**Guardrails:** allowlist + cooldown.

------------------------------------------------------------------------

### 3.3.11 `freeswitch.sofia_profile_rescan` **(Write)**

**Purpose:** Rescan a Sofia profile.

**Mode:** requires `execute_safe`

**Args:** - `pbx_id: string` - `profile: string` - `reason: string` - `change_ticket: string` - `confirm_token: string (optional, required when TELECOM_MCP_CONFIRM_TOKEN is configured)`

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
-   `channels[]` with consistent:
    -   `channel_id` (canonical cross-platform key)

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
