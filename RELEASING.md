# Releasing Whizzard

The tag-and-release runbook. Publishing is automated: pushing a `v*` tag
triggers `.github/workflows/release.yml`, which verifies, builds, and
publishes to PyPI via Trusted Publishing (OIDC — no API tokens stored).

## Versioning

Pre-1.0, Whizzard uses a `0.x.y` cadence — minor (`x`) bumps for feature
work, patch (`y`) for fixes; breaking changes are expected and allowed
between `0.x` minors while the API settles. From `1.0.0` onward the project
follows [SemVer](https://semver.org/): MAJOR for breaking changes, MINOR
for backwards-compatible features, PATCH for fixes.

Pre-release tags use PEP 440 suffixes: `0.1.0rc1`, `0.1.0rc2`, … PyPI
excludes pre-releases from default `pip install whizzard` resolution, so
they're safe to publish for reviewers without affecting normal installs.

The version lives in one place: `version` in `pyproject.toml`. The git tag
must match it (`v` + the pyproject version).

## Release steps

1. **Land all work on `main`** and confirm CI is green.
2. **Update the version** in `pyproject.toml` (`version = "0.x.y"`).
3. **Update `CHANGELOG.md`** — move items out of `[Unreleased]` into a new
   `[0.x.y] - YYYY-MM-DD` section. Confirm `[Unreleased]` is accurate and
   nothing pending was missed.
4. **Commit** the version + changelog bump:
   `chore(release): bump version to 0.x.y`.
5. **Tag** matching the pyproject version exactly:
   ```sh
   git tag v0.x.y
   git push origin main --tags
   ```
6. **Watch the release workflow.** It runs three jobs:
   - `verify` — lint + typecheck + unit tests on Python 3.11 and 3.12
   - `build` — sdist + wheel, with a Dockerfile-presence assertion
   - `publish` — uploads to PyPI via Trusted Publishing
7. **Confirm on PyPI** the new version is live and the long description
   renders correctly.

## First-ever publish

The PyPI project name is claimed on the first successful publish. This
requires the **pending publisher** to be registered first at
<https://pypi.org/manage/account/publishing/> (project `whizzard`, owner
`BuckG71`, repo `whizzard`, workflow `release.yml`, no environment). Until
that's registered, the `publish` job fails with an OIDC error while
`verify` + `build` still pass — so you can dry-run the pipeline before the
publisher exists.

## Re-tagging

`skip-existing` is intentionally **not** set on the publish step: a re-tag
with a version that already exists on PyPI fails loudly rather than
silently no-op'ing. If a release is botched, bump to the next patch
version rather than reusing a tag — PyPI does not allow overwriting a
released version.

## Fast-follow (not yet wired)

- Sigstore signature attachment on published artifacts
- GitHub Release auto-creation from the tag (changelog body)
- Docker image tag-and-push (registry + tag format TBD — see launch
  checklist §I)
