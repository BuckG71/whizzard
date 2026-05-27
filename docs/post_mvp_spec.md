# Whizzard — Post-MVP Specification (v1.0)

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

Move from instance-level permissions to agent-level permissions, allowing different agents within the same harness/runtime to operate under different Whizzard policies.

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
- bind agents to Whizzard policies
- resolve policy at execution time
- route tool execution through Whizzard

Example:

```zsh
whizzard run --agent coder
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

Allow safe mobile management of local agents and Whizzard policies.

### Architecture

```text
Discord
  ├── Hermes Chat Channel
  │      └── Hermes/OpenClaw/etc
  │
  └── Whizzard Control Channel
         └── Whizzard Control Bot
                 ↓
            Local Whizzard Daemon
                 ↓
            Whizzard Policy Engine
                 ↓
            Docker Execution Cells
```

The Whizzard control channel must be separate from the agent interaction channel. Agents do not manage their own permissions.

### Control Plane Responsibilities

Whizzard bot may:
- start sessions
- stop sessions
- revoke sessions
- request approvals
- display status
- display logs
- switch profiles
- launch named presets

Whizzard bot may NOT:
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
/whizzard start
/whizzard stop
/whizzard status
/whizzard revoke
/whizzard preset launch
```

### Example Approval Flow

```text
/whizzard start
Agent: coder
Profile: power
Mount: project-alpha
Duration: 1h
```

Whizzard replies:

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

Bring multiple agent harnesses online through the existing adapter layer (defined in [architecture.md](architecture.md)) without coupling Whizzard core to any single runtime.

### v1 Adapter Slate

- generic shell adapter (carried forward from MVP)
- Hermes adapter
- OpenClaw adapter
- NanoClaw adapter

Future:
- MCP gateway adapter

The adapter contract and canonical `harnesses.json` schema are defined once in [architecture.md](architecture.md) and apply to all adapters.

### Adapter Spec — Contributor-Facing Artifact (D-160)

The adapter Protocol (D-28) is exposed as a versioned `ADAPTER_SPEC.md` document at OSS-launch, separate from `whizzard.adapters.base` (which remains the canonical Python implementation). The spec describes contract semantics in language-neutral terms — lifecycle hooks, `container_mounts`, `container_env`, `mcp_env`, `wrap_up` timing, preflight expectations — so third-party adapter authors can build against a stable, readable contract without navigating the source tree.

Requirements:
- Single-file document at repo root: `ADAPTER_SPEC.md`
- Carries a `SPEC_VERSION` independent of the package version
- Lists every method on the adapter Protocol with: contract semantics, return shape, when called by core, failure modes
- Documents `harnesses.json` and any other shared schemas adapters consume
- Includes a minimal worked example (probably the generic shell adapter)
- Treated as a release-gate artifact: any change requires an explicit `SPEC_VERSION` bump and changelog entry

Rationale: see D-160. Symphony's SPEC.md-first model demonstrates that contributor-driven ecosystem growth works when the contract is a versioned, language-neutral artifact rather than an in-tree language binding.

---

## 4. MCP Gateway Direction

### Objective

Position Whizzard as a capability-governed MCP tool gateway.

### Concept

