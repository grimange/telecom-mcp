# Release Checklist

- [x] `python -m telecom_mcp` entrypoint exists and starts with example config.
- [x] Config file missing-path error is typed (`VALIDATION_ERROR`), but currently surfaces as traceback in CLI startup.
- [x] `pytest`, `ruff`, `mypy` evidence collected.
- [x] SBOM exported (`sbom/cyclonedx.json`).
- [x] Dependency vulnerability scan generated (`evidence/deps-vuln.txt`).
- [x] Contract diff generated (`evidence/contract-tool-diff.json`).
- [ ] Missing spec-defined tools implemented (see findings).
- [ ] Dependency vulnerabilities remediated in execution environment.
