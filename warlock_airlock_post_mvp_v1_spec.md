# Warlock / Airlock Post-MVP v1.0 Specification

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

---

# v1.0 Primary Goals

v1.0 introduces:

1. Per-agent capability scoping
2. Discord/mobile control plane
3. Multi-harness adapter architecture
4. MCP gateway direction
5. Improved usability and operational workflows

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

Reply:
approve 4821
```

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

```json
{
  "harnesses": {
    "hermes": {
      "type": "agent",
      "start_command": "hermes start"
    },
    "openclaw": {
      "type": "agent",
      "start_command": "openclaw run"
    }
  }
}
```

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

# 5. Quick Access Presets

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
