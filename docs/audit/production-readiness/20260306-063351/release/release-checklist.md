# Release Checklist

- [x] Tool registry matches documented v1 tool catalog.
- [x] Envelope and standard error contracts validated by tests.
- [x] Write tools disabled by default (`inspect`) and guarded by `execute_safe` + allowlist + cooldown.
- [x] `mypy`, `ruff`, and `pytest` quality gates are clean.
- [x] Startup errors are typed/user-friendly (`startup_error code=...`).
- [x] Timestamped PRR artifacts generated.
- [x] SBOM generated (`sbom/cyclonedx.json`, `sbom/pip-freeze.txt`).
- [x] Runbook artifacts present for core incident classes.
- [ ] Host-level `black --check .` timeout behavior investigated (non-blocking).
