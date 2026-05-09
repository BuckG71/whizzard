# Whizzard

Local capability governance for AI agents. Run powerful agent harnesses inside explicit, temporary, human-readable permission boundaries.

> **Status:** MVP under construction. Stages 1–7 are working (contained shell, mount registry, profiles, dry-run, session logging, safety validation, generic adapter); subsequent stages add Hermes integration, MCP cooperation surface, presets and CLI ergonomics, Claude Code slash commands, OneCLI vault, mid-session capability adjustment, duration enforcement, Discord control plane, and image management. See [docs/mvp_build_plan.md](docs/mvp_build_plan.md).

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
pip install -e .
```

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
