# Warlock / Airlock — Branding & Product Roadmap Notes

## Working Product Architecture

```text
Warlock = agent runtime/orchestrator
Airlock = permission/governance layer
Breaker = runtime behavioral interruption engine
Quarantine = high-risk execution mode
```

Core framing:

```text
Warlock operates.
Airlock governs.
```

or:

```text
Warlock executes inside Airlock.
```

---

# Product Positioning

This project should NOT be positioned merely as:
- a Docker wrapper
- an AI sandbox
- a security utility

The stronger positioning is:

```text
Local Agent Capability Governance
```

or:

```text
Agent Permission Management Infrastructure
```

Core value proposition:

```text
Useful autonomous agents without unrestricted machine access.
```

---

# Naming System

## Primary Names

| Component | Role |
|---|---|
| Warlock | Agent runtime / orchestrator |
| Airlock | Permission and containment layer |
| Breaker | Behavioral interruption engine |
| Quarantine | High-risk execution mode |

---

# UX / Mental Model

The terminology should map directly to the operational model.

Example:

```zsh
warlock run --profile coding --mount project-alpha
```

Output:

```text
Airlock Profile: POWER
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

---

# Strategic Product Direction

## Phase 1 — MVP

Focus:
- profiles
- scoped mounts
- Docker isolation
- session logging
- explicit permission grants
- temporary capability exposure

Do NOT add:
- autonomous AI risk scoring
- shadow home simulation
- enterprise orchestration
- browser governance

Goal:
Validate the capability-governance workflow.

---

## Phase 2 — Breaker System

### Core Concept

```text
Permissions are dynamically revocable based on runtime behavior.
```

This is materially different from static sandboxing.

The system evaluates:
- expected behavior
vs
- observed behavior

Risk increases when the agent deviates from the expected capability envelope for the task.

---

## Example Breaker Triggers

### Filesystem anomalies
- access to ~/.ssh
- scanning ~/Documents unexpectedly
- recursive enumeration of host filesystem
- attempts to access browser profiles or credential stores

### Privilege escalation
- sudo requests
- Docker socket access attempts
- attempts to modify shell startup files

### Suspicious networking
- outbound traffic to unexpected domains
- bulk uploads
- encoded/encrypted exfiltration patterns

### Destructive behavior
- rm -rf
- chmod -R
- mass file moves/deletes

### Reconnaissance behavior
- ps aux
- launchctl
- netstat
- system profiling unrelated to task

---

## Breaker Responses

Possible automated responses:

```text
- revoke mounts
- disable network
- pause container
- require approval
- terminate session
```

Initial implementation recommendation:
- deterministic heuristics only
- no autonomous AI behavioral scoring initially

---

# Phase 3 — Shadow Home / Decoy Environment

## Concept

Before granting access to the real environment, risky tasks first execute against a synthetic environment containing:
- decoy files
- fake credentials
- synthetic projects
- simulated browser/session artifacts

Purpose:
Observe agent behavior before exposure to the real environment.

---

## Shadow Execution Flow

```text
1. Run against synthetic environment
2. Observe behavior
3. Generate impact report
4. Require approval
5. Re-run against real environment
```

---

## Important Limitation

A shadow environment does NOT prove safety.

A malicious system could behave benignly during testing and attack later.

However, this approach is still highly valuable for detecting:
- accidental overreach
- sloppy tooling
- destructive scripts
- credential scraping attempts
- broad filesystem exploration

---

# Long-Term Strategic Thesis

Most current agent systems focus on:
- static sandboxing
- container isolation
- permission prompts

This project instead focuses on:

```text
dynamic capability governance
```

That distinction may become increasingly important as autonomous local agents become more capable.

---

# Architectural Principle

```text
The mount list IS the permission model.
```

This creates:
- visible permissions
- temporary capability grants
- auditable sessions
- composable security boundaries
- lower accidental exposure risk

---

# Product Category Observation

Harness providers will likely absorb:
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
