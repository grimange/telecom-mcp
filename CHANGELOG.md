# Changelog

## Unreleased

### Added

- Added Batch 1 capability-expansion tools:
  - `telecom.endpoints`, `telecom.registrations`, `telecom.channels`, `telecom.calls`, `telecom.logs`, `telecom.inventory`
  - `asterisk.pjsip_show_contacts`, `asterisk.version`, `asterisk.logs`
  - `freeswitch.version`, `freeswitch.logs`
- Added optional per-target `logs` configuration in `targets.yaml` (`path`, `source_command`) for bounded read-only log access.
- Added tests for Batch 1 tool behavior and MCP wrapper argument coercion.
- Added Batch 2 troubleshooting tools:
  - `telecom.diff_snapshots`
  - `asterisk.cli`, `asterisk.core_show_channel`
  - `freeswitch.api`, `freeswitch.channel_details`
- Added Batch 2 tests for command allowlists, channel details parsing, and snapshot diff behavior.
- Added Batch 3 auditing and drift tools:
  - `telecom.compare_targets`
  - enriched `telecom.inventory` with normalized `baseline` and `posture` sections.
- Added Batch 3 tests for inventory posture fields and cross-target comparison drift output.
- Added Batch 4 validation tools:
  - `telecom.run_smoke_test`, `telecom.assert_state`, `telecom.verify_cleanup`
  - `telecom.run_registration_probe`, `telecom.run_trunk_probe`
  - `asterisk.originate_probe`, `freeswitch.originate_probe`
- Added explicit active-probe runtime guard (`TELECOM_MCP_ENABLE_ACTIVE_PROBES=1`) for originate probe execution.
- Added Batch 4 tests for smoke/assert helpers, probe guardrails, and cleanup verification.
- Hardened probe execution:
  - destination allow-pattern validation
  - per-target probe rate limiting (`TELECOM_MCP_PROBE_MAX_PER_MINUTE`)
  - probe timeout cap (`TELECOM_MCP_PROBE_MAX_TIMEOUT_S`)
  - probe-ID tracking and `telecom.verify_cleanup(pbx_id, probe_id?)` correlation.
- Added module inventory tools:
  - `asterisk.modules`
  - `freeswitch.modules`
- Enriched `telecom.inventory` module posture with live module counts/samples from vendor module tools.
- Added module posture policy evaluation:
  - critical-module missing detection
  - risky-module loaded detection
  - env override knobs (`TELECOM_MCP_CRITICAL_MODULES`, `TELECOM_MCP_RISKY_MODULE_PATTERNS`)
- Enriched `telecom.compare_targets` with semantic drift categories:
  - `critical_modules_missing`, `risky_modules_loaded`, `connector_coverage`, `version_mismatch`.
- Added Stage-02 troubleshooting workflow framework:
  - `telecom.run_playbook`
  - `telecom.run_smoke_suite`
- Added mandatory playbooks:
  - `sip_registration_triage`, `outbound_call_failure_triage`, `inbound_delivery_triage`, `orphan_channel_triage`, `pbx_drift_comparison`
- Added mandatory smoke suites:
  - `baseline_read_only_smoke`, `registration_visibility_smoke`, `call_state_visibility_smoke`, `audit_baseline_smoke`
- Added optional gated smoke suite:
  - `active_validation_smoke` (blocked in inspect/plan mode and requires active-probe enablement)
- Added stage-02 tests for playbook/suite result contracts and safety gating.
- Added Stage-03 telecom audit baseline and drift tooling:
  - `telecom.baseline_create`, `telecom.baseline_show`
  - `telecom.audit_target`, `telecom.audit_report`, `telecom.audit_export`
  - `telecom.drift_target_vs_baseline`, `telecom.drift_compare_targets`
- Added baseline policy catalog, drift classification, and audit scoring model in tool implementation.
- Added stage-03 tests for baseline creation/show, policy scoring, drift, and report/export behavior.
- Added Stage-03 resilience scorecard tooling:
  - `telecom.scorecard_target`
  - `telecom.scorecard_cluster`
  - `telecom.scorecard_environment`
  - `telecom.scorecard_compare`
  - `telecom.scorecard_trend`
  - `telecom.scorecard_export`
- Added explainable dimension scoring, confidence overlays, and local trend tracking for scorecards.
- Added stage-03 scorecard tests for PBX/cluster/environment rollups, comparison, trend, and export behavior.
- Added Stage-03 incident evidence tooling:
  - `telecom.capture_incident_evidence`
  - `telecom.generate_evidence_pack`
  - `telecom.reconstruct_incident_timeline`
  - `telecom.export_evidence_pack`
- Added structured evidence item hashing, incident pack integrity hash generation, and timeline reconstruction.
- Added stage-03 incident evidence tests for capture, pack generation, timeline, and export formats.
- Added Stage-03 gated active validation probe framework:
  - `telecom.list_probes`
  - `telecom.run_probe`
