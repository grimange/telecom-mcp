# PRR Remediation Batch

## Executed
- [x] Add all missing v1 spec tools to server registry and tool modules.
- [x] Add write-tool policy gates (allowlist + cooldown).
- [x] Add tests for mode/allowlist/cooldown behavior.
- [x] Add user-friendly startup error handling.
- [x] Pin dev dependencies in `pyproject.toml`.
- [x] Re-run production-readiness phases and regenerate artifacts.

## Remaining
- [ ] Investigate host-specific `black --check` timeout behavior in CI runtime.
