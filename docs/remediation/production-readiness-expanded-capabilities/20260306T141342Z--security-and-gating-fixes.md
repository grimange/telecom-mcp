# Security And Gating Fixes

## Findings addressed
- Addressed `PRR-SEC-001` / `PRR-RUN-001` by adding fail-closed lab-safe checks to:
  - `telecom.run_registration_probe`
  - `telecom.run_trunk_probe`
- Addressed `PRR-SEC-002` by adding defense-in-depth eligibility checks to:
  - `asterisk.originate_probe`
  - `freeswitch.originate_probe`
- Addressed `PRR-SEC-003` by adding deterministic policy mapping provenance:
  - `mapping_revision`
  - `mapping_schema`
  - `mapping_checksum`
- Addressed `PRR-SEC-005` by surfacing non-fatal state persistence failures as runtime warnings.

## Code areas changed
- `src/telecom_mcp/tools/telecom.py`
- `src/telecom_mcp/tools/asterisk.py`
- `src/telecom_mcp/tools/freeswitch.py`
- `src/telecom_mcp/scorecard_policy_inputs/mapping.py`
- `src/telecom_mcp/scorecard_policy_inputs/engine.py`

## Hardening improvements
- Active probe wrappers now require explicit lab-safe target metadata before delegating active execution.
- Platform originate tools independently enforce the same target eligibility constraints.
- Mapping outputs now carry deterministic governance provenance suitable for drift tracking.
- State persistence failures are still non-fatal for runtime continuity but no longer silent.

## Residual risks
- Batch C and D findings are still open (operator UX consolidation and post-pilot analytics maturity).
- Persistence warnings are surfaced in payload warnings; no dedicated metric sink was added in this run.

## Intentionally deferred issues
- `PRR-OPS-001`
- `PRR-OBS-001`
- `PRR-IMP-001`
- `PRR-IMP-002`
