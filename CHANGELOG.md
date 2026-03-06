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

### Changed

- Updated README/docs tool catalog and examples to include vendor-neutral workflow expansion and log collection patterns.
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
