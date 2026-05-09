# Hermes Research Notes

Investigation pass before Stage 8 design. Surfaces what Hermes already does that overlaps with Whizzard's plans, where the integration seams should be, and what's worth knowing before writing the Hermes adapter.

Written: 2026-05-08.

---

## TL;DR — what changes

Several of Whizzard's planned features already exist in Hermes. The Stage 8 adapter design should **lean on these** rather than rebuild them. The biggest implications:

1. **`HERMES_HOME` is the single knob that anchors a Hermes instance.** Set it to a directory and Hermes operates entirely out of that path. Hermes already supports running with `HERMES_HOME` outside `~/.hermes` (e.g., `/opt/data` for Docker). This eliminates most of the "selective subdirectory mount" complexity I was proposing.
2. **Hermes profiles are full HERMES_HOME directories.** Each profile is a self-isolated Hermes instance: own config, sessions, skills, memories, gateway state. Whizzard can mount a *specific Hermes profile* into the container as that profile's HERMES_HOME, leaving the host's other profiles (and the default) untouched. This solves host-vs-container concurrency cleanly.
3. **Hermes has built-in Docker support.** `docker-compose.yml` and `entrypoint.sh` already exist in the Hermes repo, with a UID/GID remapping pattern. Whizzard isn't competing with this — we're adding policy/safety that Hermes's own Docker setup doesn't provide.
4. **Hermes has a full approval system.** Dangerous-command detection, yolo mode, smart mode (LLM-asks-aux-LLM), per-tool patterns. Several of Whizzard's planned approval flows can defer to Hermes for harness-specific approvals and only own session-level approvals.
5. **Hermes has env-var credential support natively.** `<PLATFORM>_TOKEN` env vars override config. Our planned env-var injection isn't a hack — it's an officially supported path.
6. **Plugins for platforms.** Hermes supports adding messaging platforms via plugins in `~/.hermes/plugins/`. Whizzard could ship a plugin if we ever needed to. Probably not needed for MVP.

---

## Hermes architecture in one page

### Layout

`~/.hermes/` (a.k.a. `HERMES_HOME`) is the root. Everything Hermes does is anchored to it. Key contents:

| Path | Purpose |
|---|---|
| `config.yaml` | Master config: model, providers, platforms, agents, security, hooks, etc. |
| `auth.json` | Per-provider OAuth state, credential pools, refresh tokens. Cross-process locked. |
| `state.db`, `state.db-{shm,wal}` | Operational state (sessions, kanban, runtime). SQLite WAL mode. |
| `kanban.db` | Task tracking. |
| `skills/` | Self-improving skills the agent loads / authors. |
| `memories/MEMORY.md`, `USER.md` | Long-term memory files. |
| `sessions/` | Conversation history per session. |
| `plans/`, `projects/` | In-flight plans and project state. |
| `SOUL.md` | Agent persona; user-edited; loaded fresh each message. |
| `hooks/` | Shell-script hooks (configured via config.yaml `hooks:`). |
| `image_cache/`, `audio_cache/`, `document_cache/` | Tool output artifacts (24h auto-cleanup). |
| `gateway.pid`, `gateway.lock`, `gateway_state.json` | Daemon lifecycle and current platform connections. |
| `<platform>_threads.json` | Per-platform thread/session mapping (discord, slack, telegram, …). |
| `channel_directory.json` | Cross-platform channel → session mapping. |
| `processes.json` | Background process tracking. |
| `profiles/<name>/` | Independent named profiles, each a fully separate HERMES_HOME. |
| `bin/`, `hermes-agent/` | Installation artifacts (binaries, repo checkout). |
| `cron/`, `logs/`, `sandboxes/`, `checkpoints/` | Operational state (auto-managed). |

### Operating modes

Three primary modes:

1. **Interactive** — `hermes chat` (or just `hermes`). Foreground TTY session. User types, agent responds, exits cleanly via `/quit` or Ctrl-D.
2. **Gateway daemon** — `hermes gateway run`. Long-running background process. Connects to platform adapters per config (Discord, Slack, etc.). Routes inbound platform messages to agent sessions, sends responses back.
3. **One-shot** — `hermes chat -q "query"`. Non-interactive single response.

