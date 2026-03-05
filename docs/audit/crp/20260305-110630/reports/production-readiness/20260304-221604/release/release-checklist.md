# Release Checklist

- [x] Tool registry matches documented v1 tool catalog.
- [x] Envelope and standard error contracts validated by tests.
- [x] Write tools are disabled by default (`inspect`) and require `execute_safe` plus allowlist/cooldown.
- [x] `pytest`, `ruff`, `mypy` pass.
- [x] Startup errors are typed/user-friendly (`startup_error code=...`).
- [x] Timestamped PRR artifacts generated.
- [x] SBOM generated for pinned project tooling dependencies.
- [ ] Black check command in this host intermittently exits via timeout despite reporting no file changes.
