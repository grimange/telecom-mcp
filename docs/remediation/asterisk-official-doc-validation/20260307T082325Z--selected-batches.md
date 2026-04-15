# Selected Batches

- Remediation run timestamp: `20260307T082325Z`
- Consumed audit set: `20260307T081209Z` from `docs/audit/asterisk-official-doc-validation/`

## Batch Selection

### B1
- Batch id: `B1-high-ami-contract-actions`
- Linked findings: `DR-001`, `DR-002`
- Rationale: high-risk contract mismatches producing runtime failures on Asterisk 22.5.2.
- Dependencies: AMI event parsing utilities.
- Expected files:
  - `src/telecom_mcp/tools/asterisk.py`
  - `src/telecom_mcp/normalize/asterisk.py`
  - tests for AMI action contract behavior.

### B2
- Batch id: `B2-high-ami-command-framing`
- Linked findings: `DR-003`
- Rationale: command wrappers (`asterisk.modules`, `asterisk.cli`) require deterministic parser behavior.
- Dependencies: AMI socket response completion logic.
- Expected files:
  - `src/telecom_mcp/connectors/asterisk_ami.py`
  - `src/telecom_mcp/tools/asterisk.py`
  - `tests/test_connectors.py`

### B3
- Batch id: `B3-medium-pjsip-empty-contacts`
- Linked findings: `DR-004`
- Rationale: avoid false negative error on valid empty-contact state.
- Dependencies: none.
- Expected files:
  - `src/telecom_mcp/tools/asterisk.py`
  - `tests/test_remediation_hardening.py`
  - `docs/tools.md`

### B4
- Batch id: `B4-medium-local-contract-docs`
- Linked findings: local contract override for dual-plane health requirement.
- Rationale: explicit documentation of intentional behavior.
- Dependencies: none.
- Expected files:
  - `docs/tools.md`
  - `src/telecom_mcp/mcp_server/server.py` (tool description clarity).
