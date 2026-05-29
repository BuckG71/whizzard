# Changelog

All notable user-facing changes to Whizzard land here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project follows
[Semantic Versioning](https://semver.org/) once the public API stabilizes at
v1.0.

Decision IDs (`D-NN`) in entries below reference [`docs/decisions.md`](docs/decisions.md) — the canonical record for *why* a change happened.

## [Unreleased]

First public release in preparation. See [ROADMAP.md](ROADMAP.md) for what's
planned through v1.0.

### Added

- **`whiz init` first-run wizard.** Walks new users through five short
  configuration steps + a Hermes profile sub-step. Builds both the base
  and Hermes execution images, sets up profiles / mounts / harnesses /
  presets, and detects existing Hermes installs to clone profiles
  automatically. Non-interactive `--yes` mode for CI / scripted installs.
- **`whiz hermes image build` CLI verb.** First-class command for
  building `whizzard-hermes:latest` from the bundled `Dockerfile.hermes`.
  Mirrors the existing `whiz image build` shape; called by `whiz init`.
- `whiz image check` reports whether the local execution image is older
  than a configurable staleness threshold (default 30 days). Exits 0 fresh,
  1 stale, 2 not-built. CI-scriptable.
- `whiz image status` now shows the image id, build date, and the base
  digest pinned in the Dockerfile.

### Changed

- **Dockerfiles are now bundled as package data.** Moved from `docker/`
  at the repo root to `whizzard/_dockerfiles/` inside the Python package
  so `pip install whizzard` distributes them. Runtime lookup uses
  `importlib.resources`; works in both dev (editable install) and
  installed (wheel) modes.
- `Dockerfile` pins the base image by sha256 digest. A floating tag
  silently rolls the containment surface; the digest is the integrity
  anchor session logs and `whiz image status` reference.

### Fixed

- `run_shell` now wraps the session lifecycle in a try/finally so the
  per-session cidfile is unlinked even if an exception interrupts the
  session (KeyboardInterrupt, monitor / audit errors). Prevents
  long-running installs accumulating stray files in STATE_DIR.

### Packaging

- GitHub Actions release workflow (`.github/workflows/release.yml`)
  builds sdist + wheel on `v*` tag push and publishes to PyPI via
  Trusted Publishing (OIDC; no API token storage). Pre-release tags
  (`v0.1.0rc1`) route through the same workflow as stable tags;
  PyPI's pre-release semantics keep them out of default `pip install`
  resolution until promoted.
