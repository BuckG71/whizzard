# Session Handoff — 2026-05-08

> **Historical snapshot — superseded by subsequent work.** This document captures the project state as of 2026-05-08. The 2026-05-09 session moved well past it: MVP scope expanded to 18 stages, naming consolidated to single "Whizzard" (D-144), repo and local dir renamed (D-145, D-146), control-layering framing formalized in [architecture.md](architecture.md), control surface mapped in [control_surface.md](control_surface.md), decisions index built in [decisions.md](decisions.md). A new session should orient from those documents, not this one.

Comprehensive context for resuming this work in a new Claude Code session. Designed so a fresh session can read this one document and pick up the thread without re-deriving the whole project from scratch.

---

## Quick orientation

If you're a new Claude Code session reading this:

1. The user is **BuckG71** (`<redacted>`, `BuckG71` on GitHub).
2. The project is **Whizzard / Airlock** — a local capability-governance layer for AI agents. Currently shipping under the placeholder repo name `basicagentauth` and internal package name `whizzard`. Real names TBD post-MVP.
3. Repo: [github.com/BuckG71/basicagentauth](https://github.com/BuckG71/basicagentauth) (private).
4. Local working directory: `/Users/USER/ai-sandbox/airlock-warlock` (the `airlock-warlock` name is legacy from before the rename; do not rename mid-session — Claude Code's working-dir binding breaks).
5. We are mid-design on **Stage 8 (Hermes adapter)**. No code written yet for Stage 8. Stages 1–7 are complete, pushed, and validated by the user.
6. The user's durable preferences are in this project's memory directory and load automatically. Read them.

## Build progress

| Stage | Status | Tests |
|---|---|---|
| 1: Generic Docker Shell Launch | ✅ Done, validated | 13 |
| 2: Mount Registry | ✅ Done, validated | +19 |
| 3: JSON-driven Profiles | ✅ Done, validated | +14 |
| 4: Dry Run | ✅ Done, validated | +9 |
| 5: Session Logging | ✅ Done, validated | +13 |
| 6: Safety Validation | ✅ Done, validated | +18 |
| 7: Generic Adapter | ✅ Done, validated | +41 |
| **8: Hermes Integration** | **In design — no code yet** | — |
| 9: Image Management hardening | Not started | — |

**131 tests passing** as of latest commit. Last commit: `2a73fbc` (NanoClaw research notes).

## Repository contents (key files)

```
airlock-warlock/
├── README.md
├── pyproject.toml
├── whizzard/               # Python package
│   ├── __init__.py
│   ├── cli.py              # Typer CLI entry point
│   ├── config.py           # Profile + WHIZZARD_HOME / paths
│   ├── docker_cmd.py       # docker run argv builder + run_shell
│   ├── mounts.py           # Mount registry
│   ├── safety.py           # Hard-block + override-required policy
│   ├── session_log.py      # JSONL session logging
│   ├── harness_config.py   # harnesses.json loader
│   └── adapters/
│       ├── __init__.py     # build_adapter() factory
│       ├── base.py         # HarnessAdapter Protocol + WrapUpResult
│       └── generic.py      # GenericShellAdapter
├── tests/                  # 131 tests passing
├── docker/Dockerfile       # whizzard-base:latest image
├── config/
│   ├── mounts.json.example
│   ├── profiles.json.example
│   └── harnesses.json.example
├── docs/
│   ├── vision_and_strategy.md
│   ├── architecture.md
│   ├── mvp_build_plan.md
│   ├── post_mvp_spec.md
│   ├── stage_validation.md     # manual validation checklists per stage
│   ├── hermes_research.md      # ★ Hermes deep-dive findings
│   ├── nanoclaw_research.md    # ★ NanoClaw comparative analysis
│   └── session_handoff.md      # this file
└── scripts/                # empty placeholder
```

The two ★ files are the most important reading for a new session — they capture investigation findings that shape Stage 8 design.

## Durable feedback (auto-loaded from memory)

Three files at `/Users/USER/.claude/projects/-Users-USER-ai-sandbox-airlock-warlock/memory/`:

1. **MVP focus** — until MVP is operational, push back on doc tweaks and steer toward implementation. Backlog additions are explicit exceptions.
2. **One topic at a time** — surfacing a multi-item list is fine, but discuss and resolve them one at a time before moving on.
3. **Don't push to close items** — stop ending responses with "ready to close X?" prompts. Topics close naturally.

These auto-load. Honor them.

## Architectural decisions made

- **Project name:** `basicagentauth` (placeholder GitHub repo)
- **Internal package:** `whizzard` (placeholder, was `warlock` until we discovered Warlock is an active 2026 ransomware family)
- **Local working dir:** stays `airlock-warlock` (renaming mid-session breaks Claude Code working-dir binding)
- **Architecture: Airlock = governance/containment, Whizzard = runtime/orchestrator.** Most of what we've built so far is *Airlock* work (profile/mount/safety policy); the *Whizzard* work (orchestrating real agent harnesses) is Stage 8+.
- **Five built-in profiles:** safe, default, build, power, quarantine. `default` is unlimited duration with network enabled — the productive baseline.
- **Two-gate broad-mount override:** profile must permit AND `--allow-broad-mount` must be passed. Either alone is insufficient.
- **Hard-block list (no override):** `/`, `$HOME`, `~/.ssh`, `~/Library`, `~/.docker`, `/var/run/docker.sock`, `~/.whizzard`. Bidirectional intersection check.
- **Container hardening:** non-root UID 1000, `--cap-drop=ALL`, `--read-only` rootfs with tmpfs for `/tmp` and `/home/whizzard`, `--security-opt no-new-privileges`, network policy from profile.
- **Session log:** JSONL at `~/.whizzard/logs/sessions.jsonl`, one `session_start` and one `session_end` per session, sharing session_id.
- **Adapter contract:** `HarnessAdapter` Protocol with `start_command()`, `container_env()`, `working_dir()`, `wrap_up(container_id, grace_seconds)`, `health_check_command()`. WrapUpStatus enum: SUCCESS / TIMEOUT / NO_OP / ERROR.
- **Vault-mediated credentials = OneCLI Agent Vault pattern** (validated by NanoClaw). Currently a backlog item; should be promoted to v1-must-have based on NanoClaw's production validation.

## Stage 8 design state — what we know

The Hermes adapter design has been substantially clarified by the research investigation. The integration is simpler than originally proposed.

### Settled

1. **Profile-based isolation, not per-subdir mount table.** Hermes profiles are full HERMES_HOME directories under `~/.hermes/profiles/<name>/`. Mount one profile dir into the container as the contained Hermes's HERMES_HOME. Host's other profiles untouched. Solves state.db concurrency cleanly.

2. **Env-var credential injection is Hermes-native, not a workaround.** `<PLATFORM>_TOKEN` env vars override config in `_apply_env_overrides()`. `--expose-key NAME` flag injects host env vars; auth.json never enters the container.

3. **Hermes already has approval system, hooks, dangerous-command detection.** Whizzard does NOT recreate. Layers stack: Whizzard (capability/network/mount policy) + Hermes (in-session approval, dangerous-command interception) + OneCLI Vault (credentials never enter cell, when v1 lands).

4. **UID strategy: hybrid.** Default UID 1000; if host UID differs from 1000, use host UID for the Hermes profile mount. NanoClaw demonstrates this works in practice. Logged in session_start.

5. **Self-improvement loop survives.** Profile mounted RW, plus the UID hybrid means writes work. Skills/memories/state.db all stay writeable inside the cell; Hermes can author skills, accumulate memories, update state across sessions.

6. **Wrap-up via `/quit` slash command.** `docker exec` into the running container to send the command. SIGTERM as fallback.

7. **Two operating modes:** interactive (`hermes chat`) and gateway (`hermes gateway run`). User confirmed gateway is the more common interaction mode but interactive must remain available.

### Open design questions

These need to be resolved before writing the adapter. The user's directive is **one item at a time, no rushing**.

1. **Profile auto-creation UX.** Should Whizzard auto-create a `whizzard-cell` Hermes profile on first hermes-harness launch (`hermes profile create whizzard-cell --clone`), or require the user to create one manually first?

2. **Concurrency exclusivity.** Should Whizzard refuse to launch a contained Hermes if the host is already running a gateway with the same Hermes profile (would corrupt state.db)? Or just document the constraint?

3. **Default mode.** Interactive or gateway as the adapter's default? User has signaled gateway is more common but Option B (two explicit modes) might be more transparent than Option A (gateway-default).

4. **Platform credential UX (gateway mode).** When user runs `--mode gateway`, how do they declare which platforms are active? Four candidates discussed:
   - A. Implicit from config.yaml (whichever platforms have non-empty config sections)
   - B. CLI allowlist (`--platform discord --platform slack`)
   - C. Harness-config presets in harnesses.json (`hermes-discord-only`)
   - D. Hybrid: config.yaml provides defaults, CLI overrides
   I have a lean toward D; user hasn't weighed in yet.

5. **In-session approval routing.** Hermes's approval system prompts the user to confirm dangerous commands. In interactive mode → TTY prompt works. In gateway mode → approval has to go through the platform (Discord/etc.) or be `--yolo`-bypassed. This is a real product decision.

### Estimated adapter size

~250-350 LOC (down from initial 400-600 estimate). Smaller because Hermes does most of the work; the adapter mostly orchestrates.

## Recent conversation — verbatim

The most recent turns of substantive design discussion. Use these to pick up the thread.

---

### User (the most recent question that opened the current thread)

> Now I don't have any pushback, but I do have questions. Here they are, and let's talk about them one at a time as usual
>
> Pls provide further explanation for this statement:
> > Files outside ~/.hermes: technically isolated by container namespace, but: the entrypoint remaps the container user to the host UID, which means on any host volume the agent has access to, the agent has the host user's effective permissions on those files. Bidirectional visibility.
>
> Now that you know precisely how Hermes works without Whizzard, do you have a better handle on how we can integrate it with Whizzard?

---

### Claude (response — UID remapping deep dive, holding question 2)

> Holding question 2 for after we close out question 1. Here's the deeper explanation.
>
> ## What UID remapping actually is
>
> In Linux, file access is gated by UID and GID. A file owned by UID 501 with mode `0600` is readable/writable only by UID 501. UID 1000 trying to access it gets `EACCES`.
>
> When you bind-mount a host directory into a Docker container, the **mount preserves UIDs**. Files in the mount keep their host-side UID/GID as the container sees them. The Linux kernel still gates access by UID...
>
> [Full detailed answer about how Hermes's entrypoint uses usermod to remap container `hermes` user to host UID, what "bidirectional visibility" means, and why Whizzard's fixed UID 1000 is different]

---

### User

> Not quite yet. How does this impact Hermes's ability to self-improve through its memory and skills files, which live on the host?

---

### Claude (response — self-improvement permission analysis)

> Excellent question — this exposes a real wrinkle...
>
> [Detailed answer: with Whizzard's fixed UID 1000 and typical macOS host user UID 501, files are world-readable but NOT world-writable, so the agent could read but not write skills/memories. Writes appear to work in our Stage 2 validation because Docker Desktop on macOS does transparent UID translation via gRPC-FUSE/VirtioFS. On raw Linux without that translation, self-improvement breaks.]
>
> [Concluded: scoped UID parity for the Hermes profile mount specifically — match container UID to host UID for that mount, keep UID 1000 for other mounts. Hard-block paths still apply. Logged in session_start.]

---

### User

> I think before we go on to question two. It would be useful if you do a deep-dive review of the Nano Claw repository on GitHub, assessing it for these same issues.

---

### Claude (action: cloned NanoClaw, analyzed, wrote `docs/nanoclaw_research.md`)

Cloned `qwibitai/nanoclaw`, read SECURITY.md, isolation-model.md, container-runner.ts, container/Dockerfile, container/entrypoint.sh, container-runtime.ts, mount-security module. Wrote comprehensive findings to `docs/nanoclaw_research.md`.

Key findings:
- **NanoClaw IS the closest existing peer to Whizzard.** Container isolation for Claude-based agents.
- **OneCLI Agent Vault** — production-proven credential isolation. Real credentials NEVER enter the container.
- **External mount allowlist** at `~/.config/nanoclaw/mount-allowlist.json` — never mounted, can't be modified by agents.
- **UID handling matches my proposed hybrid** — default UID 1000, override to host UID if it differs from 1000. Same as what I proposed for Whizzard's Hermes adapter.
- **NanoClaw container hardening is meaningfully WEAKER than Whizzard's:** no `--cap-drop=ALL`, no `--read-only`, no `--security-opt no-new-privileges`, no tmpfs, no network policy ("Unrestricted" by design), tag-only image refs.
- **Confirmed positioning:** Whizzard is the policy/hardening layer that complements harness-native containment. The strongest overall posture is harness scope-reduction (NanoClaw or Hermes) + Whizzard hardening + OneCLI vault.
- **OneCLI Agent Vault should move to v1-must-have** in the post-MVP backlog.

---

### User

> I actually have NanoClaw installed on this machine right now, so I could also offer you access to that directory if that would be better.

---

### Claude (response — declined, with reasoning)

> Appreciate it, but honestly — I'd say no for this round, though it's a thoughtful offer.
>
> [Reasoning: public repo gave me what's needed for design questions; live install would mean reading user's `.env`, `store/` SQLite, `groups/` content, channel auth state — which are intentionally outside any container's reach. Slight irony in being the loophole defeating that design.]
>
> One legitimate exception — for a focused targeted question (e.g., "what does OneCLI's container.json actually look like in practice"), would take you up on it. Proactive browsing for context isn't a fit.

---

### User

> Okay, let's move on to question two.

---

### Claude (response — yes, substantially better handle on integration)

> Yes — substantially better, and a lot of the early complexity collapses.
>
> ## The core integration becomes simpler than I originally proposed
>
> The critical insight from the research: **Hermes is already designed to be relocated.** `HERMES_HOME` is one env var. Set it to a directory, and Hermes operates entirely out of that path...
>
> [Walked through:
> - Old plan: selectively mount sub-directories of ~/.hermes
> - New plan: mount one Hermes profile directory as HERMES_HOME
> - The Hermes adapter does roughly 8 things, ~250-350 LOC
> - Three-layer security (Whizzard / Hermes / OneCLI Vault)
> - Each layer does what it does best
> - 7 corrections to my pre-research assumptions in a comparison table
> - 5 still-open design questions]
>
> That close out question 2? Or do you want to push on any of the integration specifics before we pick one of the five open design questions?

---

### User (the response that triggered the most recent feedback)

> You really have to stop pushing to close things out. We will close them out when it's appropriate to do so, but that adds friction to this process, not that it doesn't take it away.
>
> Let's talk for a moment as if Whizzard doesn't exist. Explain to me precisely how the Hermes profiles work. It seems inefficient to have agents that don't share memories among them, unless they were for entirely different work streams.

---

### Claude (response — saved feedback to memory + answered profiles question)

Saved durable feedback (`feedback_dont_push_to_close.md`) and updated MEMORY.md.

Then answered the profiles question:

- **What a profile is technically:** a directory serving as a complete self-contained HERMES_HOME. Lives at `<root>/profiles/<name>/`. Default profile is `~/.hermes` itself. Inside any profile: complete Hermes installation state — config.yaml, auth.json, .env, SOUL.md, memories/, sessions/, skills/, plans/, projects/, kanban.db, state.db, hooks/, gateway state, home/ subprocess HOME, logs/, cron/, image_cache/, audio_cache/, etc.
- **Profile selection** via `HERMES_HOME` env var or `hermes -p coder <command>`.
- **What's NOT per-profile:** the hermes binary, source code, bundled "stock" skills (copied into a profile when you create it), shared Python env.
- **Creation:**
  - `hermes profile create coder` — fresh profile, bundled skills, default config
  - `--clone` — copies config.yaml, .env, SOUL.md, memories from source
  - `--clone-all` — full filesystem copy minus a strip list (gateway runtime files)
- **Addressing the "inefficient" intuition:** profiles are FOR different work streams. The misconception comes from assuming "agent = runtime instance." In Hermes:
  - Agent identity = a profile (one persona, memory, history)
  - Runtime invocation = one launch of `hermes` against a profile
  - Multi-platform reach = one profile connected to multiple platforms
- **NanoClaw's three-level isolation model summary:** same session across channels / same agent separate sessions / separate agents. Levels 1-2 use one profile; level 3 uses multiple profiles — and at level 3, the memory non-sharing is deliberate.
- **When profiles make sense vs. don't:** table of scenarios.
- **Multi-agent collaboration:** Hermes uses subagent delegation within ONE profile, not multiple profiles. `delegation.max_concurrent_children: 3`, `delegation.max_spawn_depth: 2`.
- **Shared memory across profiles** is opt-in via pluggable memory backends (Honcho, Mem0). Multiple profiles point at the same external service to share long-term memory while keeping per-profile session isolation.
- **Why isolation is the default:** memory cross-contamination has high cost — privacy leaks, persona contamination, accidental cross-context skill propagation. Sharing made deliberately hard.

---

### User (current message)

> I noticed that we're getting close to the context window limit. I propose that we should write a summary document so that if I need to create a new Claude Code session, all of the relevant context will be preserved. Make the most recent turns verbatim.

---

## Recommended next move for a new session

When the user picks back up, the substantive thread is:

> Five open design questions for Stage 8 Hermes adapter (listed above). User's directive: one at a time, no rushing.

Reasonable opening: ask the user which of the five they want to take first. The most consequential is probably #3 (default mode — interactive vs. gateway) since it cascades into the others. But honor the user's choice; they may want #1 (profile auto-creation UX) first as the foundation.

**Do not:**
- Re-derive what's already in the research docs. Read them.
- Push to close items. Let topics resolve naturally.
- Surface a list of all 5 questions and try to answer them at once. One at a time.
- Make assumptions about names ("Whizzard," "basicagentauth" are placeholders).
- Edit production architecture docs unless truly critical (MVP-focus rule).

**Do:**
- Start by reading `docs/hermes_research.md` and `docs/nanoclaw_research.md` so you have the baseline.
- Read `docs/architecture.md`, `docs/mvp_build_plan.md`, `docs/stage_validation.md` for the broader context.
- Read this file (you're reading it).
- Ask the user where they want to pick up.

Good luck.
