# Changelog

## Unreleased

### Added

- Added `freeswitch.inbound_esl_sessions` for bounded inspect-mode discovery of inbound ESL management sessions.
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
- Extended release-gating pipeline (Batch 2):
  - added MCP/core tool `telecom.release_gate_decision`
  - integrated release-gate decision evidence into incident evidence collection/timeline
  - added tool/wrapper contract coverage for release-gate invocation
- Extended release-gating pipeline (Batch 3):
  - added environment promotion tool `telecom.release_promotion_decision`
  - added release-gate history analytics tool `telecom.release_gate_history`
  - added in-memory release-gate history tracking and trend rollups
- Added policy registry with bounded low-risk and escalate-only policy classes.
- Added centralized remediation gating, retry/cooldown tracking, verification, and escalation evidence hooks.
- Added stage-03 self-healing tests for policy discovery, eligibility evaluation, gated blocking, and successful bounded execution.
- Added production-readiness remediation hardening for expanded capabilities:
  - export-time evidence-pack redaction and bounded export scope
  - explicit target eligibility metadata (`environment`, `safety_tier`, `allow_active_validation`) for active frameworks
  - environment membership enforcement for environment scorecards and release promotion decisions
  - connector retry/backoff on transient AMI/ARI/ESL failures
  - durable state persistence for scorecard history, release-gate history, and evidence packs
  - remediation-focused tests for redaction, gating, membership checks, retries, and persistence
- Added production-readiness remediation follow-up hardening:
  - fail-closed lab-safe eligibility checks in `telecom.run_registration_probe` and `telecom.run_trunk_probe`
  - defense-in-depth lab-safe eligibility checks in `asterisk.originate_probe` and `freeswitch.originate_probe`
  - deterministic scorecard-policy mapping provenance fields (`mapping_revision`, `mapping_schema`, `mapping_checksum`)
  - surfaced non-fatal state persistence failures as runtime warnings in scorecard/release/evidence flows
  - regression tests for direct wrapper denial paths, platform originate denial paths, mapping metadata, and persistence warning observability
- Added expanded-capability remediation hardening for authenticated caller and governance durability:
  - authenticated caller boundary for request dispatch (`TELECOM_MCP_REQUIRE_AUTHENTICATED_CALLER`, `TELECOM_MCP_AUTH_TOKEN`, `TELECOM_MCP_ALLOWED_CALLERS`)
  - principal/auth context in audit records (`principal`, `principal_authenticated`, `auth_scheme`)
  - persisted baseline/probe/self-healing coordination state under `TELECOM_MCP_STATE_DIR`
  - strict fail-closed persistence profile for critical governance artifacts (`TELECOM_MCP_STRICT_STATE_PERSISTENCE=1`)
  - startup target metadata policy enforcement profile (`TELECOM_MCP_ENFORCE_TARGET_POLICY=1`)
  - remediation tests for auth boundary, strict persistence denial, metadata policy denial, and self-heal state persistence
  - fail-closed delegated probe wrapper behavior (`telecom.run_registration_probe`, `telecom.run_trunk_probe`) with delegated error propagation
  - production runtime bootstrap profile (`TELECOM_MCP_RUNTIME_PROFILE=production`) requiring auth, strict persistence, and target-policy enforcement
- Added hardened default runtime dispatch posture:
  - non-lab profiles default capability classes to `observability` when `TELECOM_MCP_ALLOWED_CAPABILITY_CLASSES` is unset
  - authenticated caller policy defaults on outside explicit lab/test profiles
  - MCP SDK healthcheck now reports effective caller-auth policy
  - added regression tests for default capability-class denial and default caller-auth requirement
- Added Batch A/B remediation hardening for expanded-capability production-readiness findings:
  - active orchestration write-intent propagation for `active_validation_smoke` and class C probe active routes (`reason`, `change_ticket`, optional `confirm_token`)
  - explicit `change_ticket` requirement for write-capable self-healing policies (`safe_sip_reload_refresh`, `gateway_profile_rescan`)
  - strict destination validation in direct vendor originate tools (`asterisk.originate_probe`, `freeswitch.originate_probe`)
  - integration and negative-path tests for active orchestration contract continuity and direct originate input rejection
- Added Batch C/D remediation follow-up hardening:
  - first-class capability-class policy metadata in dispatch (`observability`, `validation`, `chaos`, `remediation`, `export`) with optional runtime allow policy (`TELECOM_MCP_ALLOWED_CAPABILITY_CLASSES`)
  - internal delegated subcall contract-failure taxonomy metrics and `failed_sources[*].contract_failure_reason` annotations
  - additional non-mocked delegated orchestration integration coverage through real `execute_tool` routing (`telecom.run_probe` -> `telecom.run_registration_probe` -> delegated vendor tool)
- Added expanded remediation hardening follow-up:
  - production runtime profile now requires explicit `TELECOM_MCP_ALLOWED_CAPABILITY_CLASSES` including `observability`
  - startup warning for write-capable runtime when capability-class policy env is unset (`CAPABILITY_CLASS_POLICY_UNSET`)
  - operator runbook taxonomy mapping for delegated `contract_failure_reason` triage
  - CI now runs MCP initialize transport tests explicitly (`tests/test_mcp_stdio_initialize.py`)
- Added structural root-cause eliminator shared control-plane modules:
  - `src/telecom_mcp/safety/policy.py` for centralized active-target eligibility and probe destination validation
  - `src/telecom_mcp/execution/active_control.py` for shared active-operation concurrency controls
- Added structural recurrence-prevention tests:
  - `tests/test_safety_policy.py`
  - shared active concurrency coverage in `tests/test_expansion_batch4_tools.py`
- Added hardened-profile startup safeguards:
  - `TELECOM_MCP_RUNTIME_PROFILE=pilot` now enforces the same mandatory hardening controls as production/prod
  - `TELECOM_MCP_ALLOWED_CAPABILITY_CLASSES` containing `chaos`/`remediation` now requires explicit approval via `TELECOM_MCP_ENABLE_HIGH_RISK_CAPABILITY_CLASSES=1`
  - config tests for pilot hardening and high-risk capability-class approval checks

### Changed

- Updated FreeSWITCH inbound ESL session posture to be explicit and non-misleading:
  - `freeswitch.drop_inbound_esl_session` remains a high-friction placeholder and now reports `unsupported_current_posture` consistently instead of implying latent operability
  - `freeswitch.capabilities` now reports inbound ESL discovery as supported and exact one-session disconnect as unsupported in the current connector/server posture
  - README/tool-spec/docs wording now makes the supported discovery vs unsupported disconnect distinction explicit
- Restored missing readiness prompt artifacts so the full test suite runs cleanly again.
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
- Updated telecom/vendor active paths to consume shared control-plane safety modules:
  - `telecom.run_registration_probe`, `telecom.run_trunk_probe`
  - `telecom.run_probe` (class C), `telecom.run_chaos_scenario` (lab mode), `telecom.run_self_healing_policy` (active/remediation policies)
  - `asterisk.originate_probe`, `freeswitch.originate_probe`
- Updated docs for shared control-plane posture and active concurrency tuning:
  - `README.md`
  - `docs/security.md`
  - `docs/runbook.md`
  - `docs/telecom-mcp-implementation-plan.md`

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
