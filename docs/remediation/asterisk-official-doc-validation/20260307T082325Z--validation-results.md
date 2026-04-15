# Validation Results

## Tests Run

Command:

```bash
pytest -q tests/test_connectors.py tests/test_expansion_batch2_tools.py tests/test_remediation_hardening.py tests/test_mcp_server_stage10.py tests/test_tools_contract_smoke.py
```

Result:
- Pass: `103`
- Fail: `0`

## Evidence Collected

- New regression test validates fragmented AMI command output handling:
  - `tests/test_connectors.py::test_ami_send_action_reads_fragmented_command_output`
- Updated regression test validates documented `CoreShowChannels` usage for channel details:
  - `tests/test_expansion_batch2_tools.py::test_asterisk_core_show_channel_uses_ami`
- New regression tests validate:
  - plural registration action contract
  - empty-contact normalization path

## Runtime Validation

- Live MCP runtime probes were executed after code changes, but responses still reflected pre-remediation behavior (`PJSIPShowRegistrationOutbound`, `CoreShowChannel`, `No Contacts found` as hard error).
- Interpretation: running telecom MCP endpoint appears to be on an older build; runtime evidence is environment-limited for this remediation run.

## Remaining Uncertainty

- Post-fix live-target verification requires deploying/restarting the MCP runtime with this code revision.
