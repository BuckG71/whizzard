# Airlock / Whizzard — System Architecture

This document defines the system architecture, security invariants, and adapter contract for Airlock/Whizzard. It applies across all phases of the project — MVP, v1, and beyond.

---

## Core Architectural Principle

```text
Whizzard controls capabilities.
Agents request capabilities.
Agents do not grant themselves capabilities.
```

This is the foundational trust model. It applies to profiles, mounts, harness adapters, the Discord control plane, the breaker engine, and any future MCP integration.

---

## System Components

```text
Whizzard         = local orchestrator / launcher
Airlock         = policy and containment layer
Execution Cell  = the contained execution environment (Docker container in MVP)
Harness Adapter = integration layer for Hermes / OpenClaw / etc.
```

Verbal framing:

```text
Whizzard operates.
Airlock governs.
```

or:

```text
Whizzard executes inside Airlock.
```

---

## Architecture Layers

### 1. Airlock Core

Responsibilities:
- profiles
- mount registry
- policy resolution
- container execution
- network controls
- safety validation
- session logging
- dry-run preview

Airlock core must remain harness-neutral. It must know nothing about:
- Hermes internals
- OpenClaw internals
- Discord bots
- MCP specifics

This is the most important architectural rule. **No harness-specific logic belongs in Airlock core.**

### 2. Harness Adapter Layer

Adapters translate harness-specific behavior into Airlock-compatible execution.

Responsibilities:
- launch harness
- stop harness
- inject workspace/config
- identify agents at the harness boundary
- route tool execution through Airlock
- expose capability boundaries
- **wrap up the harness gracefully before container termination, using harness-native means**

The wrap-up step is required from MVP, not deferred to v1. When a session is about to end (duration expiry, user-initiated stop, or safety termination), Airlock invokes `adapter.wrap_up(grace_seconds)` *before* sending SIGTERM. The adapter's job is to give the harness a chance to finalize its own state via whatever mechanism that harness provides — for example, Hermes has a wrap-up slash command. The grace period is bounded so wrap-up cannot block termination indefinitely.

The generic shell adapter implements `wrap_up()` as a no-op (no agent state to preserve). Harness-specific adapters (Hermes, etc.) implement it meaningfully.

Initial adapters:
- generic shell adapter (MVP)
- Hermes adapter (post-MVP)
- OpenClaw adapter (post-MVP)
- NanoClaw adapter (post-MVP)

Future:
- MCP gateway adapter

### 3. Execution Backend Layer

MVP backend:
- Docker

Future backends:
- Podman
- Firecracker
- Apple Virtualization Framework
- cloud execution cells

The execution backend is intentionally abstracted so that future migrations do not require changes to Airlock Core or the Harness Adapter Layer.

---

## Host vs Container Boundary

```text
Host machine = control plane
Container    = execution plane
```

Runs on host:
- Whizzard daemon
- Airlock policy engine
- config registry
- logs
- Discord control bot (post-MVP)

Runs inside container:
- agent runtime
- shell execution
- filesystem access (only via registered mounts)
- tool execution

This separation is mandatory for maintaining the security model.

---

## Control Layering

Whizzard's controls compose in three concentric layers. Each layer has a different shape, a different enforcement mechanism, and a different owner. They do not collapse into each other.

