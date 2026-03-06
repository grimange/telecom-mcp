# Input Audit Selection

## selected audit set
- Selected set: `docs/audit/production-readiness-expanded-capabilities/20260306T134250Z--*`
- Reason: newest complete set containing all required artifacts.

## normalized findings list
- `SEC-01` / `RSG-01` (Critical): evidence export returned raw pack payload without export-time redaction or bounds.
- `SEC-02` / `RSG-02` (High): active-flow eligibility relied on `tags`/`validation_safe` and optional untagged bypass, mismatched with config model.
- `SEC-03` (High): environment rollups/promotion did not enforce target membership in requested environment.
- `SEC-04` (Medium): connectors lacked bounded retry/backoff for transient failures.
- `SEC-05` (Medium): scorecard/release/evidence history remained in-memory only.
- `OP-02` (Batch C): docs lacked one authoritative mode x capability x environment matrix.
- `OP-04` / `TEST-02` (Batch C): MCP parity skip should be release-gated.
- `OP-01` / `TEST-03` (Batch D): richer governance UX and presets.

## dependencies
- `SEC-02` precedes gating tests for probe/chaos/self-healing.
- `SEC-03` depends on canonical target environment handling in `config.py`.
- `SEC-05` persistence wiring must land before persistence tests/reload validation.
- Docs updates depend on final behavior after A/B code changes.

## deferred findings
- Deferred by policy (post A/B): `OP-01`, `OP-04`, `TEST-02`, `TEST-03`.
- In-scope now: `SEC-01`..`SEC-05`, `RSG-01`, `RSG-02`, plus operator matrix documentation (`OP-02` subset).

## remediation assumptions
- Safety overrides convenience: fail-closed eligibility for active flows.
- Persistence backend is local filesystem JSON state in `TELECOM_MCP_STATE_DIR`.
- Existing MCP dependency skip remains open and documented as remaining blocker for stricter release profile.
