# Airlock / Warlock — Post-MVP Specification (v1.0)

This document is the tactical plan for v1.0, the first major evolution following the MVP. It assumes context from:

- [vision_and_strategy.md](vision_and_strategy.md) — positioning, audience, long-term thesis, Phase 3 (Breaker), Phase 4 (Shadow Home)
- [architecture.md](architecture.md) — system architecture, safety policy, adapter schema, config write-protection, agent identity
- [mvp_build_plan.md](mvp_build_plan.md) — MVP scope and capabilities

The MVP proves containerized capability governance, profiles, scoped mounts, safety validation, logging, and harness abstraction. v1.0 extends this into a broader **Local Agent Governance Runtime** focused on multi-agent orchestration, mobile control, harness interoperability, and low-friction capability management.

---

## v1.0 Primary Goals

1. Per-agent capability scoping
2. Discord / mobile control plane
3. Multi-harness adapter rollout
4. MCP gateway direction
5. Session duration as a first-class enforced primitive
6. Image management at runtime
7. Quick-access presets
8. Repo onboarding (docs and setup scripts)

---

## 1. Per-Agent Capability Scoping

### Objective

Move from instance-level permissions to agent-level permissions, allowing different agents within the same harness/runtime to operate under different Airlock policies.

### Architecture

```text
Harness Runtime
  ├── Agent A → Profile: researcher
  ├── Agent B → Profile: build
  ├── Agent C → Profile: ops
  └── Agent D → Profile: quarantine
```

### Example Agent Policy

```json
{
  "agents": {
    "researcher": {
      "profile": "default",
      "mounts": ["research:ro"]
    },
    "coder": {
      "profile": "build",
      "mounts": ["project-alpha:rw"]
    },
    "ops": {
      "profile": "power",
      "mounts": ["agentwork:rw"],
      "approval_required": true
    }
  }
}
```

### Initial v1 Approach

Do NOT implement full autonomous multi-agent orchestration initially. Instead:
- bind agents to Airlock policies
- resolve policy at execution time
- route tool execution through Airlock

Example:

```zsh
warlock run --agent coder
```

Agent identity resolution is the responsibility of the harness adapter — see [architecture.md](architecture.md).

### Approval Flow — Local Path

`approval_required: true` must have a local approval path before the Discord bot exists. Without it, this policy setting is unusable during the v1 build phase.

Local approval mechanism:
- terminal prompt requiring explicit confirmation before session starts
- `--pre-approve` flag for scripted/trusted contexts (logged)
- approval record written to session log

Discord approval is additive to local approval, not a replacement for it.

---

## 2. Discord / Mobile Control Plane

### Objective

Allow safe mobile management of local agents and Airlock policies.

### Architecture

```text
Discord
  ├── Hermes Chat Channel
  │      └── Hermes/OpenClaw/etc
  │
  └── Airlock Control Channel
         └── Warlock Control Bot
                 ↓
            Local Warlock Daemon
                 ↓
            Airlock Policy Engine
                 ↓
            Docker Execution Cells
```

The Airlock control channel must be separate from the agent interaction channel. Agents do not manage their own permissions.

### Control Plane Responsibilities

Warlock bot may:
- start sessions
- stop sessions
- revoke sessions
- request approvals
- display status
- display logs
- switch profiles
- launch named presets

Warlock bot may NOT:
- execute arbitrary shell commands
- mount arbitrary paths
- grant unrestricted permissions
- expose secrets

### Discord Command Model

Initial support:
- slash commands
- optional legacy `!` commands

Preferred direction: slash commands. Reasons:
- structured inputs
- lower parser attack surface
- mobile-friendly UX
- autocomplete/dropdowns
- clearer administrative semantics

### Example Commands

```text
/warlock start
/warlock stop
/warlock status
/warlock revoke
/warlock preset launch
```

### Example Approval Flow

```text
/warlock start
Agent: coder
Profile: power
Mount: project-alpha
Duration: 1h
```

Warlock replies:

```text
Approval Required
Agent: coder
Profile: power
Mount: project-alpha rw
Network: enabled
Expires: 1h from approval

Reply:
approve 4821
```

### Approval Security Requirements

The "approve NNNN" token flow must enforce:
- tokens are single-use and expire after a short window (e.g. 5 minutes)
- approvals are only accepted from the Discord user who initiated the session request
- the bot must validate the approver's Discord user ID against the session record, not just the token
- approval events are written to the session log with approver ID and timestamp

Without these controls the approval flow is vulnerable to token replay and to other server members sending captured tokens.

---

## 3. Multi-Harness Rollout

### Objective

Bring multiple agent harnesses online through the existing adapter layer (defined in [architecture.md](architecture.md)) without coupling Airlock core to any single runtime.

### v1 Adapter Slate

- generic shell adapter (carried forward from MVP)
- Hermes adapter
- OpenClaw adapter
- NanoClaw adapter

Future:
- MCP gateway adapter

