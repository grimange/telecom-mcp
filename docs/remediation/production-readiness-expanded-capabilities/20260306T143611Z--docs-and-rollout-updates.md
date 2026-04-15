# Docs And Rollout Updates

## Files updated
- `README.md`
- `docs/security.md`
- `docs/runbook.md`
- `CHANGELOG.md`

## Behavior clarified
- Probe wrapper success semantics now require delegated originate success.
- Production profile bootstrap requirements are now explicit and documented.
- Hardened caller/target-policy/strict-persistence controls are documented as production-profile requirements.

## Rollout changes
- Added explicit production bootstrap profile:
  - `TELECOM_MCP_RUNTIME_PROFILE=production`
  - requires caller auth, strict persistence, target policy enforcement, and auth token.
- Active wrapper execution semantics are now strict fail-closed for delegated failures.

## Operator guidance added
- README hardening env block includes production profile toggle.
- Security docs include production-profile required controls.
- Runbook includes production-profile startup requirement checklist.

## Remaining documentation gaps
- Extended redaction edge-case runbook guidance (Batch C)
- deeper multi-runner/state-backend guidance beyond file-backed coordination
