# Whizzard Control Surface

The full landscape of structural controls Whizzard could in principle expose, organized by domain. This is the reference map for "what's possible" — narrower scope decisions (what's in MVP, what's in OSS-launch, what's deferred indefinitely) layer on top of it.

Cross-references:
- [architecture.md](architecture.md) — system components, safety policy, adapter schema, foundational invariants
- [post_mvp_spec.md](post_mvp_spec.md) — current v1.0 plan
- [vision_and_strategy.md](vision_and_strategy.md) — long-term direction (Phase 3 Breaker, Phase 4 Shadow Home)
- [hermes_research.md](hermes_research.md), [nanoclaw_research.md](nanoclaw_research.md), [nanoclaw_internals.md](nanoclaw_internals.md) — what existing harnesses already do (don't recreate)

Written: 2026-05-09. Status markers reflect this date and will drift as work progresses.

---

## What this doc is for

Two things kept getting lost in conversation without a single home:

1. **The total surface area Whizzard could in principle control.** Every time we discuss a new feature, we re-derive the list. This is the canonical version.
2. **The line between Whizzard's enforcement layer (structural, pre-session, kernel/Docker-enforced) and Whizzard's cooperation layer (in-session, agent-facing via MCP).** Both matter; they have different shapes and different design constraints.

The intent is that future design discussions can refer to this doc rather than re-survey the space.

---

## Foundational framing — enforcement vs. cooperation

Whizzard exposes two architecturally distinct kinds of control. They look related but they're enforced differently and reachable from different places.

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

**Why this matters for design:**

- Anything in the **enforcement layer** must be set at container launch and is not addressable by the running agent. The agent doesn't know it could ask. Approval flows don't apply (it's a refusal-to-launch, not an in-session decision).
- Anything in the **cooperation layer** is naturally an MCP tool. The agent can call it; Whiz host-side decides; if the decision implies a structural change, host applies it via stop+restart (or, post-MVP, sidecar mechanisms).
- Anything in the **behavioral layer** is the harness's job. Whiz does not recreate Hermes's dangerous-command approval, NanoClaw's MCP gating, etc. We trust harnesses to handle behavioral interception and we layer outside.

**Assumption baseline:** all modern agent harnesses support MCP. We treat this as a given, not an adapter capability flag.

---

## The control surface

Status legend:

- **✓** in MVP today (Stages 1–7 implemented; Stages 8–18 planned for MVP)
- **◐** in post-MVP backlog ([post_mvp_spec.md](post_mvp_spec.md))
- **○** identified but not yet scoped to any milestone
- **✗** harness-native — Whiz must NOT recreate this

### 1. Filesystem

| Item | Status | Notes |
|---|---|---|
| Mount visibility (registry, named capabilities) | ✓ | Stage 2 |
| RO vs RW per mount | ✓ | Stage 2 |
| Hard-block list (no override) | ✓ | Stage 6 |
| Override-required tier (`--allow-broad-mount`) | ✓ | Stage 6 |
| Pattern/extension filtering inside a mount | ○ | e.g. mount allows `*.md` but not `*.key`; needs FUSE shim |
| Decoy/canary file placement | ○ | touched = alarm; defensive |
| Shadow Home (virtualized FS, writes diverted) | ○ | Phase 4 in [vision_and_strategy.md](vision_and_strategy.md) |

### 2. Network

| Item | Status | Notes |
|---|---|---|
| On/off entire egress (profile-driven) | ✓ | Stage 3 |
| Egress allowlist by host/domain | ○ | needs sidecar proxy mechanism |
| Egress allowlist by port | ○ | sidecar proxy |
| HTTPS interception for credential injection | ◐ | OneCLI vault generalization, [post_mvp_spec.md §Vault](post_mvp_spec.md) |
| DNS scoping (resolve only specified domains) | ○ | sidecar / nss-stub |
| Bandwidth or rate caps | ○ | likely enterprise-shaped, deprioritized |

### 3. Process and kernel

| Item | Status | Notes |
|---|---|---|
| Capability drop (ALL) | ✓ | Stage 1 |
| no-new-privileges | ✓ | Stage 1 |
| Read-only rootfs + tmpfs scratch | ✓ | Stage 1 |
| Custom seccomp filter | ○ | currently relying on Docker default |
| AppArmor / SELinux profile | ○ | Linux-only; enterprise-shaped, deprioritized |
| ulimits (CPU, memory, FDs, processes) | ○ | small lift, useful for personal-use |

### 4. Time

| Item | Status | Notes |
|---|---|---|
| Hard duration cap | ✓ planned | logged in MVP via session_log; enforcement at Stage 15 |
| Idle timeout (kill if no activity) | ✓ planned | Stage 15 |
| Time-of-day windows | ○ | enterprise-shaped, deprioritized |
| Mid-session extend prompt | ✓ planned | Stage 14 (`whiz_request_extend`) + Stage 15 enforcement |

### 5. Credentials and secrets

| Item | Status | Notes |
|---|---|---|
| Vault-mediated credentials (OneCLI) | ✓ planned | Stage 12; with env-var fallback when OneCLI not on host |
| Per-domain credential scoping at vault | ○ | OneCLI primitive |
| Per-call rate limits at vault | ○ | OneCLI primitive |
| Credential-use audit (independent of agent log) | ○ | enterprise-shaped, deprioritized |

### 6. Tools / MCP

| Item | Status | Notes |
|---|---|---|
| In-session command approval | ✗ | Hermes / NanoClaw native |
| Tool-level intent gating | ✗ | Hermes / NanoClaw native |
| MCP server allowlist per session (Whiz layer) | ○ | sits *outside* harness-native gating |
| MCP tool allowlist within a server | ○ | sidecar proxy |
| Tool argument/result shaping | ○ | sidecar proxy with redaction |

### 7. Container / image

| Item | Status | Notes |
|---|---|---|
| Hardened base image (non-root, minimal) | ✓ | Stage 1 |
| Digest-pinned base image | ✓ planned | Stage 18 (was Stage 9, then Stage 11, then Stage 17; final per D-143) |
| Staleness check + warning | ◐ | post-MVP §6 |
| Per-session image override | ○ | useful when adapters land for different agent types |

### 8. Identity / multi-agent

| Item | Status | Notes |
|---|---|---|
| Per-agent policy | ◐ | post-MVP §1 |
| Agent identity tagging at harness boundary | ◐ | adapter responsibility, [architecture.md](architecture.md) |
| Cross-agent communication policy | ○ | curator can read X's memory, not Y's |

### 9. Observability

| Item | Status | Notes |
|---|---|---|
| Session audit log (JSONL) | ✓ | Stage 5 |
| Network traffic log | ○ | sidecar proxy |
| File-access log | ○ | FUSE or audit subsystem |
| Session replay visualization | ◐ | post-v1 backlog |
| Whiz MCP `whiz_audit_self` (agent-facing read of own log) | ✓ planned | Stage 9 cooperation-layer subset |
| Whiz MCP `whiz_emit_event` (agent-authored entries) | ✓ planned | Stage 9 |

### 10. Governance / approval

| Item | Status | Notes |
|---|---|---|
| In-session command approval | ✗ | Hermes / NanoClaw native |
| Local TTY approval flow (substrate for request-side MCP) | ✓ planned | Stage 13 |
| Discord control plane — read-only (status, list sessions, tail logs) | ✓ planned | Stage 16 |
| Discord control plane — write/approve (start, stop, extend, switch profile, approve mount) | ✓ planned | Stage 17; single-use time-bounded tokens, identity-bound |
| Multi-party approval | ○ | enterprise-shaped, deprioritized |
| Auto-approve allowlist per profile | ○ | small lift |

### 11. Resource quotas

| Item | Status | Notes |
|---|---|---|
| CPU limits (`--cpus`) | ○ | small lift |
| Memory limits (`--memory`) | ○ | small lift |
| Disk write quota | ○ | small lift via tmpfs sizing |
| PID limit | ○ | small lift |

### 12. Failure-mode policy

| Item | Status | Notes |
|---|---|---|
| Action on violation: kill / pause / quarantine / continue+log | ○ | belongs alongside any new control with violation semantics |
| Alerting destination on violation | ○ | overlaps observability |

### 13. Cooperation layer (Whiz MCP server)

These are the agent-facing tools Whiz exposes via MCP. The MCP server is a first-class part of the design (assumption: all modern harnesses support MCP).

| Tool | Direction | MVP-feasible? | Notes |
|---|---|---|---|
| `whiz_status` | read | ✓ planned (Stage 9) | profile, mounts, network, expiry, harness, session id |
| `whiz_audit_self` | read | ✓ planned (Stage 9) | this session's audit log |
| `whiz_emit_event` | append | ✓ planned (Stage 9) | structured agent-authored audit entry |
| `whiz_list_presets` | read | ✓ planned (Stage 9) | enumerable presets (depends on Stage 10) |
| `whiz_request_mount` | mutate | ✓ planned (Stage 14) | depends on Stage 13 stop+restart + local TTY approval |
| `whiz_request_extend` | mutate | ✓ planned (Stage 14) | depends on Stage 13 |
| `whiz_request_network` | mutate | ○ | requires sidecar proxy; remains post-MVP |
| `whiz_graceful_exit` | mutate | ○ | overlaps adapter `wrap_up()`; not committed to MVP |

---

## What this map shows

Three patterns:

1. **The MVP through Stage 18 covers roughly half of the total surface.** That's the foundational layer (FS, network on/off, container hardening, audit log) plus the personal-use cluster pulled in 2026-05-09 (vault, stop+restart, request-side MCP, Discord control plane read+write, duration + idle enforcement, presets + CLI ergonomics, Claude Code slash commands, image management). The remaining ~50% is post-MVP, post-OSS-launch, or deferred indefinitely.

2. **The "new territory" (○) clusters in three areas, each with a single mechanism that unlocks it:**
   - **Sidecar proxy** — unlocks network egress allowlists, MCP tool shaping, traffic logging, vault generalization
   - **FUSE shim** — unlocks pattern filtering inside mounts, file-access logging
   - **Scheduler daemon** — unlocks idle timeout, time-of-day windows, hard kill schedule

   Picking a mechanism unlocks a cluster. Picking none keeps the design narrow.

3. **A different OSS user persona will weight this surface differently.** A solo developer cares about FS scope + time bounds + credentials + low-friction switching. A security-conscious individual additionally cares about network granularity + observability. A small team cares about identity + shared presets. The surface is the same; the priority order is not.

---

## What's explicitly out of scope

The following items appear above but are deprioritized indefinitely. They're things larger organizations (Microsoft etc.) will likely build. The OSS Whiz project is targeted at individual / security-conscious developer personas, not enterprises.

- AppArmor / SELinux profiles
- Time-of-day execution windows
- Bandwidth and rate caps
- Multi-party approval flows
- Credential-use audit independent of agent log
- Network traffic and file-access logs (compliance grade)
- Identity-provider integrations (SAML, etc.)

If a community contributor wants to layer these in, the architecture should accommodate it. The MVP and OSS-launch versions don't need to deliver them.

---

## Recent framing decisions

These were made in conversation 2026-05-09 and aren't yet reflected in [mvp_build_plan.md](mvp_build_plan.md) or [post_mvp_spec.md](post_mvp_spec.md). They're captured here so the surface map status markers are consistent with current intent.

1. **MVP ≠ OSS-launch.** The current MVP plan (Stages 1–9) is a local-testing milestone. OSS-launch is a later milestone with broader functionality. MVP scope expands to whatever is needed for personal daily-driver use.

2. **MCP-universal assumption.** We assume all modern agent harnesses support MCP. The Whiz MCP server is a first-class design element, not a per-adapter capability flag.

3. **Day-1 OSS value prop is B+D combination:**
   - **B**: "Define what your agent can touch, see, and do on your machine — not by approving every individual action, but by shaping the environment it runs in."
   - **D**: "Switch between named, scoped agent contexts (research / coding / ops / quarantine) faster than you can type the docker command yourself."

   D specifically pulls presets up from post-MVP §7 into MVP scope, because preset-driven switching is how D is delivered.

4. **MVP scope additions** (driven by B+D, personal-use threshold, and slash command surface decisions). The MVP build order is now Stage 1 → Stage 18 (D-143):
   - Stage 9: Whiz MCP server, read-only subset (`whiz_status`, `whiz_audit_self`, `whiz_emit_event`, `whiz_list_presets`)
   - Stage 10: Presets and CLI ergonomics (`whiz` alias, subcommand shortcuts, smart defaults)
   - Stage 11: Host-side Claude Code slash commands (`.claude/skills/` bundle for `/whiz launch`, `/whiz status`, etc.)
   - Stage 12: OneCLI vault integration (with env-var fallback when OneCLI not on host)
   - Stage 13: Stop+restart mechanism + local TTY approval flow
   - Stage 14: Whiz MCP server request-side tools (`whiz_request_mount`, `whiz_request_extend`)
   - Stage 15: Duration + idle timeout enforcement
   - Stage 16: Discord control plane (read-only)
   - Stage 17: Discord control plane (write + approve flow)
   - Stage 18: Image management (digest pinning, status, age check)

5. **Mid-session adjustment mechanism = stop+restart.** When the user (CLI or, eventually, Discord) or the agent (via MCP request tools) requests a capability change mid-session, Whiz wraps_up the harness, terminates the container, and relaunches with new flags. Acceptable friction; clean state model.

6. **Enforcement vs. cooperation layer split** (this document's central framing). The MCP server is the cooperation layer; structural controls remain enforcement. They never collapse into each other.

7. **All five personal-use candidate items pulled into MVP** (D-137). Rather than rank-ordering them, the user committed to all of them so MVP fully clears the personal daily-driver threshold.

8. **Discord control plane includes write + approve, not just read-only** (D-139). The original "read-only first" framing was a staging suggestion; both subsets are in MVP, with read-only at Stage 16 and write/approve at Stage 17.

9. **Slash command surface — A, B, C in MVP; D post-MVP** (D-142). CLI brevity (A) folds into Stage 10. Claude Code slash commands (C) become new Stage 11. Discord slash commands (B) ride on Stages 16–17. In-agent-chat command interception (D) is post-MVP and will be designed-for during Stage 8 so the adapter contract supports it without retrofitting.

---

## Open items

These came up during the surface-mapping conversation but haven't been resolved. They're not blockers for current MVP work but worth tracking.

1. ~~Which additional ○ items rise to MVP for personal-use threshold?~~ **Resolved 2026-05-09 by D-137** — all five candidates pulled into MVP.
2. **OSS-launch milestone scope.** Distinct from MVP. Needs its own definition once MVP is operational.
3. **Whether to introduce a sidecar-proxy mechanism in OSS-launch.** Unlocks a large cluster but is a real architectural commitment.
4. **Failure-mode semantics across new controls.** Each new ○ control needs a violation policy (kill / pause / quarantine / continue+log). Defining once at the framework level is cheaper than defining per-feature.

---

## Bottom line

This is the structural-controls-Whizzard-could-expose map. Most of it is not in scope today. The parts that are (✓) form a coherent foundational layer; the parts in backlog (◐) extend it sensibly; the parts that are new (○) cluster around three mechanisms (sidecar proxy, FUSE shim, scheduler daemon) and inform the OSS-launch and post-launch shape.

Update this doc when status markers change or when major new categories emerge.
