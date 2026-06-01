# Changelog

All notable user-facing changes to Whizzard land here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project follows
[Semantic Versioning](https://semver.org/) once the public API stabilizes at
v1.0.

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

### Security

- **Credential values are redacted from the audit log.** Secret env
  vars injected into a session (LLM / platform tokens resolved via
  OneCLI or host-env fallback) are scrubbed to `***` in the `argv`
  recorded in `~/.whizzard/logs/sessions.jsonl`. The container still
  receives the real values; only the on-disk log is sanitized.
- **Launches fail closed.** If the per-session capability snapshot
  can't be written, the launch aborts rather than starting a session
  whose in-cell status surface can't reflect its own constraints.
- **Harness config rejects process-loader env keys.** `harnesses.json`
  refuses `LD_PRELOAD`, `LD_LIBRARY_PATH`, `PATH`, `IFS`, and similar
  names that could alter process loading or tool resolution in the
  sandbox.
- **Config writes are atomic.** Profiles, mounts, harnesses, presets,
  the per-session snapshot, and request resolutions write via a
  temp-file + rename, so a crash mid-write can't leave a truncated
  config that locks you out.
- Adversarial red-team test suite added for the containment invariants
  (escape, config write-protection, network policy, cooperation-layer
  forgery, snapshot poisoning); the dependency tree is scanned with
  `pip-audit` in CI.

### Packaging

- GitHub Actions release workflow (`.github/workflows/release.yml`)
  builds sdist + wheel on `v*` tag push and publishes to PyPI via
  Trusted Publishing (OIDC; no API token storage). Pre-release tags
  (`v0.1.0rc1`) route through the same workflow as stable tags;
  PyPI's pre-release semantics keep them out of default `pip install`
  resolution until promoted.