```text
Harness
   ↓
MCP Tool Request
   ↓
Whizzard Policy Engine
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
- Whizzard enforces termination at expiry: the container is stopped, not just warned
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

### v1 Additions to Duration Handling

The MVP ships with enforced expiry plus harness-native wrap-up via `adapter.wrap_up()` (see [architecture.md](architecture.md) and [mvp_build_plan.md](mvp_build_plan.md)). v1 extends the surrounding UX:

- **Extend-session prompt**: at N minutes before expiry (default 5), prompt the user — terminal locally, Discord remotely — with "extend by X?" Default extension X is configurable per profile.
- **Maximum-extension cap**: each profile declares a hard ceiling on total session duration so extensions cannot accumulate indefinitely.
- **`/whizzard extend <session-id> <duration>`**: Discord command to extend an active session from mobile.
- **Adapter `pre_terminate` hook**: a richer adapter callback (distinct from `wrap_up`) that runs before wrap_up and lets the adapter perform structured state checkpointing — e.g., serializing the harness's conversation history to a mounted volume so a follow-up session can resume.
- **Auto-extend on user activity**: optional per-profile setting to extend automatically when the user is actively interacting (vs idle). Off by default; opt-in only.

Session checkpointing (full serialize/resume across sessions) is v2 work; v1 only provides the hooks for it.

---

## 6. Image Management at Runtime

### Objective

Ensure execution images remain known, current, and auditable past the MVP.

### Requirements

The MVP introduces `whizzard image build`, `whizzard image status`, and image-id logging (see [mvp_build_plan.md](mvp_build_plan.md)). v1 extends this with:

- `whizzard image check` to compare current image age against a configurable staleness threshold
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
whizzard preset launch coding-session
```

or:

```text
/whizzard preset launch coding-session
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

Ensure that anyone cloning the public repo can get a working Whizzard/Whizzard environment without friction or guesswork.

### Requirements

The repo must ship with:
- a getting-started guide covering prerequisites (Docker, Python version, supported platforms)
- a setup script or Makefile target that handles environment creation, dependency installation, and initial config scaffolding
- a worked example showing a complete session from `whizzard run` through to session log output
- clear documentation of the default security posture and what each profile does
- a note on what is and isn't protected by the containment model (sets accurate expectations)

### Rationale

Users cloning this repo are placing meaningful trust in the system. Docs and setup scripts are not optional polish — they are part of the trust surface. A user who misconfigures the system because the setup process was unclear has weaker containment than intended, which reflects on the product regardless of whether the underlying design is sound.

The setup path should be opinionated: one recommended way to get started, not a menu of options that requires the user to already understand the system.

---

## 9. Orchestrator Integration API

### Objective

Expose a programmatic launch surface (Python library first) so external orchestrators — task-board systems like Symphony, custom job runners, supervised agent swarms — can spawn and supervise OIQ cells without shelling out to the CLI.

### Concept

The CLI surface is designed for human-driven, one-cell-at-a-time use. The library surface is designed for automated, supervisor-driven, many-cells-at-a-time use. Both call into the same core; the library is the lower-friction binding for orchestration patterns.

Minimum v1.0 surface:

```python
import oiq

# Launch a cell. Returns a session handle.
handle = oiq.launch(
    harness="hermes-cell",
    preset="default",
    session_id=None,     # auto-generated if omitted; supplied for restart-on-crash
    on_exit=callback,    # optional callback fired at session_end
)

# Poll lifecycle / health.
status = oiq.status(handle.session_id)
# → SessionStatus(state="running" | "exited" | "missing", exit_code=..., ...)

# Explicit termination (otherwise SIGTERM via wrap_up at duration).
oiq.terminate(handle.session_id, grace_seconds=30)
```

### Design Constraints

- **Library API only at v1.0** — no daemon, no supervisor process. OIQ stays a containment layer; orchestration is the orchestrator's job (D-159 rationale).
- **Reuses existing core** — same profiles, presets, mounts, harness adapters, session-log JSONL. The library is a new entry point, not a new code path.
- **Session-id-keyed** — orchestrators rely on stable session IDs for restart-on-crash semantics; the API exposes IDs explicitly rather than hiding them in opaque handles.
- **Errors are exceptions, not exit codes** — structured failure surface is the main value over shelling out to `whiz r`.
- **Sync API first; async wrapper later** — most orchestrators already have their own concurrency model and prefer driving a sync API from inside their event loop.

### Out of Scope for v1.0

- Async / coroutine-native API (deferred until a real orchestrator demands it)
- Remote launch (cells stay local-first per D-9; remote orchestration is a different product)
- Cross-language bindings (Python is the reference; other languages can land later if needed)
- A built-in supervisor / restart loop (that's the orchestrator's job, not OIQ's)

### Rationale

See D-159. Symphony (InfoQ 2026-05) demonstrates the orchestration layer above harnesses; OIQ wants to be the containment substrate those orchestrators plug into. A CLI-only entry forces brittle shell-out integration; a library API is the minimum viable interop surface.

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

Whizzard becomes a governed MCP execution runtime for arbitrary harnesses.

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

### Vault-Mediated Credentials

Adopt the OneCLI Agent Vault pattern, as implemented by [NanoClaw](https://docs.nanoclaw.dev/introduction). Real API credentials never enter the container; outbound HTTPS is routed through a host-side gateway that matches requests by host and path, injects the real credential at request time, and forwards. The agent never holds, sees, or can exfiltrate the credential — it is absent from env vars, files, stdin, and `/proc`.

Architecture:

```text
Agent (in container)
  ↓ outbound HTTPS request with placeholder/no credential
