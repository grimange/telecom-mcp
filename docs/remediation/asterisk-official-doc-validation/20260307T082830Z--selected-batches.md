# Selected Batches

- Remediation run timestamp: `20260307T082830Z`
- Consumed audit set: `20260307T081209Z` from `docs/audit/asterisk-official-doc-validation/`

## Batch Selection

### B1
- Batch id: `B1-high-ami-contract-actions`
- Linked findings: `DR-001`, `DR-002`
- Rationale: production-impacting action-name and contract mismatches on AMI paths.
- Dependencies: AMI event-list parsing/selection behavior.
- Expected files to change (already remediated in workspace):
  - `src/telecom_mcp/tools/asterisk.py`
  - `src/telecom_mcp/normalize/asterisk.py`
  - `tests/test_expansion_batch2_tools.py`
  - `tests/test_remediation_hardening.py`

### B2
- Batch id: `B2-high-ami-command-framing`
- Linked findings: `DR-003`
- Rationale: command wrappers must reliably consume multi-frame AMI `Command` output.
- Dependencies: connector response completion and parsing heuristics.
- Expected files to change (already remediated in workspace):
  - `src/telecom_mcp/connectors/asterisk_ami.py`
  - `src/telecom_mcp/tools/asterisk.py`
  - `tests/test_connectors.py`

### B3
- Batch id: `B3-medium-pjsip-empty-contacts`
- Linked findings: `DR-004`
- Rationale: avoid false-hard-failure for documented/observed empty-contact outcomes.
- Dependencies: none.
- Expected files to change (already remediated in workspace):
  - `src/telecom_mcp/tools/asterisk.py`
  - `docs/tools.md`
  - `tests/test_remediation_hardening.py`

### B4
- Batch id: `B4-medium-local-contract-docs`
- Linked findings: local dual-plane health contract clarification
- Rationale: make local override explicit for operators and agents.
- Dependencies: none.
- Expected files to change (already remediated in workspace):
  - `docs/tools.md`
  - `src/telecom_mcp/mcp_server/server.py`
