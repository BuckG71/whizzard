# Whizzard — MVP Build Plan

This document is the tactical plan for the MVP. It assumes context from:

- [vision_and_strategy.md](vision_and_strategy.md) — the product's why, audience, and long-term direction
- [architecture.md](architecture.md) — system components, layers, safety policy, adapter schema, and architectural invariants

The MVP exists to prove that useful autonomous agents can coexist with practical local security boundaries.

---

## MVP Definition

The MVP is a **personal daily-driver milestone, not the OSS-launch milestone** (D-101). OSS-launch scope is defined separately once MVP is operational.

**Future versions** (per D-155): v1.0 adds a NanoClaw adapter; v2.0 adds a Whizzard-native secure-by-design harness. Other harnesses (OpenClaw, Claude Code, Codex, Cursor, etc.) are community-maintained via the adapter Protocol (D-28) as the open contract. The core-maintained slate is intentionally capped at three.

The MVP is operational when the system can:

**Foundational capabilities (Stages 1–9):**

1. Launch a generic Docker shell under a profile.
2. Mount only approved registered folders.
3. Apply read-only and read-write mount modes.
4. Toggle network access by profile.
5. Reject dangerous mounts per the safety policy.
6. Show dry-run permission previews.
7. Write session logs.
8. Launch a generic harness and a Hermes harness through adapters.
9. Expose a read-only Whiz MCP server so the contained agent can introspect its own constraints.

**Personal-use capabilities (Stages 10–18, added 2026-05-09 per D-137 / D-140 / D-142 / D-143):**

10. Switch between named, scoped agent contexts via presets, with terse CLI shortcuts (`whiz r`, `whiz p`, `whiz s`).
11. Operate Whiz from inside Claude Code via slash commands (`/whiz launch`, `/whiz status`, `/whiz adjust`, etc.).
12. Inject API credentials via OneCLI vault (with env-var fallback when OneCLI is absent).
13. Adjust an active session's capabilities mid-session via stop+restart, with local TTY approval.
14. Expose request-side MCP tools so the agent can ask for capability changes (`whiz_request_mount`, `whiz_request_extend`).
15. Enforce session duration and idle timeout, not just log them.
16. View running sessions, status, and audit logs via a Discord read-only control plane.
17. Start, stop, extend, switch profile, and approve mount additions remotely via Discord write/approve flow with single-use identity-bound tokens.
18. Build, audit, and pin by digest the container image used for execution.

---

## Build Order

### Stage 1 — Generic Docker Shell Launch

Goal: prove contained execution.

Deliverable:

```zsh
whizzard run --profile default
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
whizzard run --profile build --mount project-alpha
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
whizzard run --dry-run --profile build --mount project-alpha
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
- enforce config write-protection (the Whizzard config directory must never be reachable from any agent-writable mount, regardless of `mounts.json`)
- reject any mount path that resolves into the Whizzard config directory

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
Whizzard = Hermes wrapper
```

Instead:
```text
Hermes adapter → Whizzard core
```

Profile-based isolation: Whizzard mounts a single Hermes profile directory as `HERMES_HOME` rather than mounting individual subdirectories of `~/.hermes`. Credentials inject via env vars; `auth.json` never enters the cell. Stage 8 design is resolved (D-86 through D-90 all `active` as of 2026-05-14); see `STAGE_8_BUILD_PLAN.md` for the build-state detail.

### Stage 9 — Whiz MCP Server (Read-Only Subset)

Goal: give the contained agent a structured, agent-facing interface to introspect its own Whiz-imposed constraints.

Tools shipped at this stage (cooperation layer, all read-only):
- `whiz_status` — current profile, mounts, network policy, expiry, harness, session id
- `whiz_audit_self` — this session's own audit log entries
- `whiz_emit_event` — agent-authored entry appended to the audit log
- `whiz_list_presets` — enumerable presets (Stage 10 dependency)

The MCP server is a first-class part of the design (D-25). Mutate-side tools come at Stage 13.

### Stage 10 — Presets and CLI Ergonomics

