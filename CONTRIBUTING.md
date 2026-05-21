# Contributing to Whizzard

> **Status:** Whizzard is in MVP-construction phase (single-developer, single-user). The contributor guidance below describes the process used today and the conventions the project will commit to at OSS launch. PRs are not yet open to outside contributors — this doc is for when that changes.

## What this project is, in one sentence

Whizzard is a local capability-governance layer for AI agents — wraps an agent harness in a hardened, scoped, time-bounded execution cell with auditable capability grants. See [`docs/vision_and_strategy.md`](docs/vision_and_strategy.md) for the long version.

## Before you write code

1. **Read [`docs/README.md`](docs/README.md)** — the doc nav index. Specifically the first-time orientation order: vision → architecture → mvp_build_plan → control_surface → post_mvp_spec.
2. **Read [`docs/decisions.md`](docs/decisions.md)** for any decision IDs your change interacts with. Decisions are append-only (D-129); they capture the *why* behind the code. Use `python3 scripts/dx.py D-NN` to look up a specific decision or `python3 scripts/dx.py find <text>` to search.
3. **Check [`docs/HANDOFF.md`](docs/HANDOFF.md)** for the latest session entry (newest at top of the log) and the Current State header — tells you what's in flight and what's just-shipped.
4. **For UX-shaped changes** (CLI surfaces, presets, slash commands, Discord control plane), expect a design conversation before code per D-148. Stages 11, 16, 17 have explicit design-pause requirements.

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
make check                  # lint + typecheck + 311 tests
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
| `make dx ARGS='D-158'` | Pretty-print a decision entry; supports `find`, `tag`, `type`, `status`, `list` |

CI (GitHub Actions, `.github/workflows/ci.yml`) runs the same set on push and PR against Python 3.11 and 3.12.

## Code conventions

- **Type hints on public APIs.** mypy runs in CI; `pyproject.toml` declares the strictness level.
- **Ruff handles formatting + imports.** Run `make fmt` before committing; pre-commit enforces it. Curated rule set (E/W/F/B/I/UP/SIM) — see `[tool.ruff.lint]` in `pyproject.toml`.
- **Decision references in commits and PRs.** When the change implements or modifies a decision, mention the D-NN in the commit message (`feat(adapters): Hermes UID parity wiring (D-56)`).
- **Adapter authors:** the `HarnessAdapter` Protocol in `whizzard/adapters/base.py` is the contract. `D-153` is the load-bearing rule — Hermes/OpenClaw/etc.-specific identifiers stay inside the adapter module, not in core.

## Tests

- Unit tests live under `tests/`, one test file per source module (`test_<module>.py`). They use `monkeypatch` + `tmp_path`; **no real Docker, no real Hermes, no real OneCLI** required for the suite to pass. Default `make test` runs this tier (311 tests, <1s).
- **Integration tests** live under `tests/integration/`, marked `@pytest.mark.integration`. They exercise real Docker against the built `whizzard-base:latest` image to verify containment (read-only rootfs, non-root user, tmpfs writable, etc.). Excluded from default runs via the `addopts = "-m 'not integration'"` setting in `pyproject.toml`; run explicitly with `make integration` or `pytest -m integration`. Gated on Docker daemon availability — skipped cleanly when Docker isn't reachable.
- Adding a new test file? Follow the existing per-module pattern (unit) or add to `tests/integration/` with the marker (integration).
- Manual smoke tests (real Hermes + real harness) live in `docs/stage_validation.md` and `docs/STAGE_8_BUILD_PLAN.md` (M7 runbook). These require user-specific config and aren't part of either automated tier.

## Decisions, handoffs, and process artifacts

- **`docs/decisions.md`** is append-only. Add a new `D-NN` rather than editing prior entries. If your change supersedes a prior decision, update the prior entry's `Status:` to `superseded by D-NN` in the same commit. See [`~/.claude/skills/decision-capture/SKILL.md`](https://github.com/) (TBD repo link) for the schema and self-audit checklist; canonical tag vocabulary lives at the bottom of `docs/decisions.md`.
- **`docs/HANDOFF.md`** is append-only per D-150. The `# Current State` block at the top of the file is mutable; the log section below is not.
- **Memory entries** (collaboration patterns, user preferences) live in personal memory files outside the repo — not part of the contribution surface.

## Filing issues

(When the issue tracker is live.) Please include:

- What you were trying to do
- What happened instead
- A minimal reproduction (`pyproject.toml` + harness config + command run)
- `whiz status` output if a session was involved
- Tail of `~/.whizzard/logs/sessions.jsonl` for the failing session

## Security

Security-relevant findings — escape-of-cell, capability-bypass, credential-leak surfaces — should be reported privately first. (Contact path will be documented at OSS launch.) See `docs/vision_and_strategy.md`'s threat-model + the security-conscious decisions cluster (D-9, D-11, D-21, D-156, D-162) for the design posture you're testing against.

## License

Whizzard is MIT-licensed. By contributing you agree your contributions are also under MIT. See [`LICENSE`](LICENSE).
