# Warlock / Airlock MVP Build Plan v4

Date: 2026-05-08

## Core Thesis

Warlock/Airlock is a local-first capability governance layer for running powerful AI agents with explicit, temporary, human-readable permission boundaries.

Core principle:

```text
Warlock controls capabilities.
Agents request capabilities.
Agents do not grant themselves capabilities.
```

The MVP should prove:

```text
Useful autonomous agents can coexist with practical local security boundaries.
```

---

# Architectural Separation

## Critical Design Rule

```text
No harness-specific logic belongs in Airlock core.
```

Airlock core must remain harness-neutral.

---

# System Architecture

```text
Warlock = local orchestrator / launcher
Airlock = policy and containment layer
Execution Cell = Docker container
Harness Adapter = Hermes/OpenClaw/etc integration layer
```

---

# Explicit Architecture Layers

## 1. Airlock Core

Responsibilities:
- profiles
- mount registry
- policy resolution
- Docker execution
- network controls
- safety validation
- session logging
- dry-run preview

Airlock core should know nothing about:
- Hermes internals
- OpenClaw internals
- Discord bots
- MCP specifics

---

## 2. Harness Adapter Layer

Adapters translate harness-specific behavior into Airlock-compatible execution.

Initial adapters:
- generic shell adapter
- Hermes adapter (post-MVP integration)
- OpenClaw adapter (future)
- NanoClaw adapter (future)

Future:
- MCP gateway adapter

Responsibilities:
- launch harness
- stop harness
- inject workspace/config
- identify agents
- route tool execution

---

## 3. Execution Backend Layer

MVP backend:
- Docker

Future backends:
- Podman
- Firecracker
- Apple Virtualization Framework
- cloud execution cells

The execution backend is intentionally abstracted.

---

# Host vs Container Boundary

```text
Host machine = control plane
Container = execution plane
```

Runs on host:
- Warlock daemon
- Airlock policy engine
- config registry
- logs
- Discord control bot

Runs inside container:
- agent runtime
- shell execution
- filesystem access
- tool execution

This separation is mandatory for maintaining the security model.

---

# MVP Definition

The MVP is operational when the system can:

1. Launch a generic Docker shell under a profile.
2. Mount only approved registered folders.
3. Apply read-only and read-write mount modes.
4. Toggle network access by profile.
5. Reject dangerous mounts.
6. Show dry-run permission previews.
7. Write session logs.
8. Launch a generic harness through an adapter.
9. Support future harness abstraction cleanly.

---

# Explicit Build Order

## Stage 1 — Generic Docker Shell Launch

Goal:
Prove contained execution.

Deliverable:

```zsh
warlock run --profile default
```

Requirements:
- non-root container user
- no host home mount
- no Docker socket
- baseline restrictions active

---

## Stage 2 — Mount Registry

Goal:
Human-readable named capabilities.

Example:

```zsh
warlock run --profile build --mount project-alpha
```

Rules:
- mounts must be registered
- no arbitrary host paths
- mount permissions capped by registry

---

## Stage 3 — Profiles

Initial profiles:
- safe
- default
- build
- power
- quarantine

Default profile:

```text
SAFE-NET
```

Meaning:
- network enabled
- useful by default
- no unrestricted host access

---

## Stage 4 — Dry Run

Goal:
Visible permissions before execution.

Example:

```zsh
warlock run --dry-run --profile build --mount project-alpha
```

---

## Stage 5 — Session Logging

Log:
- profile
- mounts
- network mode
- container id
- session duration
- exit status

---

## Stage 6 — Safety Validation

Block:
- /
- $HOME
- ~/.ssh
- ~/Library
- Keychains
- browser profiles
- Docker socket

Warn on:
- broad folders
- cloud sync roots
- parent project folders

---

## Stage 7 — Generic Adapter

First adapter:

```text
Generic shell adapter
```

This proves the harness abstraction architecture before Hermes integration.

---

## Stage 8 — Hermes Integration

Hermes integration must occur ONLY through the adapter layer.

Not:
```text
Airlock = Hermes wrapper
```

Instead:
```text
Hermes adapter → Airlock core
```

---

# Repository Structure

```text
warlock-airlock/
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

# Initial Harness Architecture

## harnesses.json

```json
{
  "generic": {
    "type": "shell",
    "start_command": "/bin/bash"
  },
  "hermes": {
    "type": "agent",
    "start_command": "hermes start"
  }
}
```

---

# MVP Acceptance Test

The MVP passes if:

```zsh
warlock run --profile safe
warlock run --profile default
warlock run --profile build --mount project-alpha
warlock run --dry-run --profile build
warlock adapters list
warlock profiles list
warlock mounts list
```

And:
- dangerous mounts blocked
- logs written
- containerized execution works
- network mode changes by profile
- host home directory inaccessible
- adapter abstraction preserved

---

# Explicit Non-MVP Features

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

These belong to post-MVP phases.

---

# MVP Strategic Goal

The MVP is NOT intended to compete with:
- Claude Code
- Codex
- Cursor

Instead, the MVP targets:
- Hermes
- OpenClaw
- NanoClaw
- local/open-source agents
- solo developer power users

Positioning:

```text
Warlock/Airlock corrals local AI agent harnesses.
```

---

# Design Discipline

Keep MVP narrow.

Primary success criteria:
- useful
- understandable
- secure enough
- low-friction
- extensible

The MVP succeeds if it becomes a practical daily-driver permission harness for local agents.
