# Documentation Alignment Audit

- Timestamp (UTC): 2026-03-06T09:30:43Z

## Repository Docs (local)

- `CHANGELOG.md` includes `0.1.4`.
- `README.md` remains aligned with behavior.
- `docs/release/RELEASING.md` includes tag/version safeguards.

## Published Tag Docs (remote)

- `CHANGELOG.md` at `v0.1.4` does not include `0.1.4` section.

## Finding

Documentation at published tag is inconsistent with release identity and local release-prepared state.

## Severity

Critical (public release can mislead users about actual source version).