The adapter contract and canonical `harnesses.json` schema are defined once in [architecture.md](architecture.md) and apply to all adapters.

---

## 4. MCP Gateway Direction

### Objective

Position Airlock as a capability-governed MCP tool gateway.

### Concept

```text
Harness
   ↓
MCP Tool Request
   ↓
Airlock Policy Engine
   ↓
Controlled Tool Execution
```

This enables:
- harness-neutral integrations
- future-proof interoperability
- centralized capability governance

### Scope Constraint

The MCP gateway is a v1 *direction*, not a v1 *deliverable*. The interface is defined enough to ship without it; the adapter itself remains in the post-v1 backlog.

---

## 5. Session Duration

### Objective

Make time-bounded sessions a first-class, enforced capability primitive — not a soft hint.

### Behavior

- duration is set per-session, per-preset, or per-agent policy
- Warlock enforces termination at expiry: the container is stopped, not just warned
- a configurable warning is issued N minutes before expiry (default: 5 min)
- the session log records: configured duration, actual duration, expiry reason
- dry-run output must always show the effective duration limit

### Duration Hierarchy

```text
session flag (--duration) overrides
  preset duration overrides
    agent policy duration overrides
      profile default duration
        (no duration = unlimited, logged as such)
```

Unlimited sessions must be explicit, not the silent default for misconfigured policies.

---

## 6. Image Management at Runtime

### Objective

Ensure execution images remain known, current, and auditable past the MVP.

### Requirements

The MVP introduces `warlock image build`, `warlock image status`, and image-id logging (see [mvp_build_plan.md](mvp_build_plan.md)). v1 extends this with:

- `warlock image check` to compare current image age against a configurable staleness threshold
- staleness warnings shown at session start when image is older than threshold
- optional auto-rebuild policy per profile

### Rationale

A stale or unknown base image is a silent security failure: policy correctness is meaningless if the contained environment itself is compromised. Image provenance must be treated as part of the security surface, not an ops afterthought.

---

## 7. Quick-Access Presets

### Objective

Reduce friction for common workflows.

### Concept

Presets bundle a harness, agent, profile, mounts, duration, and network policy into one named workflow.

### Example Presets

```text
research-session
coding-session
ops-session
quarantine-review
```

### Example Commands

```zsh
warlock preset launch coding-session
```

or:

```text
/warlock preset launch coding-session
```

### Example Preset Config

```json
{
  "presets": {
    "coding-session": {
      "harness": "hermes",
      "agent": "coder",
      "profile": "build",
      "mounts": ["project-alpha"],
      "duration": "2h"
    }
  }
}
```

---

## 8. Repo Onboarding — Docs and Setup Scripts

### Objective

Ensure that anyone cloning the public repo can get a working Airlock/Warlock environment without friction or guesswork.

### Requirements

The repo must ship with:
- a getting-started guide covering prerequisites (Docker, Python version, supported platforms)
- a setup script or Makefile target that handles environment creation, dependency installation, and initial config scaffolding
- a worked example showing a complete session from `warlock run` through to session log output
- clear documentation of the default security posture and what each profile does
- a note on what is and isn't protected by the containment model (sets accurate expectations)

### Rationale

Users cloning this repo are placing meaningful trust in the system. Docs and setup scripts are not optional polish — they are part of the trust surface. A user who misconfigures the system because the setup process was unclear has weaker containment than intended, which reflects on the product regardless of whether the underlying design is sound.

The setup path should be opinionated: one recommended way to get started, not a menu of options that requires the user to already understand the system.

---

## Operational Philosophy

The safe path must also be:
- fast
- convenient
- understandable

Security systems fail when:
- secure workflows are too painful
- users bypass governance for convenience

Quick-access presets are therefore a security feature as much as a usability feature.

---

## Deferred Features (Post-v1 Backlog)

The following are explicitly out of scope for v1 but tracked for later. Phase 3 (Breaker) and Phase 4 (Shadow Home) are documented in [vision_and_strategy.md](vision_and_strategy.md).

### Mount Picker / File Tree Browser

Human-controlled browsing of the local filesystem for selecting mount targets.

Requirements:
- human-only interaction
- risk labeling
- dangerous path warnings
- ro/rw assignment
- named capability registration

Agents themselves should not browse the host filesystem tree.

### MCP-Native Governance Layer

Airlock becomes a governed MCP execution runtime for arbitrary harnesses.

### GUI / Desktop Application

Features:
- visual mount picker
- session dashboard
- risk indicators
- profile management
- approval dialogs
- mobile pairing

### VM-Based Execution Backends

Alternative execution environments:
- Firecracker
- Apple Virtualization Framework
- lightweight microVMs

### Credential Mediation Layer

Instead of exposing raw secrets:
- scoped credential grants
- operation-limited credentials
- temporary tokens
- approval-gated secrets

### Session Replay / Audit Visualization

Visual review of:
- commands
- mounts
- network access
- approvals
- breaker events
