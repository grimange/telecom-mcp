# Changelog

## Unreleased

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
