# Security And Gating Fixes

## Findings addressed
- Addressed `F-SEC-001` / `F-RT-001`:
  - `telecom.run_registration_probe` and `telecom.run_trunk_probe` now fail closed on delegated originate failures.
  - Delegated write intent metadata (`reason`, `change_ticket`, optional `confirm_token`) is forwarded to delegated originate tools.
  - Wrapper errors now surface delegated failure details (`delegated_tool`, `failed_sources`).
- Addressed `G-TEST-001`:
  - Added full dispatch-chain tests validating delegated-write deny/success behavior.
- Addressed `F-SEC-002` / `F-SEC-003` / `F-SEC-004`:
  - Added production bootstrap profile gate: `TELECOM_MCP_RUNTIME_PROFILE=production`.
  - Production profile now requires:
    - `TELECOM_MCP_REQUIRE_AUTHENTICATED_CALLER=1`
    - `TELECOM_MCP_ENFORCE_TARGET_POLICY=1`
    - `TELECOM_MCP_STRICT_STATE_PERSISTENCE=1`
    - non-empty `TELECOM_MCP_AUTH_TOKEN`

## Code areas changed
- `src/telecom_mcp/tools/telecom.py`
- `src/telecom_mcp/config.py`
- `tests/test_expansion_batch4_tools.py`
- `tests/test_tools_contract_smoke.py`
- `tests/test_config.py`

## Hardening improvements
- Active wrapper signal integrity is fail-closed and deterministic.
- Production profile startup is now explicitly hardened and cannot boot with missing critical controls.
- Delegated-write path now aligns with write-intent and confirm-token policies.

## Residual risks
- `F-SEC-005` redaction remains pattern-based and may require broader key-shape coverage.
- `G-TEST-002` still has partial mocked-path usage in non-remediated test slices.

## Intentionally deferred issues
- `F-SEC-005` (Batch C)
- `G-TEST-002` (Batch C)
