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

For active probe tools, also set:

```bash
export TELECOM_MCP_ENABLE_ACTIVE_PROBES=1
```

Active flows (Class C probes, lab chaos, risk-class B/C self-healing) are now fail-closed unless the target has explicit metadata:

- `environment: lab`
- `safety_tier: lab_safe`
- `allow_active_validation: true`

Optional hardening knobs for probes:

```bash
export TELECOM_MCP_PROBE_MAX_PER_MINUTE=5
export TELECOM_MCP_PROBE_MAX_TIMEOUT_S=30
```

Shared active-operation concurrency controls:

```bash
export TELECOM_MCP_ACTIVE_MAX_GLOBAL=4
export TELECOM_MCP_ACTIVE_MAX_PER_TARGET=2
```

Optional export and state hardening:

```bash
export TELECOM_MCP_RUNTIME_PROFILE=production
export TELECOM_MCP_EXPORT_MAX_EVIDENCE_ITEMS=200
export TELECOM_MCP_STATE_DIR=.telecom_mcp/state
export TELECOM_MCP_STRICT_STATE_PERSISTENCE=1
export TELECOM_MCP_ENFORCE_TARGET_POLICY=1
export TELECOM_MCP_ALLOWED_CAPABILITY_CLASSES=observability,validation,export
export TELECOM_MCP_ENABLE_HIGH_RISK_CAPABILITY_CLASSES=0
export TELECOM_MCP_REQUIRE_AUTHENTICATED_CALLER=1
export TELECOM_MCP_AUTH_TOKEN="set-a-strong-token"
export TELECOM_MCP_ALLOWED_CALLERS="ops-bot,release-gate"
export TELECOM_MCP_CALLER_ID="mcp-sdk"
export TELECOM_MCP_CALLER_TOKEN="$TELECOM_MCP_AUTH_TOKEN"
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

Capability x mode x environment guardrails:

- `inspect`: read-only tools only.
- `execute_safe`/`execute_full`: allowlisted write tools plus active frameworks.
- Active lab flows require explicit lab-safe target metadata (`environment=lab`, `safety_tier=lab_safe`, `allow_active_validation=true`).
- Environment rollups and release promotion enforce target membership by `target.environment`.
- Hardened startup can enforce explicit metadata policy checks (`TELECOM_MCP_ENFORCE_TARGET_POLICY=1`).
- Dispatch requires authenticated caller identity by default outside explicit lab/test profiles.
- Capability classes are now first-class dispatch metadata (`observability`, `validation`, `chaos`, `remediation`, `export`).
- When `TELECOM_MCP_ALLOWED_CAPABILITY_CLASSES` is unset, non-lab profiles fail closed to `observability` only.
- Hardened profiles (`production`, `prod`, `pilot`) require explicit capability-class policy and authenticated-caller/target-policy/strict-persistence controls at startup.
- In hardened profiles, enabling `chaos` or `remediation` classes requires explicit approval: `TELECOM_MCP_ENABLE_HIGH_RISK_CAPABILITY_CLASSES=1`.
- Runtime class policy override example: `TELECOM_MCP_ALLOWED_CAPABILITY_CLASSES=observability,validation,export`.
- Internal delegated-tool contract failures are emitted with taxonomy reason codes in `failed_sources[*].contract_failure_reason`.
- Shared safety policy module is used by telecom and vendor originate paths for active-target eligibility + probe destination validation (`src/telecom_mcp/safety/policy.py`).
- Shared active-operation concurrency guard is used by active probe/chaos/self-healing and vendor originate paths (`src/telecom_mcp/execution/active_control.py`).

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
- `telecom.scorecard_target`
- `telecom.scorecard_cluster`
- `telecom.scorecard_environment`
- `telecom.scorecard_compare`
- `telecom.scorecard_trend`
- `telecom.scorecard_export`
- `telecom.scorecard_policy_inputs`
- `telecom.capture_incident_evidence`
- `telecom.generate_evidence_pack`
- `telecom.reconstruct_incident_timeline`
- `telecom.export_evidence_pack`
- `telecom.list_probes`
- `telecom.run_probe`
- `telecom.list_chaos_scenarios`
- `telecom.run_chaos_scenario`
- `telecom.list_self_healing_policies`
- `telecom.evaluate_self_healing`
- `telecom.run_self_healing_policy`
- `telecom.release_gate_decision`
- `telecom.release_promotion_decision`
- `telecom.release_gate_history`
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
- `freeswitch.capabilities`
- `freeswitch.recent_events`
- `freeswitch.sofia_status`
- `freeswitch.registrations`
- `freeswitch.gateway_status`
- `freeswitch.route_check`
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
- `active_validation_smoke` remains mode-gated and probe-gated, and requires `params.reason` + `params.change_ticket`.

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

## Resilience Scorecards

Resilience scorecards provide explainable PBX/cluster/environment reliability scoring based on audit, smoke, playbook, and validation evidence.

Scorecard examples:
- Generate a scorecard for a PBX target:
  - `{"tool":"telecom.scorecard_target","args":{"pbx_id":"pbx-1"}}`
- Compare two PBX targets:
  - `{"tool":"telecom.scorecard_compare","args":{"entity_type":"pbx","entity_a":"pbx-1","entity_b":"fs-1"}}`
- Generate a cluster resilience scorecard:
  - `{"tool":"telecom.scorecard_cluster","args":{"cluster_id":"cluster-a","pbx_ids":["pbx-1","fs-1"]}}`
- Review trend changes for the last 30 days:
  - `{"tool":"telecom.scorecard_trend","args":{"entity_type":"pbx","entity_id":"pbx-1","window":"30d"}}`
- Interpret confidence and top risks:
  - check `scorecard.confidence`, `scorecard.confidence_reasons`, and `scorecard.top_risks`.

## Incident Evidence Packs

Incident evidence packs capture structured PBX telemetry, validation results, audit signals, and a reconstructed timeline for incident forensics.

Examples:
- `{"tool":"telecom.capture_incident_evidence","args":{"pbx_id":"pbx-1"}}`
- `{"tool":"telecom.generate_evidence_pack","args":{"pbx_id":"pbx-1","incident_type":"trunk_outage","incident_id":"inc-123"}}`
- `{"tool":"telecom.reconstruct_incident_timeline","args":{"pack_id":"pack-inc-123"}}`
- `{"tool":"telecom.export_evidence_pack","args":{"pack_id":"pack-inc-123","format":"markdown"}}`

Export behavior:

- `telecom.export_evidence_pack` performs export-time redaction of sensitive fields (`password`, `token`, `secret`, `authorization`).
- JSON/zip exports are bounded by `TELECOM_MCP_EXPORT_MAX_EVIDENCE_ITEMS` (default `200`) and include sensitivity labels.

## Gated Active Validation Probe Suite

Active validation probes are safety-gated runtime checks. Passive probes can run in inspect mode; active call/route probes require explicit validation controls.

Examples:
- Run a registration visibility probe:
  - `{"tool":"telecom.run_probe","args":{"name":"registration_visibility_probe","pbx_id":"pbx-1","params":{"endpoint":"1001"}}}`
- Run a controlled originate probe on a lab target:
  - `{"tool":"telecom.run_probe","args":{"name":"controlled_originate_probe","pbx_id":"pbx-1","params":{"destination":"1001","timeout_s":10,"reason":"active validation","change_ticket":"CHG-1002"}}}`
- Run post-change validation after a PBX config update:
  - `{"tool":"telecom.run_probe","args":{"name":"post_change_validation_probe_suite","pbx_id":"pbx-1","params":{"include_active":false}}}`
- Verify cleanup after active probing:
  - `{"tool":"telecom.run_probe","args":{"name":"cleanup_verification_probe","pbx_id":"pbx-1"}}`
- Use probe results to improve smoke suites and playbooks:
  - inspect `phases`, `evidence`, and `warnings` for failed assertions vs failed actions.

## Chaos Simulation Framework

Chaos scenarios are gated, bounded failure injections for fixture/lab validation of detection and rollback quality.

Examples:
- Run a fixture-only registration loss scenario:
  - `{"tool":"telecom.run_chaos_scenario","args":{"name":"sip_registration_loss","pbx_id":"pbx-1","params":{"mode":"fixture"}}}`
- Run trunk outage simulation in lab mode:
  - `{"tool":"telecom.run_chaos_scenario","args":{"name":"trunk_gateway_outage","pbx_id":"pbx-1","params":{"mode":"lab"}}}`
- Validate that rollback restored baseline smoke:
  - inspect `phases` for `rollback` + `postcheck` and verify `baseline_smoke_post` in `evidence`.
- Use chaos results to improve troubleshooting playbooks:
  - correlate `evidence.detections` with expected playbook/smoke detections.
- Use drift injection to validate audit policies:
  - run `drift_injection_fixture` and compare resulting `audit` evidence shifts.

## Self-Healing Policies

Self-healing policies are bounded, gated remediation decisions. Many cases intentionally escalate instead of acting when evidence or risk boundaries are not acceptable.

Examples:
- Evaluate whether self-healing is eligible for a target:
  - `{"tool":"telecom.evaluate_self_healing","args":{"pbx_id":"pbx-1","context":{"change_context":"post-deploy"}}}`
- Run a safe reload policy on a lab target:
  - `{"tool":"telecom.run_self_healing_policy","args":{"name":"safe_sip_reload_refresh","pbx_id":"pbx-1","params":{"reason":"refresh stale sip","change_ticket":"CHG-1001"}}}`
- Review why a policy escalated instead of acting:
  - inspect `gating_failures`, `escalation`, and `phases` in policy result.
- Verify that post-action smoke checks passed:
  - inspect `evidence.post.smoke_post` and `phases.verify`.
- Use evidence packs to review remediation history:
  - inspect `evidence.incident_evidence_pack` when escalation is required.

## Scorecard Policy Inputs

Scorecard policy inputs convert resilience scorecards into safe, explainable self-healing policy recommendation hints.

Safety boundaries:
- scorecards do not directly execute remediation
- low confidence blocks action-oriented recommendation handoff
- stale scorecards force evidence refresh before policy evaluation
- dimension-level degradation is used; total score alone is not enough
- output includes deterministic mapping provenance (`mapping_revision`, `mapping_schema`, `mapping_checksum`) for governance drift tracking

Examples:
- Generate self-healing policy inputs from a PBX scorecard:
  - `{"tool":"telecom.scorecard_policy_inputs","args":{"entity_type":"pbx","pbx_id":"pbx-1"}}`
- Review why a low score did not produce an automated recommendation:
  - inspect `policy_input.recommended_no_act_candidates`, `policy_input.required_evidence_refresh`, and `policy_input.policy_handoff.stop_conditions`.
- Use dimension-level degradation to prioritize safe policy evaluation:
  - inspect `policy_input.dimension_signals` and `policy_input.recommended_policy_candidates`.
- Verify mapping revision/checksum used by the policy-input decision:
  - inspect `policy_input.mapping_revision`, `policy_input.mapping_schema`, and `policy_input.mapping_checksum`.
- Refresh stale evidence before acting on scorecard signals:
  - if `policy_input.freshness != "fresh"`, run fresh smoke/playbook/audit collection before self-healing evaluation.
- Send scorecard-derived inputs into the self-healing policy engine:
  - call `telecom.evaluate_self_healing` and inspect `recommended_policy_candidates` and `scorecard_policy_handoff`.

## Production Readiness Artifacts

Production readiness reports are generated into timestamped folders:

`docs/audit/production-readiness/YYYYMMDD-HHMMSS/`

Latest run:

`docs/audit/production-readiness/20260306-063351/`

## Release Gates

A confidence-aware release gate engine is available for scorecard-policy-input + validation decisioning:
- MCP tool: `telecom.release_gate_decision`
- module: `telecom_mcp.release_gates.evaluate_release_gate`
- decisions: `allow`, `hold`, `escalate`
- inputs: scorecard policy input + validation status + change context

Examples:
- `{"tool":"telecom.release_gate_decision","args":{"pbx_id":"pbx-1"}}`
- `{"tool":"telecom.release_gate_decision","args":{"pbx_id":"pbx-1","context":{"high_risk_change":true}}}`
- `{"tool":"telecom.release_promotion_decision","args":{"environment_id":"staging","pbx_ids":["pbx-1","fs-1"],"context":{"high_risk_change":false}}}`
- `{"tool":"telecom.release_gate_history","args":{"entity_type":"environment","entity_id":"staging","limit":20}}`

Pipeline artifacts are under:
- `docs/release/scorecard-release-gates/`

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

## Hardening Notes

- `telecom.run_registration_probe` and `telecom.run_trunk_probe` are fail-closed unless the target is explicitly lab-safe (`environment=lab`, `safety_tier=lab_safe`, `allow_active_validation=true`).
- Wrapper probe success now requires delegated originate execution success; delegated denial is returned as top-level tool failure with `failed_sources` details.
- Use `docs/runbook.md` contract-failure taxonomy table to map `failed_sources[*].contract_failure_reason` to first-response actions.
- `asterisk.originate_probe` and `freeswitch.originate_probe` enforce the same target eligibility locally (defense in depth).
- State persistence failures are non-fatal but now surfaced as runtime warnings in affected outputs (scorecard, release-gate history, evidence-pack mutations).
- Baseline/probe/self-healing coordination state is persisted under `TELECOM_MCP_STATE_DIR`; set `TELECOM_MCP_STRICT_STATE_PERSISTENCE=1` to fail closed on critical persistence errors.

## Development Validation

Run tests through the project virtual environment to ensure MCP dependencies are resolved:

```bash
.venv/bin/python -m pytest
```
