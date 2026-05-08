# Airlock / Warlock

Local capability governance for AI agents. Run powerful agent harnesses inside explicit, temporary, human-readable permission boundaries.

> **Status:** MVP under construction. Stage 1 (contained shell launch) is working; subsequent stages add mounts, profiles, dry-run, logging, safety validation, adapters, Hermes integration, and image management. See [docs/mvp_build_plan.md](docs/mvp_build_plan.md).

---

## What this is

See [docs/vision_and_strategy.md](docs/vision_and_strategy.md). In one sentence: Warlock is the orchestrator, Airlock is the containment layer it operates inside.

The core invariant:

```
Airlock controls capabilities.
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
cd airlock-warlock
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## First run

Build the execution image:

```sh
warlock image build
warlock image status
```

Launch a contained shell under the default profile:

```sh
warlock run --profile default
```

You should see an `Airlock Profile: DEFAULT` banner followed by a bash prompt inside the container. Confirm containment by trying to access the host home directory:

```sh
ls /Users/$USER   # should fail or show nothing — host home is not mounted
whoami            # should print "warlock", not your host user
```

Exit with `exit` or `Ctrl-D`.

## Available profiles

```sh
warlock profiles list
```

Profiles available in Stage 1: `safe`, `default`, `build`, `power`, `quarantine`. The `default` profile is the always-on baseline (network enabled, no mounts, no expiry); other profiles add or remove capabilities.

## Repository layout

```
airlock-warlock/
  warlock/         # Python package
  docker/          # execution image
  config/          # JSON configs (populated in later stages)
  scripts/         # profile wrapper scripts (populated in later stages)
  docs/            # design docs (vision, architecture, build plans)
  tests/           # tests
  README.md
  pyproject.toml
```

## Documentation

- [docs/vision_and_strategy.md](docs/vision_and_strategy.md) — what this is, who it's for, where it's going
- [docs/architecture.md](docs/architecture.md) — system structure, safety policy, adapter contract
- [docs/mvp_build_plan.md](docs/mvp_build_plan.md) — tactical MVP plan
- [docs/post_mvp_spec.md](docs/post_mvp_spec.md) — v1.0 features and backlog
