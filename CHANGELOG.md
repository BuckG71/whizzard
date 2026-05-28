# Changelog

All notable user-facing changes to Whizzard land here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project follows
[Semantic Versioning](https://semver.org/) once the public API stabilizes at
v1.0.

For the detailed engineering log (stage-by-stage shipments, decision IDs,
finding-level fixes), see [`docs/engineering_log.md`](docs/engineering_log.md).

## [Unreleased]

First public release in preparation. See [ROADMAP.md](ROADMAP.md) for what's
planned through v1.0.

### Added

- `whiz image check` reports whether the local execution image is older
  than a configurable staleness threshold (default 30 days). Exits 0 fresh,
  1 stale, 2 not-built. CI-scriptable.
- `whiz image status` now shows the image id, build date, and the base
  digest pinned in the Dockerfile.

### Changed

- `docker/Dockerfile` now pins the base image by sha256 digest. A floating
  tag silently rolls the containment surface; the digest is the integrity
  anchor session logs and `whiz image status` reference.

### Fixed

- `run_shell` now wraps the session lifecycle in a try/finally so the
  per-session cidfile is unlinked even if an exception interrupts the
  session (KeyboardInterrupt, monitor / audit errors). Prevents
  long-running installs accumulating stray files in STATE_DIR (F-B-09).
