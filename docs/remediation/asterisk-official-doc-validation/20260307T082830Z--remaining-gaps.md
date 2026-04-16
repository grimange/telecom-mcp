# Remaining Gaps

## Unresolved Findings

### DR-005
- Status: `deferred`
- Severity: Medium
- Issue: Dialplan `Dial()` / `Stasis()` and ARI lifecycle semantics remain unverified by runtime evidence.
- Why unresolved: this run focused on code-level doc drift remediation and regression validation; no dialplan/websocket evidence inputs were added.
- Recommended next pipeline: `02--validate-live-asterisk-targets-against-official-docs-base-contracts.md`.

## Environment Gaps

- Live target evidence capture is needed to fully close runtime-proof requirements for docs-aligned lifecycle behavior.
