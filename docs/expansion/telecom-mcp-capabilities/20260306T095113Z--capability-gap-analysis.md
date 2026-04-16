# Capability Gap Analysis

Timestamp: `20260306T095113Z`

## Current tool inventory

### telecom.*
- `telecom.list_targets`
- `telecom.summary`
- `telecom.capture_snapshot`
- `telecom.endpoints` (new)
- `telecom.registrations` (new)
- `telecom.channels` (new)
- `telecom.calls` (new)
- `telecom.logs` (new)
- `telecom.inventory` (new)

### asterisk.*
- `asterisk.health`
- `asterisk.pjsip_show_endpoint`
- `asterisk.pjsip_show_endpoints`
- `asterisk.pjsip_show_registration`
- `asterisk.pjsip_show_contacts` (new)
- `asterisk.active_channels`
- `asterisk.bridges`
- `asterisk.channel_details`
- `asterisk.version` (new)
- `asterisk.logs` (new)
- `asterisk.reload_pjsip` (gated write)

### freeswitch.*
- `freeswitch.health`
- `freeswitch.sofia_status`
- `freeswitch.registrations`
- `freeswitch.gateway_status`
- `freeswitch.channels`
- `freeswitch.calls`
- `freeswitch.version` (new)
- `freeswitch.logs` (new)
- `freeswitch.reloadxml` (gated write)
- `freeswitch.sofia_profile_rescan` (gated write)

## Capability map

- Troubleshooting: health, channels/calls, endpoint visibility, log access (configured file source), snapshots.
- Auditing: inventory baseline now available via `telecom.inventory`; module-level auditing still limited.
- Testing/validation: strong fixture-backed tests; no active probe/originate tools in inspect mode.
- Agent usability: improved by vendor-neutral wrappers (`telecom.*`) with stable normalized fields.

## Strong areas

- Read-first architecture remains intact.
- Envelope and error mapping are consistent.
- Safety model (mode gate + allowlist + cooldown + intent metadata) remains enforced.
- Test coverage includes wrapper coercion, registry, and new Batch 1 functionality.

## Missing areas

- Snapshot diffing tool not implemented.
- Compare-targets tool not implemented.
- CLI/API allowlisted deep diagnostics (Batch 2) not implemented.
- Audit module/version posture beyond version string is incomplete.
- Active validation probes are deferred.

## Duplication or abstraction drift

- Existing vendor tools kept for backward compatibility.
- New vendor-neutral wrappers reduce cross-platform parsing in agents.
- No destructive rewrite; additive expansion only.

## Immediate code hotspots

- `src/telecom_mcp/tools/telecom.py`: wrapper normalization and inventory composition.
- `src/telecom_mcp/tools/asterisk.py`: contacts/version/log readers.
- `src/telecom_mcp/tools/freeswitch.py`: version/log readers.
- `src/telecom_mcp/mcp_server/server.py`: catalog exposure and argument coercion.

## Capability matrix

### Troubleshooting
- target connectivity checks: Present
- registration visibility: Present
- endpoint/contact visibility: Partial
- channel/call/bridge visibility: Present
- filtered logs: Present
- per-object deep inspection: Partial
- safe command diagnostics: Partial
- snapshot capture: Present
- snapshot diffing: Missing
- normalized failure summaries: Partial

### Auditing
- configuration inventory: Partial
- version/module inventory: Partial
- trunk/gateway posture: Partial
- endpoint/auth/AOR/transport inventory: Partial
- drift detection across PBXs: Missing
- baseline/security posture checks: Partial
- exportable evidence artifacts: Present

### Testing / Validation
- smoke tests: Present
- assert-style checks: Partial
- state verification after action: Partial
- active originate probes: Missing
- reproducible fixtures/scenarios: Present
- cleanup verification: Missing
- failure-path validation: Present

### Agent Usability
- consistent naming: Partial
- predictable schemas: Partial
- vendor-neutral abstractions: Present
- safe defaults: Present
- bounded limits and filters: Present
- human-readable summaries: Present
- machine-stable structured fields: Partial