Goal: deliver the day-1 OSS value-prop "switch between named, scoped agent contexts" (the **D** half of D-102's B+D combination), with low-friction CLI ergonomics so common operations require minimal typing.

Deliverables:

**Presets** — named bundles of profile + harness + mounts + duration + env vars + (optionally) idle timeout:

```zsh
whizzard preset launch coding-session
```

Preset config format and example presets per [post_mvp_spec.md §7](post_mvp_spec.md). Promoted from post-MVP per D-103.

**CLI brevity** (D-142 A):
- Short binary alias: `whiz` alongside `whizzard`
- Subcommand shortcuts: `whiz r` → `whiz run`, `whiz s` → `whiz sessions tail`, `whiz p` → `whiz preset launch`
- Smart defaults: `whiz r` with no args = launch the most recently used preset

Pure UX work; no architectural lift.

### Stage 11 — Host-side Claude Code Slash Commands

Goal: zero-friction Whiz operation from inside Claude Code (D-142 C).

Deliverable: a bundle of `.claude/skills/` recipes that wrap the underlying `whizzard` CLI. Pattern follows NanoClaw's operator-side skill model documented in [archive/nanoclaw_internals.md §2](archive/nanoclaw_internals.md).

Skills shipped at this stage:

- `/whiz launch <preset>` — start a preset session
- `/whiz status` — list running sessions
- `/whiz preset list` — list available presets
- `/whiz sessions tail` — tail the audit log
- `/whiz extend <session-id> <duration>` — read-only display at this stage; mutating behavior unlocked at Stage 13
- `/whiz approve <token>` — read-only display at this stage; mutating behavior unlocked at Stage 14
- `/whiz adjust <session-id> --add-mount <name>` — read-only display at this stage; mutating behavior unlocked at Stage 13

The Stage 11 deliverable is the skill bundle plus the read-only operations. Mutating operations are unlocked progressively as their underlying stages land.

No new pip dependencies; the skills shell out to `whizzard`.

### Stage 12 — OneCLI Credential Plumbing (Cross-Adapter Generalization + Fallback)

Goal: make OneCLI credential injection a reusable adapter utility, with a clean fallback when OneCLI isn't available.

Stage 8 shipped OneCLI integration scoped to the Hermes adapter — the credential-fetch shell-out and per-platform `<PLATFORM>_BOT_TOKEN` injection live in `whizzard/adapters/hermes.py` (per D-89 amended and D-134). Stage 12 generalizes the pieces that aren't Hermes-specific into a shared adapter utility so future adapters (v1.0 NanoClaw, v2.0 Whizzard-native harness, community adapters) can use the same primitives without re-implementing them.

Deliverables:

- **Extract `_fetch_secret_via_onecli` and related helpers** from the Hermes adapter into a shared adapter utility module (e.g., `whizzard/adapters/_onecli.py`). Surface stays adapter-private per D-153 — core modules don't reference it — but the utility is shared across adapters.
- **Env-var fallback path.** When OneCLI isn't installed (or returns no matching secret), fall back to reading the corresponding env var directly from the host with a warning logged to the session record. Per D-134's "OneCLI not installed" failure-mode note.
- **Pre-launch surfacing.** `active_capabilities()` on each adapter using the utility flags whether credentials came via OneCLI, host env, or neither (the last is an error).
- **Refactor Hermes adapter** to consume the extracted utility (delete the duplicate code from `adapters/hermes.py`).

**NOT in this stage:** the proxy-based "credentials never enter container" pattern from D-91. That pattern applies to "agent uses external API" use cases (NanoClaw shape — D-91's scope per D-134's clarification), which lands in v1.0 alongside the NanoClaw adapter, not MVP.

The original Stage 12 framing (proxy pattern via `HTTPS_PROXY`) was based on D-91's literal "credentials never enter container" guarantee. D-134 clarified that for gateway-style harnesses — Hermes, the MVP target — OneCLI's role is delivery-mechanism only, not proxy-based interception. The proxy pattern is preserved for v1.0 NanoClaw adoption per D-155's slate.

Promoted to MVP per D-98 (vault is v1-must-have). Lands at this position because credential isolation hygiene — even bounded — is the strongest single argument for Whiz's security thesis (D-102 / B).

### Stage 13 — Stop+Restart Mechanism + Local TTY Approval Flow

Goal: change a running session's capabilities without losing the session.

Mechanism (D-27): adapter.wrap_up() → terminate → relaunch with new flags. The session is logically continuous from the user's perspective even though the container is replaced. Approval is a local TTY prompt for MVP; Discord approval comes at Stage 17.

User-facing CLI:

```zsh
whizzard adjust <session-id> --add-mount foo
whizzard adjust <session-id> --extend 30m
```

This is the substrate Stage 14's request-side MCP tools call into.

### Stage 14 — Whiz MCP Server (Request-Side Tools)

Goal: agent-initiated capability requests.

Tools added at this stage:
- `whiz_request_mount` — agent requests a named mount be added; Whiz host-side prompts user (or auto-approves per profile policy), applies via Stage 13 stop+restart
- `whiz_request_extend` — agent requests duration extension

Depends on Stage 13 substrate. Network-egress-allowlist requests (`whiz_request_network`) require sidecar proxy and remain post-MVP.

### Stage 15 — Duration + Idle Timeout Enforcement

Goal: time-bounded sessions become enforced (not just logged).

Requirements:
- hard duration cap kills the container at expiry
- idle timeout kills the container after N minutes with no agent activity
- both write to session log with expiry reason
- pre-expiry warning at configurable lead time

Builds on the duration tracking already present from Stage 5.

### Stage 16 — Discord Control Plane (Read-Only)

Goal: see what's running from anywhere.

Bot framework + Discord auth + read-only commands:
- `/whizzard status` — list running sessions, current profile/mounts/expiry per session
- `/whizzard sessions list` — recent session history
- `/whizzard logs tail <session-id>` — tail the audit log for one session

Reads are queries against `~/.whizzard/logs/sessions.jsonl` plus live process state. No mutation.

The Whiz control plane channel must be separate from the agent interaction channel (architecture invariant — agents do not manage their own permissions, [post_mvp_spec.md §2](post_mvp_spec.md)).

### Stage 17 — Discord Control Plane (Write + Approve)

Goal: full Discord-mediated session management.

Mutating commands:
- `/whizzard start` — launch a session (preset or explicit args)
- `/whizzard stop <session-id>`
- `/whizzard extend <session-id> <duration>`
- `/whizzard switch-profile <session-id> <profile>` — implemented via Stage 13 stop+restart
- `/whizzard approve <token>` — approve pending mount addition or other capability request

Approval token security (per D-113): tokens are single-use, expire after 5 minutes, validated against the Discord user ID that initiated the session request.

### Stage 18 — Image Management

Goal: prevent stale or unknown images from undermining containment.

Requirements:
- base image digest pinned in `Dockerfile` (not floating tag)
- `whizzard image build` to build/rebuild the local image
- `whizzard image status` to show current image id, build date, base digest
- `whizzard image check` to compare current image age against staleness threshold
- session log records the image id for each session (already implemented in Stage 5)

Stale images are a silent risk: a compromised or outdated base image defeats the containment model regardless of policy correctness. Image provenance must be visible and auditable.

This stage was originally Stage 9, then Stage 11, then Stage 17; it now lands at Stage 18 (D-143). It's polish-relative-to-functionality compared to the personal-use capability stages and benefits from being the last MVP stage so the security audit before OSS-launch starts from a fully digest-pinned baseline.

---

## Repository Structure

```text
whizzard/
  README.md
  pyproject.toml

  whizzard/
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
    whizzard-safe
    whizzard-default
    whizzard-build
    whizzard-power

  docs/
    vision_and_strategy.md
    architecture.md
    mvp_build_plan.md
    post_mvp_spec.md

  tests/
```

---

## MVP Acceptance Test

The MVP passes if these commands behave as specified:

**Foundational (Stages 1–9):**

```zsh
whizzard run --profile safe
whizzard run --profile default
whizzard run --profile build --mount project-alpha
whizzard run --dry-run --profile build
whizzard run --profile build --harness hermes
whizzard adapters list
whizzard profiles list
whizzard mounts list
whizzard harnesses list
whizzard sessions tail
```

**Personal-use (Stages 10–18):**

```zsh
whizzard preset launch coding-session
whiz r                                                 # smart default: launch most-recent preset
whiz s                                                 # subcommand shortcut: sessions tail
whizzard run --profile build --vault                  # OneCLI vault on
whizzard adjust <session-id> --add-mount foo
whizzard adjust <session-id> --extend 30m
whizzard sessions list
whizzard image status
whizzard image check
```

**Claude Code slash commands (Stage 11):**

```text
/whiz launch coding-session
/whiz status
/whiz preset list
/whiz sessions tail
/whiz extend <session-id> 30m
/whiz adjust <session-id> --add-mount foo
/whiz approve <token>
```

**Discord control plane (Stages 16–17):**

```text
/whizzard status
/whizzard start preset:coding-session
/whizzard stop <session-id>
/whizzard extend <session-id> 30m
/whizzard approve <token>
```

And:
- dangerous mounts are blocked per the safety policy
- logs are written for every session, including capability adjustments
- containerized execution works for both shell and Hermes harnesses
- network mode changes by profile
- host home directory is inaccessible
- adapter abstraction is preserved
- image provenance is recorded for every session
- credentials never enter the container when the vault is in use
- duration and idle timeouts are enforced (not just logged)
- agent-initiated `whiz_request_*` MCP calls go through the local TTY approval flow (or the Discord approval flow when the control plane is up)
- Discord control plane channel is separate from agent interaction channel

---

## Explicit Non-MVP Features

Do NOT build during MVP:
- GUI
- MCP gateway adapter (governed MCP runtime for arbitrary harnesses — distinct from the Whiz MCP server in Stages 9 and 13)
- Per-agent orchestration (per-agent capability scoping comes via Whiz profiles + presets in MVP; full multi-agent identity is post-MVP)
- Breaker engine
- Shadow-home system
- File tree mount picker
- AI risk scoring
- VM orchestration (Podman / Firecracker / Apple Virtualization Framework)
- Network egress allowlists, MCP tool shaping, traffic logs (all require sidecar-proxy mechanism — post-MVP / post-OSS-launch)
- AppArmor / SELinux profiles, time-of-day windows, bandwidth caps, multi-party approval, identity-provider integrations (deprioritized indefinitely per D-123 — enterprise-shaped)

The Discord control plane was previously listed here; it moved into MVP at Stages 15–16 per D-137 and D-139.

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
