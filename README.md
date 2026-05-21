# Whizzard

Local capability governance for AI agents. Run powerful agent harnesses inside explicit, temporary, human-readable permission boundaries.

> **Status:** MVP under construction. Stages 1–10 + 12 SHIPPED (containment, mount registry, profiles, dry-run, session logging, safety, generic adapter, Hermes integration end-to-end including manual smoke validation, in-cell MCP read-only surface, presets + CLI ergonomics, cross-adapter credential utility). Outstanding: Stage 11 (harness integration examples in `docs/examples/`), Stages 13–18 (capability adjustment, mutating MCP tools, duration enforcement, Discord control plane, image management). See [docs/mvp_build_plan.md](docs/mvp_build_plan.md).

> **Naming:** "Whizzard" is a working name. The project may rename before OSS launch. See [docs/decisions.md](docs/decisions.md) D-144.

---

## What this is

See [docs/vision_and_strategy.md](docs/vision_and_strategy.md). In one sentence: Whizzard wraps an agent harness in a hardened, scoped, time-bounded execution cell with auditable capability grants.

The core invariant:

```
Whizzard controls capabilities.
Agents request capabilities.
Agents do not grant themselves capabilities.
```

## Prerequisites

- macOS or Linux
- Python 3.11+
- Docker Desktop (or any Docker daemon) running

## Install (development)

```sh
git clone <this-repo>
cd whizzard
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"     # includes pytest, ruff, mypy
```

### Dev workflow

One-command lint + typecheck + test:

```sh
make check
```

Individual targets: `make test`, `make lint`, `make fmt` (auto-fix), `make typecheck`, `make validate-decisions`, `make dx ARGS='D-158'`. Configs for all three tools live in `pyproject.toml`.

Pre-commit hooks for the same checks: `pip install pre-commit && pre-commit install`. CI (GitHub Actions, `.github/workflows/ci.yml`) runs the same set on push and PR.

## First run

Build the execution image:

```sh
whizzard image build
whizzard image status
```

Launch a contained shell under the default profile:

```sh
whizzard run --profile default
```

You should see a `Whizzard Profile: DEFAULT` banner followed by a bash prompt inside the container. Confirm containment by trying to access the host home directory:

```sh
ls /Users/$USER   # should fail or show nothing — host home is not mounted
whoami            # should print "whizzard", not your host user
```

Exit with `exit` or `Ctrl-D`.

## Optional: Hermes adapter

Whizzard ships a generic shell adapter (above) plus an optional Hermes adapter for the [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) harness. The Hermes adapter is bundled in the Python package — no separate `pip install` step — but the execution image needs Hermes layered on top of the base image:

```sh
docker build -f docker/Dockerfile.hermes -t whizzard-hermes:latest .
```

That image pins Hermes to a specific upstream commit; bump `HERMES_REF` in `docker/Dockerfile.hermes` to update.

Then point Whizzard at the Hermes image and a harness entry:

```sh
# 1. Clone a Hermes profile into a sibling directory (auth.json + runtime state excluded).
whiz hermes profile create whizzard-cell --clone-from default

# 2. Configure ~/.whizzard/config/harnesses.json with a `hermes-cell` entry — see config/harnesses.json.example.

# 3. Launch.
WHIZZARD_IMAGE=whizzard-hermes:latest whiz run --harness hermes-cell
```

For non-Ollama providers (Anthropic, OpenAI, etc.), declare credential env-var names in the harness's `secrets:` field; values resolve from OneCLI or host env at launch (D-162). Never put plaintext credential values in `harnesses.json`.

## Using OIQ inside your agent harness

The OIQ CLI is the harness-neutral integration surface. Any agent harness that can shell out can wrap `oiq r`, `oiq s`, etc. — no harness-specific runtime lives in OIQ core.

Copy-paste integration recipes live in **[`docs/examples/`](docs/examples/)**:

- **[`docs/examples/claude_code/`](docs/examples/claude_code/)** — Claude Code skill files (`/oiq-launch`, `/oiq-status`, `/oiq-presets`, `/oiq-sessions-tail`). Drop into `~/.claude/skills/` to install.
- **[`docs/examples/hermes/`](docs/examples/hermes/)** — Hermes adapter setup recipe (image build, profile clone, harness config, provider config).
- Other harnesses welcome via PR — see [`docs/examples/README.md`](docs/examples/README.md) for contribution guidance.

The design choice to ship integration as docs rather than as harness-specific code in OIQ core is captured in [`decisions.md`](docs/decisions.md) D-161.

## Available profiles

```sh
whizzard profiles list
```

Profiles available in Stage 1: `safe`, `default`, `build`, `power`, `quarantine`. The `default` profile is the always-on baseline (network enabled, no mounts, no expiry); other profiles add or remove capabilities.

## Repository layout

```
whizzard/
  whizzard/        # Python package
  docker/          # execution image
  config/          # JSON configs (populated in later stages)
  scripts/         # profile wrapper scripts (populated in later stages)
  docs/            # design docs (vision, architecture, build plans, decisions)
  tests/           # tests
  README.md
  pyproject.toml
```

## Documentation

- [docs/vision_and_strategy.md](docs/vision_and_strategy.md) — what this is, who it's for, where it's going
- [docs/architecture.md](docs/architecture.md) — system structure, safety policy, adapter contract, control layering
- [docs/mvp_build_plan.md](docs/mvp_build_plan.md) — tactical MVP plan (18 stages)
- [docs/post_mvp_spec.md](docs/post_mvp_spec.md) — v1.0 features and backlog
- [docs/control_surface.md](docs/control_surface.md) — full structural-control surface map
- [docs/decisions.md](docs/decisions.md) — append-only decisions index