- Added probe catalog covering passive and active validation classes:
  - registration visibility
  - endpoint reachability
  - outbound trunk
  - controlled originate
  - bridge formation
  - cleanup verification
  - observability query
  - post-change validation suite
- Added centralized probe gating evaluation, phased probe execution, and post-probe smoke/audit linkage.
- Added stage-03 probe suite tests for gating, passive probe execution, active probe enforcement, and post-change suite behavior.
- Added Stage-03 chaos scenario framework:
  - `telecom.list_chaos_scenarios`
  - `telecom.run_chaos_scenario`
- Added chaos scenario catalog with fixture-first and lab-gated scenarios:
  - registration loss, registration flapping, trunk outage, orphan channel accumulation, stuck bridge, module failure, observability degradation, fixture drift injection
- Added centralized chaos gating, phased scenario execution, detection linkage (playbooks/smoke/audit), and rollback verification.
- Added stage-03 chaos framework tests for fixture execution, lab gating enforcement, and scenario discovery.
- Added Stage-03 self-healing policy engine:
  - `telecom.list_self_healing_policies`
  - `telecom.evaluate_self_healing`
  - `telecom.run_self_healing_policy`
- Added Stage-03 scorecard-driven self-healing policy input framework:
  - `telecom.scorecard_policy_inputs`
  - scorecard confidence/freshness-aware mapping and ranking engine
  - scorecard policy handoff integration into `telecom.evaluate_self_healing`
- Started release-gating follow-up pipeline (Batch 1):
  - added `telecom_mcp.release_gates.evaluate_release_gate`
  - added unit tests in `tests/test_release_gates.py`
  - added release-gate design artifacts under `docs/release/scorecard-release-gates/`
- Added policy registry with bounded low-risk and escalate-only policy classes.
- Added centralized remediation gating, retry/cooldown tracking, verification, and escalation evidence hooks.
- Added stage-03 self-healing tests for policy discovery, eligibility evaluation, gated blocking, and successful bounded execution.

### Changed

- Updated README/docs tool catalog and examples to include vendor-neutral workflow expansion and log collection patterns.
- Updated MCP server tool catalogs and wrappers to expose `telecom.run_playbook` and `telecom.run_smoke_suite`.
- Updated MCP server tool catalogs and wrappers to expose telecom audit baseline/drift tools.
- Updated MCP server tool catalogs and wrappers to expose resilience scorecard tools.
- Updated MCP server tool catalogs and wrappers to expose incident evidence pack tools.
- Updated MCP server tool catalogs and wrappers to expose probe catalog/runner tools.
- Updated MCP server tool catalogs and wrappers to expose chaos catalog/runner tools.
- Updated MCP server tool catalogs and wrappers to expose self-healing policy tools.
- Updated MCP SDK wrappers and preflight tool-availability map to expose new Batch 2 tools.
- Updated MCP SDK wrappers/docs/examples to expose `telecom.compare_targets`.
- Updated MCP SDK wrappers/docs/examples to expose Batch 4 tools and write-intent arguments for probe operations.

## 0.1.4 - 2026-03-06

### Added

- Added release artifact traceability via checksum manifest generation in the release workflow.

### Changed

- Hardened release automation to validate tag/version identity before publishing.
- Added package metadata validation (`twine check dist/*`) to CI and release workflows.
- Updated `docs/release/RELEASING.md` to document preflight and version/tag verification steps.

## 0.1.3 - 2026-03-06

- Re-ran Stage-02 production-readiness pipeline and generated a fresh timestamped report set at `docs/audit/production-readiness/20260306-063351/`.
- Added updated scorecard/findings/evidence, release checklist/notes, incident playbooks, SBOM, and remediation re-run notes.

## 0.1.2 - 2026-03-04

- Implemented full v1 tool registry parity with `docs/telecom-mcp-tool-specification.md`.
- Added write-tool policy enforcement: mode gate + allowlist + cooldown.
- Added safe write tools:
  - `asterisk.reload_pjsip`
  - `freeswitch.reloadxml`
  - `freeswitch.sofia_profile_rescan`
- Added missing read tools:
  - `asterisk.pjsip_show_registration`, `asterisk.bridges`, `asterisk.channel_details`
  - `freeswitch.registrations`, `freeswitch.gateway_status`, `freeswitch.calls`
- Improved CLI startup behavior: typed, user-friendly startup errors without traceback.
- Pinned dev dependencies in `pyproject.toml`.

## 0.1.1 - 2026-03-04

- Added production-readiness audit artifacts pipeline output under `docs/audit/production-readiness/`.
- Fixed failing test path for ARI connector config construction.
- Improved audit logger handler behavior for deterministic stderr capture in tests.
- Fixed mypy/ruff issues in tool argument parsing and tests.
- Added release-readiness artifact docs (`release-checklist`, draft release notes, incident playbooks, perf benchmark output).
