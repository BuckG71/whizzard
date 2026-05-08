# Airlock / Warlock — MVP Build Plan

This document is the tactical plan for the MVP. It assumes context from:

- [vision_and_strategy.md](vision_and_strategy.md) — the product's why, audience, and long-term direction
- [architecture.md](architecture.md) — system components, layers, safety policy, adapter schema, and architectural invariants

The MVP exists to prove that useful autonomous agents can coexist with practical local security boundaries.

---

## MVP Definition

The MVP is operational when the system can:

1. Launch a generic Docker shell under a profile.
2. Mount only approved registered folders.
3. Apply read-only and read-write mount modes.
4. Toggle network access by profile.
5. Reject dangerous mounts per the safety policy.
6. Show dry-run permission previews.
7. Write session logs.
8. Launch a generic harness through an adapter.
9. Manage and audit the container image used for execution.

---

## Build Order

### Stage 1 — Generic Docker Shell Launch

Goal: prove contained execution.

Deliverable:

```zsh
warlock run --profile default
```

Requirements:
- non-root container user
- no host home mount
- no Docker socket
- baseline restrictions active

### Stage 2 — Mount Registry

Goal: human-readable named capabilities.

Example:

```zsh
warlock run --profile build --mount project-alpha
```

Rules:
- mounts must be registered in `mounts.json`
- no arbitrary host paths
- mount permissions capped by registry

### Stage 3 — Profiles

Initial profiles:
- `safe`
- `default`
- `build`
- `power`
- `quarantine`

Default profile is `SAFE-NET`:
- network enabled
- useful by default
- no unrestricted host access

### Stage 4 — Dry Run

Goal: visible permissions before execution.

Example:

```zsh
warlock run --dry-run --profile build --mount project-alpha
```

Dry-run output must include:
- profile name and effective capabilities
- each mount with path and mode (ro/rw)
- network mode
- session duration limit (if set)
- any safety warnings or overrides active

Duration must be shown explicitly so the user knows when the session will auto-terminate.

### Stage 5 — Session Logging

Log:
- profile
- mounts
- network mode
- container id
- image id
- session start time
- session duration limit (if set)
- actual session duration
- expiry reason (user exit / timeout / safety termination)
- wrap-up event: command sent, response received or timeout, duration consumed
- whether SIGTERM was sufficient or SIGKILL was required
- exit status

Session duration is a first-class field. Time-bounded sessions are a primary safety primitive and must be enforced, not advisory.

Termination flow:

```text
1. T-minus wrap_up_grace_seconds: adapter.wrap_up() invoked
2. Adapter sends harness-native wrap-up signal, waits for confirmation (bounded by grace)
3. SIGTERM sent to container
4. Short final grace (5s) for clean shutdown
5. SIGKILL if still running
```

Each step is logged with timestamps so a session's wind-down is fully auditable.

### Stage 6 — Safety Validation

Implement the safety policy defined in [architecture.md](architecture.md).

Specifically:
- enforce the hard-block list (no override)
- enforce the override-required list (`--allow-broad-mount`, logged)
- enforce config write-protection (the Warlock config directory must never be reachable from any agent-writable mount, regardless of `mounts.json`)
- reject any mount path that resolves into the Warlock config directory

### Stage 7 — Generic Adapter

First adapter: generic shell adapter.

This proves the harness abstraction architecture before any harness-specific integration. The adapter contract and `harnesses.json` schema are defined in [architecture.md](architecture.md).

The MVP adapter interface includes:
- `launch(workspace, config)` — start the harness inside the container
- `stop()` — clean shutdown
- `wrap_up(grace_seconds)` — invoke the harness's native graceful-shutdown mechanism (no-op for generic shell)
- `health_check()` — confirm harness is ready

The wrap_up method must exist from MVP so the Hermes adapter (Stage 8) can implement it without an interface change.

### Stage 8 — Hermes Integration

Hermes integration must occur ONLY through the adapter layer.

Not:
```text
Airlock = Hermes wrapper
```

Instead:
```text
Hermes adapter → Airlock core
```

### Stage 9 — Image Management

Goal: prevent stale or unknown images from undermining containment.

Requirements:
- base image digest pinned in `Dockerfile` (not floating tag)
- `warlock image build` to build/rebuild the local image
- `warlock image status` to show current image id, build date, base digest
- session log records the image id for each session

Stale images are a silent risk: a compromised or outdated base image defeats the containment model regardless of policy correctness. Image provenance must be visible and auditable from day one.

---

## Repository Structure

```text
airlock-warlock/
  README.md
  pyproject.toml

  warlock/
    cli.py
    config.py
    docker_cmd.py
    safety.py
    logging.py
    adapters/
      generic.py
      hermes.py

  config/
    profiles.json
    mounts.json
    harnesses.json

  docker/
    Dockerfile

  scripts/
    warlock-safe
    warlock-default
    warlock-build
    warlock-power

  tests/
```

---

## MVP Acceptance Test

The MVP passes if these commands behave as specified:

```zsh
warlock run --profile safe
warlock run --profile default
warlock run --profile build --mount project-alpha
warlock run --dry-run --profile build
warlock adapters list
warlock profiles list
warlock mounts list
warlock image status
```

And:
- dangerous mounts are blocked per the safety policy
- logs are written
- containerized execution works
- network mode changes by profile
- host home directory is inaccessible
- adapter abstraction is preserved
- image provenance is recorded for every session

---

## Explicit Non-MVP Features

Do NOT build initially:
- GUI
- Discord control plane
- MCP gateway
- per-agent orchestration
- breaker engine
- shadow-home system
- file tree mount picker
- AI risk scoring
- VM orchestration

These belong to post-MVP phases. See [post_mvp_spec.md](post_mvp_spec.md) and [vision_and_strategy.md](vision_and_strategy.md).

---

## Design Discipline

Keep the MVP narrow.

Primary success criteria:
- useful
- understandable
- secure enough
- low-friction
- extensible

The MVP succeeds if it becomes a practical daily-driver permission harness for local agents.
