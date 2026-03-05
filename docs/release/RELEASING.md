# Releasing telecom-mcp

This repository uses tag-triggered GitHub Releases.

## Prerequisites

- CI is green on the commit you plan to release.
- `pyproject.toml` version is already bumped to the intended release version.
- No secrets or internal credentials are present in tracked files.

## What the workflows do

- `.github/workflows/ci.yml`
  - Runs on pushes and pull requests.
  - Executes `ruff`, `pytest`, and `python -m build`.
  - Acts as the quality gate before tagging.

- `.github/workflows/release.yml`
  - Runs on tag push matching `v*`.
  - Builds `sdist` and `wheel` artifacts with `python -m build`.
  - Creates a GitHub Release using `GITHUB_TOKEN`.
  - Uploads `dist/*` as release assets.

## Maintainer flow

1. Bump `project.version` in `pyproject.toml`.
2. Update `CHANGELOG.md` (recommended).
3. Commit and push changes.
4. Create and push an annotated tag:

```bash
git tag -a vX.Y.Z -m "vX.Y.Z"
git push origin vX.Y.Z
```

5. Verify the `Release` workflow succeeds in GitHub Actions.
6. Verify the GitHub Release exists for the same tag and contains:
   - `*.whl`
   - `*.tar.gz`
7. Confirm package metadata version matches the tag.

## Rollback (if needed)

If a release must be retracted:

1. Delete the GitHub Release for that tag in the UI.
2. Delete the tag locally and remotely:

```bash
git tag -d vX.Y.Z
git push origin :refs/tags/vX.Y.Z
```

3. Fix the issue, then cut a new tag.

## Notes

- Release artifacts are public and must not contain secrets.
- Keep the default runtime mode safe (`inspect`) unless explicit maintenance gating is required.
