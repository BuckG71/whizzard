# Changelog

All notable user-facing changes to Whizzard land here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project follows
[Semantic Versioning](https://semver.org/) once the public API stabilizes at
v1.0.

## [0.1.0] - 2026-07-14

First public release. Runs an agent harness (Hermes) inside a hardened,
scoped, time-bounded Docker sandbox, with the agent's credentials kept out of
the container. See [ROADMAP.md](ROADMAP.md) for what's planned through v1.0.

### Added

- **Credentials never enter the sandbox.** Whizzard keeps the credentials an
  agent uses out of the container entirely — the sandbox holds a placeholder
  while the real key stays on your machine, attached to a request only as it
  leaves for the provider. Choose the posture per profile, or per session with
  `--credential-handling`: `native` (default, no extra tools) keeps your model
  key private via a host-side broker and works with API keys *and*
  subscription / OAuth logins; `onecli` and `hybrid` extend the same guarantee
  to your service tokens (GitHub, Slack, tool APIs) through
  [OneCLI](https://onecli.sh) — `hybrid` is required when you sign in to your
  model provider with OAuth, which OneCLI can't inject. The wizard asks which
  fits, in plain language, and writes it as the default.
- **`whiz init` first-run wizard.** Walks new users through five short
  configuration steps + a Hermes profile sub-step. Builds both the base
  and Hermes execution images, sets up profiles / mounts / harnesses /
  presets, and detects existing Hermes installs to clone profiles
  automatically. Non-interactive `--yes` mode for CI / scripted installs.
- **Sandbox boundary cues.** `whiz r` prints an explicit "entering the
  sandbox" banner on launch and a "you are back on your host — uncontained"
  banner on exit, and the `whiz init` summary warns that running the harness
  directly (outside Whizzard) is uncontained. Makes the contained vs.
  uncontained boundary impossible to miss.
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
- **Launch now selects the harness's image.** A bare launch derived the
  container image from the adapter's `default_image` instead of a
  hardcoded base, so `whiz r hermes` runs the Hermes cell without the user
  naming an image.
- **Hermes cell defaults to interactive mode.** The cell's default command
  is now `hermes` (interactive terminal) rather than the gateway daemon,
  which idled waiting for messaging-platform config (D-181).
- **`whiz init` Docker preflight probes the daemon.** It now distinguishes
  "Docker not installed," "installed but not running," and
  "Windows-containers mode" with OS-aware, actionable messages, instead of
  asserting Docker is running after only a PATH check.
- **`--harness` is required on `whiz run`.** Bare `whiz run` no longer
  silently defaults to the internal shell (which dead-ended after setup);
  it now asks for an explicit `--harness` (e.g. `hermes-cell`).
- Scrubbed stale `oiq` command references from user-facing output.
- **`whiz init` aborts cleanly on closed stdin.** EOF at a prompt (Ctrl-D, or
  piped / empty input) now prints a short "no input available" message and
  points at `whiz init --yes`, instead of surfacing a raw Python traceback.

### Security

- **Credential handling degrades safely.** When OneCLI is unavailable at
  launch, a session runs model-only (native handling) with a clear message
  rather than failing cryptically; the wizard and preflight warn — but never
  block — when the installed OneCLI is outside Whizzard's validated version
  range, so the marker never stands between you and an OneCLI security update.
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