Plus secondary modes: `hermes mcp` (MCP server), `hermes cron` (scheduled tasks), `hermes claw` (OpenClaw migration), worktree mode for parallel agents.

### HERMES_HOME and profiles

`HERMES_HOME` is the **single source of truth** for where Hermes operates. Default is `~/.hermes`. Override via env var.

Profiles are subdirectories under `<root>/profiles/<name>/`. Each profile is a fully-isolated HERMES_HOME with its own config, skills, memories, sessions, gateway state, etc. Switching profile = setting `HERMES_HOME` to that profile's directory.

`hermes profile create <name> [--clone | --clone-all]` creates a new profile. Clone modes copy varying subsets of the source profile (config + SOUL.md + memories at minimum; full directory tree at most).

The profile system explicitly excludes runtime files (gateway.pid, gateway_state.json, processes.json) when cloning — they're per-instance lifecycle.

### Authentication

`auth.json` is the unified credential store. Holds:

- Per-provider OAuth state (Nous Portal, Codex, Anthropic, OpenRouter, MiniMax, etc.)
- Refresh tokens with TTL tracking
- Credential pools (multiple keys per provider with rotation)
- Cross-process locking via fcntl/msvcrt for safe concurrent access

Hermes natively supports **env-var override** for credentials. From `gateway/platforms/ADDING_A_PLATFORM.md`:

```python
# In gateway/config.py _apply_env_overrides():
your_token = os.getenv("YOUR_PLATFORM_TOKEN")
if your_token:
    config.platforms[Platform.YOUR_PLATFORM].enabled = True
    config.platforms[Platform.YOUR_PLATFORM].token = your_token
```

**Implication for Whizzard:** the env-var injection path I proposed isn't a workaround. It's the officially-supported way to pass credentials. The contained Hermes can run *without auth.json* if env vars are set, and Hermes will use the env-var credentials.

### Approval system

Hermes has a full approval system in `tools/approval.py`:

- **Dangerous-command detection** (`detect_dangerous_command()`) — pattern-based identification of risky shell, file, and tool actions
- **Approval modes:**
  - `manual` (default) — user approves each dangerous command
  - `smart` — auxiliary LLM evaluates first; only escalates if LLM unsure
  - `off` / `--yolo` — bypass all approvals (dangerous mode)
  - `cron` — auto-approve in scheduled-task contexts
- **Bypass paths** — `/yolo` slash command, config-level mode, cron mode

**Implication for Whizzard:** Hermes has its own Stage-3-Breaker-like primitives for dangerous-command interception. Whizzard's safety policy operates at a different layer (mount-time, container-level), so they're complementary, not duplicate. But: Whizzard *should not* try to recreate Hermes's approval flows. Defer to Hermes for in-session approval; Whizzard's role is the outer gate.

### Plugins and extensibility

Plugins live in `~/.hermes/plugins/`. Each plugin has `PLUGIN.yaml` + `adapter.py`. Plugins can:
- Add platform adapters (no core change required)
- Register hooks (`pre_tool_call`, `post_tool_call`, `on_session_end`, etc.)
- Add tools, MCP servers, webhook subscriptions

`plugins/disk-cleanup`, `plugins/observability/langfuse`, `plugins/google_meet` are bundled examples.

### Existing Docker setup

Hermes already ships `docker-compose.yml` + `docker/entrypoint.sh`:

```yaml
services:
  gateway:
    build: .
    image: hermes-agent
    container_name: hermes
    restart: unless-stopped
    network_mode: host        # ← passes through host network
    volumes:
      - ~/.hermes:/opt/data    # ← mounts entire host ~/.hermes
    environment: { ... }
```

The entrypoint remaps the internal `hermes` user to host UID/GID via `usermod`/`gosu` so file ownership stays consistent.

