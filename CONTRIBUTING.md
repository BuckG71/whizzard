# Contributing to Whizzard

> **Status:** Whizzard is pre-`v0.1.0` (single-developer today). The contributor guidance below describes the process used now and the conventions the project will commit to at OSS launch. PRs are not yet open to outside contributors — this doc is for when that changes.

## What this project is, in one sentence

Whizzard is a local capability-governance layer for AI agents — wraps an agent harness in a hardened, scoped, time-bounded execution sandbox (the hardened Docker container Whizzard launches each agent session inside) with auditable capability grants. See [`docs/vision_and_strategy.md`](docs/vision_and_strategy.md) for the long version.

## Before you write code

1. **Read [`docs/README.md`](docs/README.md)** — the doc nav index. Recommended first-time orientation order: vision → architecture → decisions.
2. **Read [`docs/decisions.md`](docs/decisions.md)** for any decision IDs your change interacts with. Decisions are append-only; they capture the *why* behind the code. Use `python3 scripts/dx.py <decision-id>` to look up a specific decision or `python3 scripts/dx.py find <text>` to search.
3. **Check [`ROADMAP.md`](ROADMAP.md)** to see what's planned for v1.0 and where contribution would land well.
4. **Skim [`docs/known_issues.md`](docs/known_issues.md)** if your change touches an area with deferred work, a known functional gap, or recorded tech debt — saves you rediscovering it.
5. **For UX-shaped changes** (CLI surfaces, presets, slash commands, Discord control plane), expect a design conversation before code.

## Local setup

```sh
git clone <repo>
cd whizzard
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"     # core deps + pytest, ruff, mypy
pre-commit install          # optional but recommended
```

## Dev workflow

One command runs everything CI runs:

```sh
make check                  # lint + typecheck + unit tests (~460 tests, <2s)
```

Individual targets:

| Command | What it does |
|---------|--------------|
| `make test` | Fast unit suite (`pytest` against `tests/`, integration tier deselected) |
| `make lint` | `ruff check whizzard scripts tests` |
| `make fmt` | `ruff check --fix` (auto-fixable lint corrections + import sort) |
| `make typecheck` | `mypy whizzard scripts` |
| `make coverage` | Unit suite with coverage report; enforces ≥80% threshold |
| `make integration` | Integration tier — real Docker, real images. Slower; opt-in. |
| `make validate-decisions` | Schema + tag-vocabulary + reference integrity for `docs/decisions.md` |
| `make dx ARGS='<decision-id>'` | Pretty-print a decision entry; supports `find`, `tag`, `type`, `status`, `list` |

CI (GitHub Actions, `.github/workflows/ci.yml`) runs the same set on push and PR against Python 3.11 and 3.12.

## Code conventions

- **Type hints on public APIs.** mypy runs in CI; `pyproject.toml` declares the strictness level.
- **Ruff handles formatting + imports.** Run `make fmt` before committing; pre-commit enforces it. Curated rule set (E/W/F/B/I/UP/SIM) — see `[tool.ruff.lint]` in `pyproject.toml`.
- **Decision references in commits and PRs.** When the change implements or modifies a decision, mention the decision ID in the commit message (`feat(adapters): Hermes UID parity wiring (D-56)`).
- **Adapter authors:** the `HarnessAdapter` Protocol in `whizzard/adapters/base.py` is the contract. The load-bearing rule is: harness-specific identifiers (Hermes-, OpenClaw-, NanoClaw-specific) stay inside the adapter module, not in core.

## Tests

- Unit tests live under `tests/`, one test file per source module (`test_<module>.py`). They use `monkeypatch` + `tmp_path`; **no real Docker, no real Hermes, no real OneCLI** required for the suite to pass. Default `make test` runs this tier (~460 tests, ~1s).
- **Integration tests** live under `tests/integration/`, marked `@pytest.mark.integration`. They exercise real Docker against the built `whizzard-base:latest` and `whizzard-hermes:latest` images, covering: containment invariants (read-only rootfs, non-root user, capability drops, network-off egress, Docker-socket absence, bind-mount isolation, hostile-symlink containment, read-only mount writes blocked), duration + idle-timeout enforcement (verifying the cap actually stops containers), the full `run_shell` launch path end-to-end, the `whiz adjust` mid-session primitives against real Docker, in-sandbox MCP deployment (the host `whizzard` package must *not* be importable in the sandbox — verified each run), MCP stdio protocol round-trip, and Hermes binary + Ollama reachability. Excluded from default runs via the `addopts = "-m 'not integration'"` setting in `pyproject.toml`; run explicitly with `make integration` or `pytest -m integration`. Gated on Docker daemon availability — skipped cleanly when Docker isn't reachable.
- Adding a new test file? Follow the existing per-module pattern (unit) or add to `tests/integration/` with the marker (integration).
- Manual smoke tests (real Hermes + real harness) require user-specific config and aren't part of either automated tier; the maintainer keeps a private runbook.

## Decisions, handoffs, and process artifacts

- **`docs/decisions.md`** is append-only. Add a new decision (next sequential ID) rather than editing prior entries. If your change supersedes a prior decision, update the prior entry's `Status:` to `superseded by <new-id>` in the same commit. Canonical tag vocabulary lives at the bottom of `docs/decisions.md`.
- **Memory entries** (collaboration patterns, user preferences) live in personal memory files outside the repo — not part of the contribution surface.

## Filing issues

(When the issue tracker is live.) Please include:

- What you were trying to do
- What happened instead
- A minimal reproduction (`pyproject.toml` + harness config + command run)
- `whiz status` output if a session was involved
- Tail of `~/.whizzard/logs/sessions.jsonl` for the failing session

## Security

Security-relevant findings — sandbox escape, capability bypass, credential-leak surfaces — should be reported privately first via the channel in [SECURITY.md](SECURITY.md). See `docs/threat_model.md` for the design posture you're testing against; the security-load-bearing decisions are D-9 (one-way capability flow), D-11 (mount registry as permission ceiling), D-21 (config write-protection), D-156 (in-sandbox MCP cooperation layer), and D-162 (host-injected secrets).

## License

Whizzard is MIT-licensed. By contributing you agree your contributions are also under MIT. See [`LICENSE`](LICENSE).
