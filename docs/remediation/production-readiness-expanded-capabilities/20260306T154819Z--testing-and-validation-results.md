# Testing and Validation Results

## tests added
- `tests/test_config.py::test_production_profile_rejects_invalid_capability_classes`
- `tests/test_mcp_server_stage10.py::test_write_mode_warns_when_capability_class_policy_unset`

## tests updated
- `tests/test_config.py::test_production_profile_accepts_when_hardening_controls_enabled`
  - now sets `TELECOM_MCP_ALLOWED_CAPABILITY_CLASSES`

## negative-path coverage added
- production profile denial when capability class env is invalid.
- startup warning coverage for write-capable mode with unset class policy env.

## remaining blind spots
- current default interpreter still skips MCP initialize tests if optional `mcp` dependency is absent.
- this is mitigated by explicit CI step and `.venv` validation evidence.

## validation summary
- `pytest -ra` -> `225 passed, 2 skipped in 1.11s`
- `.venv/bin/pytest -ra tests/test_mcp_stdio_initialize.py` -> `2 passed in 1.07s`
- targeted suite:
  - `pytest -q tests/test_config.py tests/test_mcp_server_stage10.py tests/test_mcp_stdio_initialize.py` -> all passed with expected `mcp` skips in non-aligned interpreter