**Important property:** Hermes's own Docker setup uses `network_mode: host` and mounts the entire `~/.hermes`. It does NOT provide containment — it's a deployment convenience. Whizzard's value-add is the policy/safety layer (no host network, scoped mounts, profile isolation) that this setup lacks.

---

## What Whizzard should re-think given these findings

### Drop the per-subdir mount table for the Hermes adapter

My earlier plan was a per-file mount table inside `~/.hermes`. That was overcomplicated. The cleaner model:

1. User creates a Hermes profile dedicated to containerized use: `hermes profile create whizzard-cell --clone`
2. Whizzard mounts that profile's directory as the contained Hermes's `HERMES_HOME`
3. Set `HERMES_HOME=/home/whizzard/.hermes` (or wherever) inside the container, pointing at the mount
4. Hermes operates entirely out of that profile

The host's default profile (where the user normally runs Hermes) is untouched. Switching back is just running `hermes` on the host again — different `HERMES_HOME`, different profile, no contention.

This subsumes most of the per-file decisions:
- Skills, memories, state.db, sessions: all in the mounted profile, fully RW
- SOUL.md: lives in the profile, also RW (the *user* clones their persona into the contained profile and edits it there if they want different behavior)
- Caches, hooks, locks: scoped to the profile
- auth.json: NOT in the contained profile — credentials go via env vars
- Cross-platform state files: scoped to the profile

### The contained Hermes runs in `HERMES_HOME=<mounted-profile>` mode

The gateway-vs-interactive question becomes:

- **Interactive mode:** container runs `hermes -p whizzard-cell chat` (or sets `HERMES_HOME` directly)
- **Gateway mode:** container runs `hermes -p whizzard-cell gateway run`
- Either way, the contained instance is isolated from the host's default profile

Two-mode handling stays as I described, but the underlying isolation mechanism is simpler.

### Auth via env vars is the right path

Confirmed: this is Hermes-native, not a hack. The Whizzard `--expose-key` flag injects host env vars into the container; Hermes's `_apply_env_overrides()` picks them up and uses them.

For the eventual OneCLI Vault migration: same flag, but the env vars point to vault-fetched tokens instead of host-cached ones. Migration is transparent to Hermes.

### Don't reinvent approval

Hermes has it. Whizzard's safety policy (Stage 6) covers the *outer* gate — what mounts are even possible, what network is reachable, what's hard-blocked. Hermes's approval system covers the *inner* gate — dangerous commands within the agent's allowed surface. They stack.

Concretely: Whizzard rejects mounting `~/.ssh`. Hermes (inside the cell, with a legitimate mount) rejects an `rm -rf` against that mount unless the user approves. Different layers, different decisions.

### Plugins are NOT a path we should pursue

Some part of me wondered whether Whizzard should be a Hermes plugin. After reading the plugin architecture: no. Whizzard is fundamentally a containment layer that runs *Hermes itself* inside a sandbox. A plugin runs *inside Hermes*. The directionality is wrong.

### Things in our backlog that already exist in some form in Hermes

| Whizzard backlog item | Hermes equivalent | Recommendation |
|---|---|---|
| Per-agent capability scoping (post-MVP §1) | Hermes profiles + `--profile` flag | Use Hermes profiles for the user-facing primitive; map Whizzard agents 1:1 with Hermes profiles |
| Discord/mobile control plane (post-MVP §2) | Hermes already has gateway + Discord integration | We don't reimplement Discord; we sandbox Hermes's existing Discord-connected instance |
| Multi-harness rollout (post-MVP §3) | Plugin architecture for new platforms | Hermes covers the platform side; Whizzard covers harness-level (Hermes vs OpenClaw vs NanoClaw) |
| Quick-access presets (post-MVP §7) | Hermes profiles | Whizzard presets bundle (whizzard-profile, whizzard-mounts, hermes-profile, env-vars). Hermes profile is one ingredient. |
| Vault-mediated credentials | Hermes `_apply_env_overrides()` | Use env vars in MVP. Vault gateway in v1 substitutes the env var source. |
| Approval UX | Hermes approval system | Defer to Hermes for in-session approval; Whizzard doesn't recreate this |

