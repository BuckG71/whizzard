# Whizzard — Vision & Strategy

This document is the single source of truth for what Whizzard is, who it serves, and where it is going. Tactical plans live in [mvp_build_plan.md](mvp_build_plan.md) and [post_mvp_spec.md](post_mvp_spec.md). System architecture lives in [architecture.md](architecture.md).

> Naming note: earlier drafts used a two-name framing ("Airlock" = containment, "Whizzard" = orchestrator). Project consolidated to single name "Whizzard" on 2026-05-09 (D-144). "Whizzard" is itself a working placeholder; long-term name TBD.

---

## Core Thesis

Whizzard is a local-first capability governance layer for running powerful AI agents (and, post-MVP, general OSS tools) with explicit, temporary, human-readable permission boundaries.

The system exists to prove:

```text
Useful autonomous agents can coexist with practical local security boundaries.
```

---

## Naming System

| Component       | Role                                              |
|-----------------|---------------------------------------------------|
| Whizzard        | The whole system: orchestrator, policy engine, containment |
| Execution Cell  | The contained execution environment (Docker container in MVP) |
| Harness Adapter | Integration layer for Hermes / OpenClaw / NanoClaw / etc. |
| Breaker         | Behavioral interruption engine (post-MVP)         |
| Quarantine      | High-risk execution mode (a profile name)         |

---

## Product Positioning

This project should NOT be positioned as:
- another agent harness
- another chatbot
- another coding assistant
- a Docker wrapper
- a generic AI sandbox
- a security utility

Stronger positioning:

```text
A local capability governance layer for autonomous AI systems.
```

or:

```text
Agent Permission Management Infrastructure
```

Core value proposition:

```text
Useful autonomous agents without unrestricted machine access.
```

### Competitive Framing

Whizzard is NOT intended to compete with:
- Claude Code
- Codex
- Cursor

It targets:
- Hermes
- OpenClaw
- NanoClaw
- local/open-source agents
- solo developer power users

Tagline:

```text
Whizzard corrals local AI agent harnesses.
```

---

## Intended Audience

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

Enterprise-grade governance may follow, but is explicitly not the v1 audience.

---

## UX / Mental Model

The terminology should map directly to the operational model.

Example:

```zsh
whizzard run --profile coding --mount project-alpha
```

Output:

```text
Whizzard Profile: POWER
Network: ENABLED
Filesystem: project-alpha (rw)
Breaker: ACTIVE
Session Logging: ENABLED
```

Breaker event:

```text
BREAKER TRIGGERED

Reason:
Unexpected access attempt to ~/.ssh

Action Taken:
Network disabled
Session paused
Approval required
```

### The Mount List IS the Permission Model

Capability grants in Whizzard are not abstract policy declarations — they are the literal list of mounts and toggles a user sees before launch. This creates:

- visible permissions
- temporary capability grants
- auditable sessions
- composable security boundaries
- lower accidental exposure risk

Users should be able to read their own permissions at a glance and trust that what they see is what is granted.

---

## Strategic Product Direction

### Phase 1 — MVP

Focus:
- profiles
- scoped mounts
- Docker isolation
- session logging
- explicit permission grants
- temporary capability exposure

Goal: validate the capability-governance workflow.

See [mvp_build_plan.md](mvp_build_plan.md) for details.

### Phase 2 — Post-MVP v1.0

Focus:
- per-agent capability scoping
- Discord/mobile control plane
- multi-harness adapter architecture
- MCP gateway direction
- session duration as first-class primitive
- image management
- presets and onboarding

See [post_mvp_spec.md](post_mvp_spec.md) for details.

### Phase 3 — Breaker System

Core concept:

```text
Permissions are dynamically revocable based on runtime behavior.
```

This is materially different from static sandboxing. The system evaluates expected behavior vs observed behavior. Risk increases when an agent deviates from its expected capability envelope for the task.

#### Example Breaker Triggers

Filesystem anomalies:
- access to `~/.ssh`
- scanning `~/Documents` unexpectedly
- recursive enumeration of host filesystem
- attempts to access browser profiles or credential stores

Privilege escalation:
- sudo requests
- Docker socket access attempts
- attempts to modify shell startup files

Suspicious networking:
- outbound traffic to unexpected domains
- bulk uploads
- encoded/encrypted exfiltration patterns

Destructive behavior:
- `rm -rf`
- `chmod -R`
- mass file moves/deletes

Reconnaissance behavior:
- `ps aux`
- `launchctl`
- `netstat`
- system profiling unrelated to task

#### Breaker Responses

Possible automated responses:
- revoke mounts
- disable network
- pause container
- require approval
- terminate session

Initial implementation recommendation:
- deterministic heuristics only
- no autonomous AI behavioral scoring initially

### Phase 4 — Shadow Home / Decoy Environment

Concept: before granting access to the real environment, risky tasks first execute against a synthetic environment containing decoy files, fake credentials, synthetic projects, and simulated browser/session artifacts.

Purpose: observe agent behavior before exposure to the real environment.

#### Shadow Execution Flow

```text
1. Run against synthetic environment
2. Observe behavior
3. Generate impact report
4. Require approval
5. Re-run against real environment
```

#### Important Limitation

A shadow environment does NOT prove safety. A malicious system could behave benignly during testing and attack later.

It is still highly valuable for detecting:
- accidental overreach
- sloppy tooling
- destructive scripts
- credential scraping attempts
- broad filesystem exploration

---

## Long-Term Strategic Thesis

Most current agent systems focus on:
- static sandboxing
- container isolation
- permission prompts

Whizzard instead focuses on:

```text
dynamic capability governance
```

As autonomous local agents become more capable, users will increasingly need practical capability governance — rather than unrestricted trust or unusably restrictive sandboxes.

Whizzard attempts to occupy the middle ground:
- useful enough to matter
- controlled enough to trust
- simple enough to use daily

### Product Category Observation

Harness providers (Claude Code, Codex, Cursor, etc.) will likely absorb:
- basic sandboxing
- workspace permissions
- command approval prompts

The durable opportunity may instead be:

```text
Cross-agent local capability governance.
```

Especially:
- local-first
- harness-neutral
- human-readable
- temporary
- behavior-aware