```text
┌─ Outer (Whiz pre-session enforcement) ────────────────┐
│  Mounts, network, capabilities, image, hardening,     │
│  duration. Set at launch via container flags.         │
│  Agent can never reach or modify these directly.      │   ← enforcement layer
│  Kernel / Docker enforce.                             │
│                                                       │
│  ┌─ Inner (harness — Hermes/NanoClaw/etc) ─────────┐  │
│  │  Dangerous-command approval, tool intent gating,│  │   ← behavioral layer
│  │  /yolo, smart-mode aux LLM, etc.                │  │     (HARNESS-NATIVE
│  │  Whiz does NOT recreate these.                  │  │      — don't recreate)
│  │                                                 │  │
│  │  ┌─ Whiz MCP server (in-container surface) ──┐  │  │
│  │  │  Status / self-audit / event emission /  │  │  │   ← cooperation layer
│  │  │  capability-change requests (which       │  │  │     (agent-facing API
│  │  │  trigger outer-layer changes via         │  │  │      to Whiz host brain)
│  │  │  stop+restart)                           │  │  │
│  │  └──────────────────────────────────────────┘  │  │
│  └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

### Enforcement layer (outer, Whizzard-owned)

Set at container launch via Docker flags and container configuration. Includes mount visibility and modes, network policy, capability drops, image identity, container hardening, and session duration. The agent never sees these as configurable surfaces — they exist before the agent does, and changing them requires stop+restart. Enforced by the kernel and Docker, not by the agent or harness.

This is the layer where Whizzard's safety policy operates, and the layer that harnesses do not address themselves.

### Behavioral layer (inner, harness-owned)

Dangerous-command interception, in-session approval flows, tool intent gating, `/yolo`-style bypass mechanisms. These exist inside the harness and are intent-time, fine-grained decisions. Hermes and NanoClaw both ship robust versions of this layer.

**Whizzard does not recreate these controls.** Recreating them would duplicate harness work and add surface area the harness already maintains. Layering is the discipline: structural posture is Whizzard's job, behavioral interception is the harness's.

### Cooperation layer (innermost, Whizzard-exposed via MCP)

A first-class part of the design. MCP support is treated as a baseline harness capability, not a per-adapter feature flag. Exposes a small set of agent-facing tools that let the running agent introspect its own constraints, write structured audit entries, and request structural changes. Capability-change requests are mediated by Whizzard host-side and applied via stop+restart of the container.

The cooperation layer never replaces the enforcement layer; it is a structured, agent-visible interface to the host-side capability brain. The full cooperation-layer tool surface is documented in [control_surface.md](control_surface.md).

### Composition rule

Each layer does what the others cannot. The enforcement layer determines what the agent could possibly do; the behavioral layer determines what the agent will be allowed to attempt within that envelope; the cooperation layer determines what the agent can ask Whizzard to change about the envelope. Mixing layers — recreating harness approval at the enforcement layer, or exposing structural controls as MCP-modifiable from inside the agent — breaks the model.

---

## Config Write-Protection Invariant

The Whizzard config directory (`profiles.json`, `mounts.json`, `harnesses.json`, `agents.json`) must never be reachable from any agent-writable mount path, regardless of what policy files specify.

This is enforced at the safety validation layer, not the policy layer. An agent that can write files Airlock reads can influence its own policies — violating the foundational trust model. This rule cannot be overridden by profiles or presets.

---

## Safety Policy

Safety validation classifies mount targets into three tiers:

### Hard block (no override)

- `/`
- `$HOME`
- `~/.ssh`
- `~/Library`
- Keychains
- browser profiles
- Docker socket
- Whizzard config directory

### Hard block with explicit override

Requires `--allow-broad-mount` and is logged to the session record:

- broad folders (e.g. `~/Documents`, `~/Desktop`, `~/Projects`)
- cloud sync roots (iCloud Drive, Dropbox, OneDrive)
- parent directories of registered mount targets

### Allowed

- registered mounts within `mounts.json` whose paths fall outside the above

The override mechanism is intentional friction. Warnings are not used because they tend to be ignored; the right gate is "block by default, require explicit user action to proceed, log every override."

---

## Harness Adapter Schema

`harnesses.json` defines all harnesses Airlock can launch via the adapter layer.

```json
{
  "schema_version": 1,
  "harnesses": {
    "generic": {
      "type": "shell",
      "start_command": "/bin/bash"
    },
    "hermes": {
      "type": "agent",
      "start_command": "hermes start",
      "stop_command": "hermes stop",
      "wrap_up_command": "/quit",
      "wrap_up_grace_seconds": 30,
      "working_dir": "~/.hermes",
      "health_check": "hermes status",
      "startup_timeout_seconds": 30,
      "env": {
        "HERMES_MODE": "contained"
      }
    },
    "openclaw": {
      "type": "agent",
      "start_command": "openclaw run",
      "stop_command": "openclaw quit",
      "working_dir": null,
      "health_check": null,
      "startup_timeout_seconds": 15,
      "env": {}
    }
  }
}
```

Required fields: `type`, `start_command`.

Optional fields: `stop_command`, `wrap_up_command`, `wrap_up_grace_seconds`, `working_dir`, `health_check`, `startup_timeout_seconds`, `env`.

The `wrap_up_command` is the string the adapter sends to the harness's interactive interface to trigger graceful wind-down (e.g., a slash command). `wrap_up_grace_seconds` bounds how long Airlock waits for the harness to finish before proceeding to SIGTERM. Adapters whose harnesses do not have a native wrap-up mechanism omit these fields; their `wrap_up()` is a no-op.

The schema is versioned (`schema_version`) so it can be extended without breaking existing configs. The MVP can ship with only `type` and `start_command` populated, but the parser must accept and ignore the optional fields from day one to avoid a breaking config change later.

---

## Agent Identity

Per-agent policies require Airlock to know which agent is making a tool call at runtime. This is non-trivial for harnesses Airlock does not own.

The adapter layer is responsible for agent identity resolution. Airlock core must not assume identity is available.

Initial approach: the adapter tags tool execution with agent identity at the harness boundary. Airlock trusts the adapter's identity claim. Cryptographic identity verification is a future problem.

---

## Architectural Constants

These rules apply to all phases and cannot be relaxed by future work:

- **Capability flow is one-way.** Agents request; Whizzard grants; agents never self-grant.
- **Airlock core stays harness-neutral.** Harness behavior lives in adapters.
- **The mount list IS the permission model.** Visible, named, scoped capability grants are the system's primary affordance.
- **Config integrity is non-negotiable.** Agent-reachable paths cannot include the config directory.
- **Time-bounded sessions are enforced, not advisory.** Duration is a first-class capability primitive.
