# Tools

## telecom.*

- `telecom.healthcheck()`
- `telecom.list_targets()`
- `telecom.summary(pbx_id, fail_on_degraded?)`
- `telecom.capture_snapshot(pbx_id, include?, limits?, fail_on_degraded?)`
- `telecom.endpoints(pbx_id, filter?, limit?)`
- `telecom.registrations(pbx_id, limit?)`
- `telecom.channels(pbx_id, limit?)`
- `telecom.calls(pbx_id, limit?)`
- `telecom.logs(pbx_id, grep?, tail?, level?)`
- `telecom.inventory(pbx_id)`
- `telecom.diff_snapshots(snapshot_a, snapshot_b)`
- `telecom.compare_targets(pbx_a, pbx_b)`
- `telecom.run_smoke_test(pbx_id)`
- `telecom.run_playbook(name, pbx_id?, endpoint?, pbx_a?, pbx_b?, params?)`
- `telecom.run_smoke_suite(name, pbx_id, params?)`
- `telecom.baseline_create(pbx_id, baseline_id?)`
- `telecom.baseline_show(baseline_id)`
- `telecom.audit_target(pbx_id, baseline_id?)`
- `telecom.drift_target_vs_baseline(pbx_id, baseline_id)`
- `telecom.drift_compare_targets(pbx_a, pbx_b)`
- `telecom.audit_report(pbx_id, baseline_id?)`
- `telecom.audit_export(pbx_id, format?, baseline_id?)`
- `telecom.scorecard_target(pbx_id)`
- `telecom.scorecard_cluster(cluster_id, pbx_ids)`
- `telecom.scorecard_environment(environment_id, pbx_ids?)`
- `telecom.scorecard_compare(entity_a, entity_b, entity_type?, pbx_ids_a?, pbx_ids_b?)`
- `telecom.scorecard_trend(entity_type, entity_id, window?)`
- `telecom.scorecard_export(entity_type, entity_id, format?, pbx_ids?)`
- `telecom.capture_incident_evidence(pbx_id)`
- `telecom.generate_evidence_pack(pbx_id, incident_type?, incident_id?, collector?, collection_mode?)`
- `telecom.reconstruct_incident_timeline(pack_id)`
- `telecom.export_evidence_pack(pack_id, format?)`
- `telecom.list_probes()`
- `telecom.run_probe(name, pbx_id, params?)`
- `telecom.list_chaos_scenarios()`
- `telecom.run_chaos_scenario(name, pbx_id, params?)`
- `telecom.list_self_healing_policies()`
- `telecom.evaluate_self_healing(pbx_id, context?)`
- `telecom.run_self_healing_policy(name, pbx_id, params?)`
- `telecom.assert_state(pbx_id, assertion, params?)`
- `telecom.run_registration_probe(pbx_id, destination, reason, change_ticket, timeout_s?, confirm_token?)` (mode-gated write)
- `telecom.run_trunk_probe(pbx_id, destination, reason, change_ticket, timeout_s?, confirm_token?)` (mode-gated write)
- `telecom.verify_cleanup(pbx_id, probe_id?)`

## asterisk.*

- `asterisk.health(pbx_id)`
- `asterisk.pjsip_show_endpoint(pbx_id, endpoint)`
- `asterisk.pjsip_show_endpoints(pbx_id, filter?, limit?)`
- `asterisk.pjsip_show_registration(pbx_id, registration)`
- `asterisk.pjsip_show_contacts(pbx_id, filter?, limit?)`
- `asterisk.active_channels(pbx_id, filter?, limit?)`
- `asterisk.bridges(pbx_id, limit?)`
- `asterisk.channel_details(pbx_id, channel_id)`
- `asterisk.core_show_channel(pbx_id, channel_id)`
- `asterisk.version(pbx_id)`
- `asterisk.modules(pbx_id)`
- `asterisk.logs(pbx_id, grep?, tail?, level?)`
- `asterisk.cli(pbx_id, command)` (read-only allowlisted commands)
- `asterisk.originate_probe(pbx_id, destination, reason, change_ticket, timeout_s?, confirm_token?)` (mode-gated write)
- `asterisk.reload_pjsip(pbx_id, reason, change_ticket, confirm_token?)` (mode-gated write)

## freeswitch.*

- `freeswitch.health(pbx_id)`
- `freeswitch.sofia_status(pbx_id, profile?)`
- `freeswitch.registrations(pbx_id, profile?, limit?)`
- `freeswitch.gateway_status(pbx_id, gateway)`
- `freeswitch.channels(pbx_id, limit?)`
- `freeswitch.calls(pbx_id, limit?)`
- `freeswitch.channel_details(pbx_id, uuid)`
- `freeswitch.version(pbx_id)`
- `freeswitch.modules(pbx_id)`
- `freeswitch.logs(pbx_id, grep?, tail?, level?)`
- `freeswitch.api(pbx_id, command)` (read-only allowlisted commands)
- `freeswitch.originate_probe(pbx_id, destination, reason, change_ticket, timeout_s?, confirm_token?)` (mode-gated write)
- `freeswitch.reloadxml(pbx_id, reason, change_ticket, confirm_token?)` (mode-gated write)
- `freeswitch.sofia_profile_rescan(pbx_id, profile, reason, change_ticket, confirm_token?)` (mode-gated write)

## Contract notes

- `telecom.healthcheck` is part of the exported catalog as an additive runtime diagnostics tool.
- `telecom.run_playbook` supports:
  - `sip_registration_triage`
  - `outbound_call_failure_triage`
  - `inbound_delivery_triage`
  - `orphan_channel_triage`
  - `pbx_drift_comparison`
- `telecom.run_smoke_suite` supports:
  - `baseline_read_only_smoke`
  - `registration_visibility_smoke`
  - `call_state_visibility_smoke`
  - `audit_baseline_smoke`
  - `active_validation_smoke` (mode-gated and probe-gated)
- Channel inventory now uses canonical `channel_id` across platforms.
- `freeswitch.channels` keeps `uuid` for backward compatibility and also returns `channel_id`.
- `asterisk.active_channels` and `asterisk.pjsip_show_endpoints` now reject unknown `filter` keys with `VALIDATION_ERROR`.
- Write tools (`asterisk.reload_pjsip`, `freeswitch.reloadxml`, `freeswitch.sofia_profile_rescan`) require `reason` and `change_ticket`, and may require `confirm_token` when `TELECOM_MCP_CONFIRM_TOKEN` is set.
- Active probe tools (`telecom.run_registration_probe`, `telecom.run_trunk_probe`, `asterisk.originate_probe`, `freeswitch.originate_probe`) additionally require `TELECOM_MCP_ENABLE_ACTIVE_PROBES=1`.
- Optional probe hardening env vars:
  - `TELECOM_MCP_PROBE_MAX_PER_MINUTE` (default `5`)
  - `TELECOM_MCP_PROBE_MAX_TIMEOUT_S` (caps requested probe timeout)
- Module posture policy env vars:
  - `TELECOM_MCP_CRITICAL_MODULES` (comma-separated module names overriding platform defaults)
  - `TELECOM_MCP_RISKY_MODULE_PATTERNS` (comma-separated lowercase substring patterns)
- `telecom.compare_targets` now includes semantic `drift_categories` (for example `critical_modules_missing`, `risky_modules_loaded`, `connector_coverage`, `version_mismatch`).