Several backlog items become smaller or different in light of this.

---

## Concrete answers to my pre-investigation questions

**Q: How does `hermes gateway run` start, and what config does it read?**
A: Reads `config.yaml` from `HERMES_HOME`, applies `_apply_env_overrides()` to layer env-var credentials on top, then iterates configured platforms. For each, calls `_create_adapter()` which checks dependencies via `check_<platform>_requirements()` and instantiates the adapter. Async event loop manages all platforms concurrently. Writes `gateway.pid`, `gateway.lock`, `gateway_state.json` for lifecycle and platform-state visibility.

**Q: How does auth flow per platform?**
A: `auth.json` for OAuth-flow providers (Nous, Codex, MiniMax, etc.) with refresh tokens and credential pools. Static-token providers (most messaging platforms) read tokens from `<PLATFORM>_TOKEN` env vars or from per-platform config sections in `config.yaml`. Env vars take precedence over config-file tokens.

**Q: How do Hermes profiles work, and do they collide with Whizzard profiles?**
A: Hermes profile = fully isolated `HERMES_HOME` directory. Whizzard profile = a capability/policy bundle (network on/off, duration, broad-mount override). They DON'T collide — they're orthogonal. A Whizzard launch can specify both: `whizzard run --profile build --hermes-profile coder`. Different concepts at different layers.

**Q: Shutdown path?**
A: Multiple signal handlers in `gateway/run.py` around line 14180. SIGTERM/SIGHUP triggers graceful shutdown — drains active turns, writes final state, exits. Configurable `restart_drain_timeout` (default 60s in your config). The `/quit` slash command in chat mode triggers clean exit. Worth confirming whether `/quit` works in gateway mode or if it's chat-only.

**Q: Worktree mode?**
A: `hermes --worktree` creates a separate git worktree per agent for parallel work. Doesn't affect HERMES_HOME structure (worktrees are workspace, not Hermes data). Probably orthogonal to our containment concerns; surface area for v1+.

---

## Open questions for next discussion

1. **Profile selection UX** — should Whizzard auto-create a `whizzard-cell` Hermes profile on first hermes-harness launch, or require the user to create one manually with `hermes profile create`?
2. **Concurrency lock** — should Whizzard refuse to launch a contained Hermes if the *same* Hermes profile is in use on the host (host-gateway running with that profile)?
3. **Default mode for the Hermes adapter** — interactive or gateway? My read is "interactive default, gateway via flag" but the user has indicated gateway will be more common.
4. **Platform credential UX** — for gateway mode, the user lists platforms via flag (`--platform discord`)? Or implicit from Hermes profile config?
5. **Hermes's approval system inside the cell** — do we let Hermes prompt for approval (interactive mode = TTY prompt; gateway mode = via the platform), or override it to non-interactive (e.g., `--yolo` for trusted auto-runs)? This is a real product decision.
6. **State.db concurrency** — Hermes profiles isolate state.db per-profile. Confirms the answer to my earlier concern: with profile-based isolation, host and contained instances use different state.db files, no contention.

These shape the actual Stage 8 design and are worth resolving in the next session.

---

## Bottom line

The investigation paid off. Stage 8 will be smaller and cleaner than I originally proposed because Hermes already does most of the work. The Whizzard Hermes adapter's job becomes:

1. Take a Hermes profile name as input
2. Set `HERMES_HOME` to the host path of that profile inside the container (via bind mount)
3. Inject specified credential env vars
4. Generate any necessary config overrides (mostly: disable host-only daemons inside the cell)
5. Launch `hermes` (chat or gateway based on mode flag) inside the container
6. Forward `/quit` for wrap_up
7. Log the profile, mode, and exposed env vars in session_start

That's a much smaller adapter than the 400-600 LOC estimate I gave earlier. Probably 200-300 LOC.

Worth more thought before coding: items 1-5 in "Open questions" above.
