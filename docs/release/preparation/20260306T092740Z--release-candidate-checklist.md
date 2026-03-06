# Release Candidate Checklist

- Timestamp (UTC): 2026-03-06T09:27:40Z
- Candidate status: **BLOCKED**

## Completed

- [x] Repository discovery complete
- [x] Packaging/test/metadata checks completed
- [x] Changelog reviewed and aligned to `0.1.3`
- [x] README reviewed
- [x] Release guide improved (`docs/release/RELEASING.md`)
- [x] Workflow hardening applied (`ci.yml`, `release.yml`)

## Blocking Items

- [ ] Bump `project.version` beyond `0.1.3`
- [ ] Prepare matching changelog section for new target version
- [ ] Produce unique release tag (`vX.Y.Z`) not already present

## Maintainer Next Step

Do not execute publish flow until version/tag identity is updated.
