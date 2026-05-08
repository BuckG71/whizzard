# Warlock / Airlock Post-MVP v2.0 Specification

Date: 2026-05-08

## Purpose

This document defines the first major post-MVP evolution of Warlock/Airlock.

MVP proves:
- containerized capability governance
- profiles
- scoped mounts
- safety validation
- logging
- harness abstraction

v1.0 extends the system into a broader:

```text
Local Agent Governance Runtime
```

focused on:
- multi-agent orchestration
- mobile control
- harness interoperability
- low-friction capability management

---

# Core Architectural Principle

```text
Warlock controls capabilities.
Agents request capabilities.
Agents do not grant themselves capabilities.
```

This remains the foundational trust model across:
- Discord control plane
- per-agent policies
- harness adapters
- MCP integrations
- future breaker systems

## Config Write-Protection Invariant

The Warlock config directory (profiles.json, mounts.json, harnesses.json, agents.json) must never be reachable from any agent-writable mount path, regardless of what policy files specify.

This is enforced at the safety validation layer, not the policy layer. An agent that can write files Airlock reads can influence its own policies — violating the foundational trust model. This rule cannot be overridden by profiles or presets.

---

# v1.0 Primary Goals

v1.0 introduces:

1. Per-agent capability scoping
2. Discord/mobile control plane
3. Multi-harness adapter architecture
4. MCP gateway direction
5. Session duration as a first-class enforced primitive
6. Image management
7. Improved usability and operational workflows

---

# 1. Per-Agent Capability Scoping

## Objective

Move from:
```text
instance-level permissions
```

to:
```text
agent-level permissions
```

This allows different agents within the same harness/runtime to operate under different Airlock policies.

---

## Architecture

```text
Harness Runtime
  ├── Agent A → Profile: researcher
  ├── Agent B → Profile: build
  ├── Agent C → Profile: ops
  └── Agent D → Profile: quarantine
```

---

## Example Agent Policy

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

---

## Initial v1 Approach

Do NOT implement full autonomous multi-agent orchestration initially.

Instead:
- bind agents to Airlock policies
- resolve policy at execution time
- route tool execution through Airlock

Example:

```zsh
warlock run --agent coder
```

## Agent Identity Challenge

Per-agent policies require Airlock to know *which agent* is making a tool call at runtime. This is non-trivial for harnesses Airlock does not own. The adapter layer is responsible for agent identity resolution — Airlock core must not assume identity is available.

Initial approach: adapter tags tool execution with agent identity at the harness boundary. Airlock trusts the adapter's identity claim. Full cryptographic identity verification is a future problem.

## Approval Flow — Local Path

`approval_required: true` must have a local approval path before the Discord bot exists. Without it, this policy setting is unusable during the v1 build phase.

Local approval mechanism:
- terminal prompt requiring explicit confirmation before session starts
- `--pre-approve` flag for scripted/trusted contexts (logged)
- approval record written to session log

Discord approval is additive to local approval, not a replacement for it.

---

# 2. Discord / Mobile Control Plane

## Objective

Allow safe mobile management of local agents and Airlock policies.

---

## Architecture

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

Critical rule:

```text
Agents do not manage their own permissions.
```

The Airlock control channel is separate from the agent interaction channel.

---

## Control Plane Responsibilities

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

---

## Discord Command Model

Initial support:
- slash commands
- optional legacy !commands

Preferred direction:
```text
slash commands
```

Reason:
- structured inputs
- lower parser attack surface
- mobile-friendly UX
- autocomplete/dropdowns
- clearer administrative semantics

---

## Example Commands

```text
/warlock start
/warlock stop
/warlock status
/warlock revoke
/warlock preset launch
```

---

## Example Approval Flow

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

## Approval Security Requirements

The "approve NNNN" token flow must enforce:
- tokens are single-use and expire after a short window (e.g. 5 minutes)
- approvals are only accepted from the Discord user who initiated the session request
- the bot must validate the approver's Discord user ID against the session record, not just the token
- approval events are written to the session log with approver ID and timestamp

Without these controls the approval flow is vulnerable to token replay, and to another server member sending a captured token.

---

# 3. Multi-Harness Compatibility

## Objective

Support multiple agent harnesses without coupling Airlock core to any single runtime.

---

## Critical Rule

```text
No harness-specific logic belongs in Airlock core.
```

---

## Adapter Model

```text
Airlock Core
    ↓
Harness Adapter
    ↓
Hermes/OpenClaw/NanoClaw/etc
```

---

## Initial Adapters

### MVP+
- generic shell adapter

### v1
- Hermes adapter
- OpenClaw adapter
- NanoClaw adapter

### Future
- MCP gateway adapter

---

## Adapter Responsibilities

Adapters:
- launch harness
- stop harness
- inject config/workspace
- identify agents
- route tool execution
- expose capability boundaries

---

## Example Harness Config

The v1 adapter schema must be versioned and extended beyond the MVP skeleton. Required fields for real adapters:

```json
{
  "schema_version": 1,
  "harnesses": {
    "hermes": {
      "type": "agent",
      "start_command": "hermes start",
      "stop_command": "hermes stop",
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

All fields beyond `type` and `start_command` are optional but the schema must support them from v1. Adding them later is a breaking config change.

---

# 4. MCP Gateway Direction

## Objective

Position Airlock as a capability-governed MCP tool gateway.

---

## Concept

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

---

## Important Scope Constraint

MCP gateway is:
```text
post-MVP v1 direction
```

not:
```text
MVP requirement
```

---

# 5. Session Duration

## Objective

Make time-bounded sessions a first-class, enforced capability primitive — not a soft hint.

---

## Behavior

- duration is set per-session, per-preset, or per-agent policy
- Warlock enforces termination at expiry: the container is stopped, not just warned
- a configurable warning is issued N minutes before expiry (default: 5 min)
- the session log records: configured duration, actual duration, expiry reason
- dry-run output must always show the effective duration limit

## Duration Hierarchy

```text
session flag (--duration) overrides
  preset duration overrides
    agent policy duration overrides
      profile default duration
        (no duration = unlimited, logged as such)
```

Unlimited sessions must be explicit, not the silent default for misconfigured policies.

---

# 6. Image Management

## Objective

Ensure execution images are known, current, and auditable.

---

## Requirements

- base image digest pinned in Dockerfile (no floating tags)
- `warlock image build` to build/rebuild from source
- `warlock image status` to display image id, build timestamp, base digest
- session log records the image id for each session
- `warlock image check` to compare current image age against a configurable staleness threshold

## Rationale

A stale or unknown base image is a silent security failure: policy correctness is meaningless if the contained environment itself is compromised. Image provenance must be treated as part of the security surface, not an ops afterthought.

---

# 8. Quick Access Presets

## Objective

Reduce friction for common workflows.

---

## Concept

Presets bundle:
- harness
- agent
- profile
- mounts
- duration
- network policy

into one named workflow.

---

## Example Presets

```text
research-session
coding-session
ops-session
quarantine-review
```

---

## Example Commands

```zsh
warlock preset launch coding-session
```

or:

```text
/warlock preset launch coding-session
```

---

## Example Preset Config

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

# Operational Philosophy

The safe path must also be:
- fast
- convenient
- understandable

Security systems fail when:
- secure workflows are too painful
- users bypass governance for convenience

Quick-access presets are therefore a security feature as much as a usability feature.

---

# Future Feature Backlog

The following features are intentionally deferred beyond v1.

---

# V2+ Feature Backlog

## 1. Mount Picker / File Tree Browser

Human-controlled browsing of local filesystem for selecting mount targets.

Requirements:
- human-only interaction
- risk labeling
- dangerous path warnings
- ro/rw assignment
- named capability registration

Important:
Agents themselves should not browse the host filesystem tree.

---

## 2. Shadow Home / Decoy Environment

Run risky tasks against:
- synthetic files
- fake credentials
- decoy browser artifacts
- simulated projects

before exposing real environment.

Purpose:
Behavioral preflight testing.

---

## 3. Breaker Runtime Engine

Dynamic capability revocation based on observed behavior.

Potential triggers:
- credential access attempts
- broad filesystem scans
- unexpected networking
- privilege escalation
- destructive operations

Potential actions:
- revoke mounts
- disable network
- pause session
- terminate container

---

## 4. MCP-Native Governance Layer

Airlock becomes:
```text
governed MCP execution runtime
```

for arbitrary harnesses.

---

## 5. GUI / Desktop Application

Features:
- visual mount picker
- session dashboard
- risk indicators
- profile management
- approval dialogs
- mobile pairing

---

## 6. VM-Based Execution Backends

Alternative execution environments:
- Firecracker
- Apple Virtualization Framework
- lightweight microVMs

---

## 7. Credential Mediation Layer

Instead of exposing raw secrets:
- scoped credential grants
- operation-limited credentials
- temporary tokens
- approval-gated secrets

---

## 8. Session Replay / Audit Visualization

Visual review of:
- commands
- mounts
- network access
- approvals
- breaker events

---

# Strategic Positioning

Warlock/Airlock is NOT:
- another agent harness
- another chatbot
- another coding assistant

It is:

```text
A local capability governance layer for autonomous AI systems.
```

---

# Intended Audience

Primary users:
- solo developers
- AI power users
- local agent enthusiasts
- security-conscious tinkerers
- open-source agent operators

Not initially targeted at:
- enterprise IAM
- SOC2 environments
- centralized corporate governance

---

# Long-Term Thesis

As local AI agents become more capable, users will increasingly need:

```text
practical capability governance
```

rather than:
- unrestricted trust
or
- unusably restrictive sandboxes

Warlock/Airlock attempts to occupy the middle ground:
- useful enough to matter
- controlled enough to trust
- simple enough to use daily