Vault Gateway (on host)
  ↓ matches request, looks up real credential, applies per-agent policy
External service
```

Properties:
- credentials never enter the container, even when access is granted
- per-agent policy at the gateway (allowed hosts/paths, rate limits, scopes)
- credential rotation is gateway-only — containers never need updating
- every credential use is logged at the gateway, independent of agent log
- pairs with the Phase 4 Shadow Home (vision_and_strategy.md): shadow-test new agents before exposure, then run them in production with vault-mediated credentials. They solve different problems — Shadow Home is observational ("we'd have caught this"), the vault is architectural ("the agent literally cannot exfiltrate").

Implementation direction: integrate with an existing vault implementation (OneCLI, HashiCorp Vault, or similar) rather than build from scratch. Whizzard's job is to wire the container's network through the vault; the credential storage and policy engine are someone else's well-tested problem.

Reference implementations:
- [NanoClaw Agent Vault blog post](https://nanoclaw.dev/blog/nanoclaw-agent-vault/)
- [NanoClaw security model](https://github.com/qwibitai/nanoclaw/blob/main/docs/SECURITY.md)

### Session Replay / Audit Visualization

Visual review of:
- commands
- mounts
- network access
- approvals
- breaker events

### Session Log Analytics Surface

Queryable analytics over the existing `~/.whizzard/sessions.jsonl` log (Stage 5, `whizzard/session_log.py`). The storage shape — append-only JSONL with `session_start` / `session_end` / `agent_events` — is already in place; this entry is just the read-side query layer on top.

Pattern reference: the `AuditLogger` in the public ["Control Layer" article](https://towardsdatascience.com/prompt-engineering-isnt-enough-i-built-a-control-layer-that-works-in-production/) pairs an append-only JSONL with an in-memory index that exposes `failure_distribution()`, `pass_rate()`, and P50/P90/P99 latency percentiles. Whizzard's metrics are different (its domain isn't LLM-call reliability), but the *shape* — in-memory index over the JSONL, rebuilt on startup, queryable via a small Python surface — transfers cleanly.

Whizzard-domain metrics worth surfacing:
- expiry-reason distribution (clean / duration / idle) across the last N sessions or last X days
- denied-capability-request distribution by adapter, profile, and request type (D-165 request channel + D-163 adjust path)
- mount-usage distribution — which named capabilities actually get used vs. granted-but-untouched
- session duration percentiles (P50/P90/P99) per profile
- idle-end rate per profile (input to Stage 15 idle-timeout tuning)

Likely surfaces:
- `whiz stats <metric>` CLI subcommands for the common views
- a Python query module (`whizzard.session_log.analytics` or similar) for programmatic use
- thread-safe read alongside the existing append-only write path

Out of scope for this entry: visualization (covered by "Session Replay / Audit Visualization" above) and any change to the on-disk log format.

Surfaced by: 2026-05-23 review of the "Control Layer" article (chat-only; no decision entry — per D-24 / D-26 the article's LLM-call middleware sits on the harness side of the boundary, but its audit/analytics shape is borrowable).

### Memory governance for agent harnesses

See internal doc.
