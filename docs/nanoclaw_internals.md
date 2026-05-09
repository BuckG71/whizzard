# NanoClaw Internals — Companion to nanoclaw_research.md

Deep-dive into the internal architecture of [qwibitai/nanoclaw](https://github.com/qwibitai/nanoclaw): agent-runner anatomy, the skill installer mechanism, DB schemas, group templates, providers, router/delivery flow, and tests. Driven by a specific use case: assessing what a Hermes-style **self-learning** skill would need to look like as an installable NanoClaw skill (and what that exercise tells us about Whizzard's own internals).

The security/containment side of NanoClaw is covered in [nanoclaw_research.md](./nanoclaw_research.md). This doc deliberately skips that ground — read it first if you haven't.

Written: 2026-05-08.

---

## TL;DR

- **NanoClaw's "skill" word means three different things at once.** Top-level `.claude/skills/` are *Claude Code skills the operator runs against the repo* (e.g. `/add-discord` is a skill for Claude Code on the host that runs git fetch/copy/install steps). `container/skills/` are *Claude Code skills the agent inside the container has at runtime* (e.g. `welcome`, `onecli-gateway`). And the `/add-X` "skill installer" is itself just a Claude Code skill that performs **branch-based code grafting** — `git fetch origin <branch>` + `git show origin/<branch>:path > path` + append a self-registration import line. There's no templating system, no generator, no separate skill manifest. Skills are git branches.
- **The composed CLAUDE.md is regenerated on every container spawn** from a shared base (`container/CLAUDE.md`) plus per-skill `instructions.md` symlinks plus per-MCP `instructions` strings. Per-group memory lives in `CLAUDE.local.md` (the only file the agent can write that survives recompose). This is the closest existing analogue to Hermes-style "load skill files dynamically" — and it's already where a self-learning loop would have to plug in.
- **The agent-runner's tool registry is one MCP server (`mcp__nanoclaw__*`) populated by side-effect-imports** in `container/agent-runner/src/mcp-tools/index.ts`. Each module calls `registerTools([...])` at module scope. New tools = new file + one import line. The Claude Agent SDK is invoked once per turn via `query()`, with this MCP server passed alongside any extra MCP servers from `container.json`. The poll loop streams user messages into a single long-lived query and drains events back out.
- **State persistence across ephemeral containers is split across three SQLite files per session** plus the central host DB. `inbound.db` is host-written / container-read (messages_in, destinations, session_routing). `outbound.db` is container-written / host-read (messages_out, processing_ack, session_state, container_state). The host's `v2.db` holds agent_groups, sessions, users, and durable scheduling. Conversation continuity rides on a per-provider `continuation` key in `session_state`. Per-group long-lived memory lives on the host filesystem at `groups/<folder>/CLAUDE.local.md` and the group's `conversations/` subdirectory (transcript archives written by a PreCompact hook).
- **A self-learning skill is a natural fit, but it would not be small.** It would have to write to `groups/<folder>/CLAUDE.local.md` (already RW from the container), drop new "skill" files under either `groups/<folder>/skills/` (would need new mount + composer hook) or piggy-back on existing skill-fragment infrastructure, and either run a curator inline (cheap, but ties into the agent's main turn) or as a `create_agent` companion (already supported, more expensive). Branch-based skill distribution is the wrong model for *self-authored* skills since the skill is the agent's own work, not an upstream artifact — so a self-learning system would need its own filesystem-resident skill mechanism alongside the existing branch-installed one.

---

## 1. Agent-runner anatomy

The in-container code lives in `container/agent-runner/src/`. It's Bun-native (no tsc build step — Bun runs TypeScript directly), and the source is **mounted RO from the host** at `/app/src/`, not baked into the image. So source-only changes don't require an image rebuild.

### 1.1 Entry point

`container/agent-runner/src/index.ts` is small and very declarative. Notable steps:

1. `loadConfig()` reads `/workspace/agent/container.json` (mounted RO from `groups/<folder>/container.json`).
2. Provider barrel is imported for side effects — `import './providers/index.js'`. Each enabled provider self-registers via `registerProvider(name, factoryFn)`. Provider-install skills append imports to that barrel.
3. Build a system-prompt addendum via `buildSystemPromptAddendum(assistantName)` from `destinations.ts`. **Everything else** (capabilities, per-module instructions, per-channel formatting) is loaded by Claude Code from `/workspace/agent/CLAUDE.md`, which the host regenerated at spawn time (see §3).
4. Walk `/workspace/extra/*` for any per-group additional directories.
5. Build the MCP servers map: nanoclaw built-in (always), plus any from `container.json`.
6. `createProvider(providerName, opts)` — opts include `assistantName`, `mcpServers`, `env`, `additionalDirectories`.
7. `runPollLoop({ provider, providerName, cwd: '/workspace/agent', systemContext: { instructions } })`.

The poll loop is the agent's main loop. It does **not** start a new Claude Code SDK call per inbound message — it keeps a single query open across messages.

### 1.2 The poll loop (pseudocode)

```
continuation = migrateLegacyContinuation(providerName)   // resume across container restart
clearStaleProcessingAcks()                                // crash recovery

forever:
    msgs = inbound.db.messages_in WHERE status='pending' AND kind != 'system'
    if no triggering message in batch: sleep 1s; continue
    markProcessing(msg ids)

    handle /clear: reset continuation, clear DB, write reply, mark completed
    run pre-task scripts (scheduling module hook); drop tasks that say wakeAgent=false
    prompt = formatMessages(survivors)

    query = provider.query({ prompt, continuation, cwd, systemContext })
    setCurrentInReplyTo(routing.inReplyTo)        // for MCP send_message stamping

    // Concurrent follow-up pump (every 500ms while query is alive):
    poller every 500ms:
        if pending slash command: query.end(); break out so outer loop reformats it
        else: query.push(formattedNewMessages)

    for await event in query.events:
        touchHeartbeat()
        if init:      continuation = event.continuation; persist immediately
        if result:    markCompleted(initialBatch); dispatchResultText(event.text)
        if compacted: query.push(reminder about <message to=...> destinations)

    if continuation changed: persist
    markCompleted(remaining)
```

Three things worth highlighting:

- **One query, many messages.** The poll loop pushes follow-up messages into the *active* query rather than re-spawning the SDK between turns. Anthropic's prompt cache is server-side and TTL-based (5 min), so this is purely a CPU cost optimization — not what keeps the cache warm.
- **Slash commands force-end the stream.** `/clear`, `/compact`, etc. only dispatch when they're the first input of a query. So when the poller sees one mid-stream it ends the query and lets the outer loop re-format with the command first.
- **Compaction injects a destination reminder.** When the SDK auto-compacts mid-conversation (default 165k token window for Claude), the agent often forgets the `<message to="...">` wrapping discipline. The poll loop catches the `compacted` event and pushes a system reminder back in.

### 1.3 Provider abstraction

`container/agent-runner/src/providers/types.ts` defines a small interface:

```typescript
interface AgentProvider {
  readonly supportsNativeSlashCommands: boolean;
  query(input: QueryInput): AgentQuery;
  isSessionInvalid(err: unknown): boolean;
}
interface AgentQuery {
  push(message: string): void;
  end(): void;
  events: AsyncIterable<ProviderEvent>;
  abort(): void;
}
```

The Claude provider (`providers/claude.ts`) is the canonical impl. Skills that add new providers (codex, opencode, ollama) drop in another file that calls `registerProvider('codex', opts => new CodexProvider(opts))`.

### 1.4 How the Claude Agent SDK is invoked

```typescript
sdkQuery({
  prompt: stream,                              // push-based async iterable
  options: {
    cwd: '/workspace/agent',
    additionalDirectories,
    resume: input.continuation,                // session id from prior turn
    pathToClaudeCodeExecutable: '/pnpm/claude',
    systemPrompt: instructions
      ? { type: 'preset', preset: 'claude_code', append: instructions }
      : undefined,
    allowedTools: [...TOOL_ALLOWLIST, ...mcpAllowPatterns],
    disallowedTools: SDK_DISALLOWED_TOOLS,    // CronCreate, AskUserQuestion, EnterPlanMode, etc.
    env, permissionMode: 'bypassPermissions',
    allowDangerouslySkipPermissions: true,
    settingSources: ['project', 'user'],
    mcpServers,                                // nanoclaw + per-group additions
    hooks: { PreToolUse, PostToolUse, PostToolUseFailure, PreCompact },
  },
});
```

Notable choices:

- `systemPrompt` uses the SDK's `preset: 'claude_code', append: instructions` form. So the agent gets Claude Code's full default system prompt PLUS NanoClaw's runtime addendum (assistant name + destinations). The bulk of NanoClaw-specific instructions ride in via `cwd` → `CLAUDE.md` autoload, *not* via systemPrompt injection.
- `bypassPermissions` + `allowDangerouslySkipPermissions: true` because the container itself is the permission boundary.
- Several SDK-native tools are *disallowed* (`CronCreate`, `ScheduleWakeup`, `AskUserQuestion`, `EnterPlanMode`, `EnterWorktree`) — they either don't fit the headless container model or duplicate NanoClaw's MCP equivalents.
- Hooks: PreToolUse records the in-flight tool to `container_state` so host sweep can extend stuck-tolerance during long Bash runs. PreCompact archives the transcript to `groups/<folder>/conversations/<date>-<slug>.md` before the SDK truncates.

### 1.5 Built-in MCP tool registry

`container/agent-runner/src/mcp-tools/index.ts` is the barrel. Each module file (`core.ts`, `scheduling.ts`, `interactive.ts`, `agents.ts`, `self-mod.ts`) calls `registerTools([...])` at module scope; the barrel imports them all and `startMcpServer()` reads from the registry. There's a single MCP server (`mcp__nanoclaw__*`) that the agent sees alongside anything wired through `container.json.mcpServers`.

Tool categories shipped in trunk:
- **core** — `send_message`, `send_file`, `edit_message`, `add_reaction`
- **scheduling** — `schedule_task`, `list_tasks`, `update_task`, `cancel_task`, `pause_task`, `resume_task`
- **interactive** — `ask_user_question`, etc.
- **agents** — `create_agent` (admin-only)
- **self-mod** — `install_packages`, `add_mcp_server` (both fire-and-forget; admin approval required)

### 1.6 Conversation history across containers

Two layers:

1. **The `continuation` token (per provider).** Stored in `outbound.db.session_state` keyed `continuation:<provider>`. Persisted on the SDK's `init` event so a mid-turn crash doesn't orphan the session. On restart, `migrateLegacyContinuation()` adopts a single legacy `sdk_session_id` value into the current provider's slot.
2. **Long-term memory on disk.** Lives at `groups/<folder>/CLAUDE.local.md` (auto-loaded by Claude Code) and `groups/<folder>/conversations/*.md` (human-readable transcript archives written by the PreCompact hook). The `conversations/` folder is searchable from the agent's CWD. Anything more structured (per the in-container `CLAUDE.md` instructions) is the agent's own choice — it's instructed to create files like `customers.md`, `preferences.md`, etc., and index them in `CLAUDE.local.md`.

This is conceptually similar to Hermes' "memory file" pattern but more loosely structured: there's no schema for memories, just a folder the agent writes Markdown into.

---

## 2. The skills system

Three distinct things share the word "skill" in NanoClaw. Untangling this is the biggest reverse-engineering payoff of this pass.

### 2.1 Tier 1 — Operator-side skills (`.claude/skills/`)

These are **Claude Code skills run by the operator on the host**, against their cloned/forked NanoClaw repo. They're standard Claude Code skills with `SKILL.md` files containing YAML frontmatter (`name`, `description`) and Markdown bodies.

Examples: `add-discord`, `add-codex`, `add-ollama-provider`, `init-first-agent`, `customize`, `setup`, `update-skills`, `migrate-nanoclaw`, `use-native-credential-proxy`.

There are ~40 of these. The user runs them via `/add-discord` in their Claude Code session (Claude Code reads them from `.claude/skills/`).

### 2.2 Tier 2 — Agent-side skills (`container/skills/`)

These are **Claude Code skills the agent inside the container has at runtime**. They're mounted at `/app/skills/` (RO) and surfaced into the agent via two paths:

1. **Skill symlinks** in `~/.claude/skills/<skill-name>` (RW dir, RO symlink targets). The container-runner syncs these at spawn from `container.json.skills` (default `'all'`). Claude Code reads from `~/.claude/skills/` (settingSources: `['project', 'user']`).
2. **Composed CLAUDE.md fragments** for any skill that ships an `instructions.md` alongside its `SKILL.md`. The host's `composeGroupClaudeMd()` walks `container/skills/<name>/instructions.md` and adds an import to the per-group `CLAUDE.md`. This makes the skill's guidance *always-on* (inline in the system prompt) rather than lazy-loaded by the model when it decides to invoke `Skill('<name>')`.

Trunk ships 7 agent-side skills: `agent-browser`, `frontend-engineer`, `onecli-gateway`, `self-customize`, `slack-formatting`, `vercel-cli`, `welcome`. Only `onecli-gateway` ships an `instructions.md` (always-on). The rest are model-discovered via Claude Code's normal skill-search pathway.

### 2.3 Tier 3 — The "skill installer" (`/add-X` mechanism)

This is the one Bryan is asking about. It's *not* a templating system, generator, or registry. It's **branch-based code grafting**, performed by a Claude Code skill in tier 1.

Mechanism, walking through `/add-discord` and `/add-codex`:

1. Operator runs `/add-discord` in Claude Code. The skill's `SKILL.md` is the operator-facing recipe.
2. The recipe reads:
   ```
   git fetch origin channels
   git show origin/channels:src/channels/discord.ts > src/channels/discord.ts
   # (append) import './discord.js'; to src/channels/index.ts
   pnpm install @chat-adapter/discord@4.27.0
   pnpm run build
   ```
3. NanoClaw uses **separate git branches** (`channels`, `providers`, etc.) that hold optional modules. Trunk ships only the bare minimum (`claude` provider, no channels). Skills "install" by `git fetch` + `git show` + write the file in place.
4. Self-registration imports are appended to barrel files. There's no plugin manifest — the architecture relies on the side-effect-import pattern (each module file calls `registerProvider(...)` or `import './discord.js'` at module scope, and barrels just need the import line added).
5. For provider skills like `/add-codex`, the recipe also bumps the Dockerfile (adds `ARG CODEX_VERSION` and a per-CLI `RUN pnpm install -g` block), then rebuilds the image.

Implications:
- **Skills are owned files.** Once installed, `src/channels/discord.ts` is just a normal source file in the operator's fork. Any local edits survive — but `/update-skills` (which re-runs `git merge upstream/skill/<name>`) will conflict with them.
- **There's no skill manifest, registry, or DB row.** The presence of the file plus the import line is the registration.
- **`update-skills` is a separate skill** that fetches and merges the upstream skill branches the user has previously merged.
- **`/add-X` skills are idempotent** by design — every step has a "skip if already in place" preflight.

### 2.4 Where skill metadata lives

| Where | What | Who reads |
|---|---|---|
| `.claude/skills/<name>/SKILL.md` | Operator-facing recipe (frontmatter + Markdown) | Claude Code on the host |
| `container/skills/<name>/SKILL.md` | Agent-facing skill (lazy-loaded by Claude Code in the container) | Claude Code in the container |
| `container/skills/<name>/instructions.md` | Always-on fragment for the composed CLAUDE.md | Claude Code in the container (via system prompt) |
| `container.json` `skills: ['name1','name2'] \| 'all'` | Per-group skill selection — controls which `~/.claude/skills/<name>` symlinks are synced | container-runner.syncSkillSymlinks() |
| Git branches `skill/<name>` (or branches like `channels`, `providers`) | The actual installable code | `/add-X` recipes via `git fetch`/`git show` |

So an "installable skill" in NanoClaw is a 4-tuple: a recipe in `.claude/skills/`, a git branch with the source, a barrel-import line to add, and (for code-modifying skills) a Dockerfile/test diff. Genuinely no central registry.

---

## 3. Database layer

### 3.1 Three databases

**Host central DB** (`data/v2.db`) — one file. Holds:
- `agent_groups` (id, name, folder, agent_provider, created_at) — note: container config is *not* in the DB; it lives in `groups/<folder>/container.json`
- `messaging_groups` (id, channel_type, platform_id, name, is_group, unknown_sender_policy)
- `messaging_group_agents` (the wiring + engage_mode/engage_pattern/sender_scope/ignored_message_policy)
- `users`, `user_roles`, `agent_group_members`, `user_dms`
- `sessions` (id, agent_group_id, messaging_group_id, thread_id, agent_provider, status, container_status, last_active, created_at)
- `pending_questions`, `pending_sender_approvals`, `delivered`, `agent_destinations` (a2a routing + ACL)
- Plus module tables (added by skills): `dropped_messages`, scheduling tables, approvals tables

**Per-session inbound.db** (host writes, container reads): `messages_in`, `delivered`, `destinations`, `session_routing`.

**Per-session outbound.db** (container writes, host reads): `messages_out`, `processing_ack`, `session_state` (persistent KV, holds the `continuation:<provider>` row), `container_state` (current tool + declared timeout).

The two-DB-per-session split exists to **eliminate SQLite cross-mount write contention**. SQLite tolerates one writer per file very well; multi-writer is painful especially across the host-container boundary. By making each file single-writer, all the IPC just works.

### 3.2 Migrations

`src/db/migrations/index.ts` is the runner. Pattern:

```typescript
interface Migration { version: number; name: string; up: (db) => void; }
const migrations: Migration[] = [migration001, migration002, ...module..., migration008, ...];
runMigrations(db) // creates schema_version table, applies missing migrations in array order
```

Two interesting touches:

1. **Uniqueness is keyed on `name`, not `version`.** That lets module migrations (added later by install skills) pick arbitrary version numbers without coordinating across modules.
2. **Some migrations carry a `module-` filename prefix.** Look at `module-agent-to-agent-destinations.ts`, `module-approvals-pending-approvals.ts`. These are migrations that were originally added by a module/skill install and later promoted into trunk (with the `module-` prefix preserved on the file but the original migration `name` field kept stable so existing DBs don't re-run them). This is a clever pattern for handling "skills graduated to trunk" without forcing a re-migration.

### 3.3 What persists where

- **Host-permanent state**: `data/v2.db`, `groups/<folder>/CLAUDE.local.md`, `groups/<folder>/conversations/*.md`, `groups/<folder>/container.json`, `groups/<folder>/<any agent-created files>`. All survive container restart.
- **Per-session ephemeral state**: `data/v2-sessions/<agent-group-id>/sessions/<session-id>/{inbound.db, outbound.db, .heartbeat, outbox/}`. Survives container restart, deleted with the session.
- **Container-only state**: nothing meaningful. The image is rebuilt on package install, but agent-runner source is RO-mounted from host. The container itself is `--rm` per spawn.

---

## 4. Group template (a fresh group folder)

`groups/<folder>/` after init holds (from `src/group-init.ts` and `src/claude-md-compose.ts`):

| File | Purpose | Writability inside container |
|---|---|---|
| `CLAUDE.md` | Composed entry — imports only. Header says "do not edit, regenerated every spawn." | RO (nested mount) |
| `CLAUDE.local.md` | Per-group memory, auto-loaded by Claude Code. Seeded with caller-provided instructions on first creation. | **RW** |
| `container.json` | Per-group container config. Mounted RO inside container. | RO (nested mount) |
| `.claude-shared.md` | Symlink → `/app/CLAUDE.md` (shared base mounted RO from `container/CLAUDE.md`) | RO via target |
| `.claude-fragments/` | Composed-at-spawn skill + MCP fragments. Each is either a symlink to `/app/skills/<name>/instructions.md` or `/app/src/mcp-tools/<name>.instructions.md`, or an inline file for `mcp.instructions` from container.json. | RO (nested mount) |
| `conversations/` | Auto-archived transcripts (PreCompact hook) | **RW** |
| `(agent-created files)` | Whatever the agent has written — `customers.md`, `preferences.md`, etc. | **RW** |

`container.json` shape (`src/container-config.ts`):

```typescript
{
  mcpServers: { [name]: { command, args?, env?, instructions? } },
  packages: { apt: string[], npm: string[] },
  imageTag?: string,        // per-agent-group rebuilt image
  additionalMounts: [{ hostPath, containerPath, readonly? }],
  skills: string[] | 'all',
  provider?: 'claude' | 'codex' | 'opencode' | ...,
  groupName?: string,
  assistantName?: string,
  agentGroupId?: string,
  maxMessagesPerPrompt?: number,
}
```

**The composed CLAUDE.md is `groups/<folder>/CLAUDE.md`**, regenerated every spawn. Its body is just a header + sorted list of `@./.claude-shared.md` and `@./.claude-fragments/<name>.md` import lines. The agent never edits it; it edits `CLAUDE.local.md`.

The `groups/global/` folder existed pre-cutover; `migrateGroupsToClaudeLocal()` deletes it on first run and consolidates content into `container/CLAUDE.md` (the shared base). Trunk currently still has `groups/global/CLAUDE.md` and `groups/main/CLAUDE.md` as reference templates, but the migration removes them after init.

---

## 5. Providers

Two parallel registries, host-side and container-side:

### 5.1 Container-side (the actual provider impl)

`container/agent-runner/src/providers/provider-registry.ts` (inferred from claude.ts and factory.ts) holds a name → factory function map. Each provider file calls `registerProvider('claude', opts => new ClaudeProvider(opts))` at module scope. The barrel (`providers/index.ts`) imports each provider file for side effects. Skills add a provider by creating `providers/<name>.ts` and appending `import './<name>.js'` to the barrel.

Currently shipped in trunk: `claude` and `mock` (for tests). Codex, OpenCode, Ollama provider come in via `/add-codex`, `/add-opencode`, `/add-ollama-provider` skills.

### 5.2 Host-side (per-spawn container config contributions)

`src/providers/provider-container-registry.ts` is parallel: name → function returning `{ mounts?, env? }`. Used at container spawn to inject provider-specific extras (e.g. mount a per-session `~/.codex` directory for the Codex provider, or set `XDG_DATA_HOME` for OpenCode).

```typescript
ProviderContainerContextFn(ctx: { sessionDir, agentGroupId, hostEnv }) → { mounts?, env? }
```

Providers without host-side needs (claude default, mock) don't appear here — `getProviderContainerConfig(name)` returns undefined and the spawn proceeds with default mounts/env.

### 5.3 Provider precedence

```
sessions.agent_provider → agent_groups.agent_provider → container.json.provider → 'claude'
```

This is in `resolveProviderName()` in `container-runner.ts`, with a unit test (`container-runner.test.ts`). The DB columns drive *host-side* contribution selection, not the in-container runner's choice — the runner reads `provider` from `container.json` directly. The host writes both, in sync, when activating a provider.

### 5.4 Credentials

OneCLI is the credential mechanism for *every* provider. The Claude provider's host-side config (`src/providers/claude.ts`) optionally sets `ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN=placeholder` so the SDK adds an Authorization header that OneCLI rewrites on the wire. Real credentials never enter the container.

---

## 6. Router/delivery flow (high level)

The host-side flow at 30,000 ft:

```
channel adapter event (Discord/Slack/etc.)
    ↓
src/router.ts: routeInbound(event)
    ├─ messageInterceptor hook (permissions module) — consume? bail.
    ├─ resolve messaging_group + agent count
    │   └─ no agents wired? drop or escalate via channelRequestGate (permissions module)
    ├─ senderResolver hook → user_id
    ├─ accessGate hook (permissions module)
    ├─ for each wired agent:
    │   evaluate engage_mode (mention | mention-sticky | pattern)
    │   │            sender_scope (all | known)
    │   │            ignored_message_policy (drop | accumulate)
    │   resolveSession → write messages_in row → wakeContainer(session)
    ↓
src/container-runner.ts: wakeContainer(session)
    ├─ buildMounts() — initGroupFilesystem, syncSkillSymlinks, composeGroupClaudeMd
    ├─ buildContainerArgs() — OneCLI gateway, host gateway, UID mapping, mounts, image
    └─ docker run --rm ...
    ↓
[container running, poll loop reading inbound.db, writing outbound.db]
    ↓
src/delivery.ts: startActiveDeliveryPoll() (1s) + startSweepDeliveryPoll() (60s)
    └─ for each session: read undelivered messages_out (RO), call channel adapter, mark delivered (in inbound.db)
    ↓
channel adapter sends to platform
```

Container spawn is **router-driven** (synchronous on inbound message) plus host-sweep-driven (catches stuck sessions, retries failed wakes). The container is always per-session; multiple sessions = multiple containers.

Concurrency model: single Node process for the host, multiple Docker children. SQLite handles host-process concurrency; per-session DB files handle host↔container concurrency. No threads, no shared mutable state across sessions.

---

## 7. Test patterns

`vitest.config.ts` runs `src/**/*.test.ts`, `setup/**/*.test.ts`, `scripts/**/*.test.ts`. `vitest.skills.config.ts` runs `.claude/skills/**/tests/*.test.ts` (skill-bundled tests). Container tests run under **Bun** (not Vitest) because they depend on `bun:sqlite` — see `container/agent-runner/package.json`.

Test categories observed:
- **Pure unit tests** — `resolveProviderName`, `attachment-naming`, `circuit-breaker`, `timezone`. Smallest, fastest, most numerous.
- **DB tests** — `db-v2.test.ts`, `session-db.test.ts`. Spin up an in-memory or temp-file SQLite, exercise migrations + queries.
- **Integration tests** — `container/agent-runner/src/integration.test.ts`. Spins up the poll loop with a `MockProvider` (returns canned responses), seeds messages_in, asserts on messages_out. **No real container, no real Claude SDK.**
- **Module tests** — `src/modules/<module>/<feature>.test.ts`. Each module ships its own tests.
- **Skill tests** — bundled with skills under `.claude/skills/<name>/tests/`. Nice pattern for skill authors.

What's missing:
- **No tests that spin up real Docker containers.** The container-runner tests cover building args, not actually running. There's a `container-runner.test.ts` but it covers `resolveProviderName`, not the spawn path.
- **No tests against real Claude API.** Everything that touches the Anthropic SDK is exercised via `MockProvider`.

Patterns worth borrowing for Whizzard:
- The MockProvider pattern (a fake AgentProvider that returns canned text) lets the entire poll loop run in-process. Whizzard's harness adapter has a similar shape; we could expose a `MockHarness` for the same purpose.
- Skill-bundled tests (`.claude/skills/<name>/tests/`). If we ever build a Whizzard plugin/skill model, this is a clean separation.
- `vitest.skills.config.ts` as a separate config keeps skill tests from running on the main suite by default. Faster main suite, opt-in skill suite.

---

## 8. Implications for the self-learning skill use case

Concretely, what would a "Hermes-style self-improvement" NanoClaw skill need to do?

### 8.1 Skill authoring (write-time)

Hermes-style: the agent decides "I should make this a reusable skill" and writes a new skill file.

**The hard problem in NanoClaw**: existing skills are git-branch-distributed and live in `container/skills/<name>/`. The agent inside the container has *no write access* to that path (it's mounted RO from `/app/skills/`). So a self-authored skill can't go where existing skills go.

**The plausible answer**: a separate skill-storage tier with its own mount.

```
groups/<folder>/skills/<self-authored-name>/SKILL.md   # written by agent (RW)
```

This requires:
1. A new mount in `container-runner.buildMounts()`: `groups/<folder>/skills/` → `~/.claude/skills/<group>/` (RW from container's POV).
2. A composer hook to symlink/copy each self-authored skill's `instructions.md` (if any) into `.claude-fragments/`.
3. (Optional) A separate symlink namespace so self-authored skills don't shadow trunk-shipped ones.

**Or** the self-learning skill could piggy-back on `CLAUDE.local.md` only — the agent appends sections describing learned patterns there, and they get auto-loaded next session. That's smaller but loses the "skill is callable as `/skill-name`" affordance.

### 8.2 Memory accumulation (read-time)

NanoClaw already has solid infrastructure here:
- `CLAUDE.local.md` is auto-loaded every spawn. Agent already writes to it.
- `conversations/` archives are written by the PreCompact hook.
- The agent is instructed to create structured files (`customers.md`, etc.) and index them in `CLAUDE.local.md`.

A Hermes-style memory system fits cleanly. The marginal additions would be:
- A more structured memory schema (Hermes uses something like `~/memories/<topic>.md`). Could mirror as `groups/<folder>/memories/`.
- A retrieval mechanism beyond "the agent reads its own files" — e.g. an MCP tool `recall_memory` that does semantic search over the memory folder. Cheaper hack: a `find_memory` Bash skill.

### 8.3 Curator agent

The `create_agent` MCP tool already supports spawning a long-lived companion agent. A "curator" pattern would be:

1. Main agent finishes a turn.
2. Optionally, a scheduled task fires (e.g., daily `0 3 * * *`) that delegates curation to a `Curator` companion agent via `send_message(to: "curator", ...)`.
3. The Curator reads the main agent's `groups/<folder>/conversations/*.md` and `CLAUDE.local.md`, decides what's worth promoting to a skill or distilled memory, and writes back.

`groups/<folder>/` is the main agent's RW home. The Curator would need cross-agent file access. Two ways:
- Mount the main agent's `groups/<folder>/` into the Curator's container as `additionalMounts`. Already supported via `container.json.additionalMounts`. **The Curator becomes a privileged agent** that can write into the main's memory.
- Or have the Curator emit recommendations as messages back to the main agent, which then chooses to apply them itself (less powerful, no privilege concern).

### 8.4 Where skill files would live

Three options, in increasing complexity:

| Option | Path | Pros | Cons |
|---|---|---|---|
| Agent-memory only | `groups/<folder>/memories/*.md` plus existing `CLAUDE.local.md` indexing | Smallest change. Already RW. Already loaded. | Not invokable as a Claude Code "skill"; loses the lazy-load token benefit. |
| Per-group skills | `groups/<folder>/skills/<name>/SKILL.md` | Properly invokable. Per-group isolated. Doesn't conflict with trunk. | New mount + composer changes. Need to think about how `/update-skills` interacts. |
| Promote to global | Self-authored skill becomes a candidate for promotion into `container/skills/` via human review | Clean upstream story. Reviewable. | Crosses a privilege boundary the Curator doesn't have. Probably out of scope for an MVP. |

### 8.5 Blockers / design tensions

1. **Branch-based distribution doesn't model self-authored skills.** `/update-skills` would treat a self-authored skill as "not installed" and ignore it; the operator's `git status` would be perpetually dirty. Probably need to gitignore `groups/<folder>/skills/` (already implicitly true since `groups/` is user state).
2. **CLAUDE.md is regenerated every spawn.** Self-authored skills need to either ship `instructions.md` (so the composer picks them up) or rely on Claude Code's lazy `Skill('<name>')` invocation. Mixing both works but doubles the surface.
3. **The container is RW for `groups/<folder>/` already**, so the agent can write skill files. But it cannot trigger a recompose of CLAUDE.md mid-session — that happens at next spawn. So a self-authored skill won't be active until the container restarts. This is probably fine (the act of authoring + a clear restart boundary is good UX) but worth being explicit about.
4. **No semantic retrieval primitive.** Hermes' memory model assumes some form of relevance ranking. NanoClaw is filename-based + grep. Adding embeddings would be a meaningful new dependency.
5. **Curator privilege model is fuzzy.** A Curator agent that can edit another agent's `CLAUDE.local.md` is, in NanoClaw's vocabulary, an admin-level operation. The existing access model (user roles + agent_group_members) doesn't have a "this agent has write access to that agent's memory" primitive. Could be hacked via `additionalMounts` but it's a privilege escalation worth doing deliberately.
6. **Self-mod approval flow doesn't currently model "I authored a new skill."** `install_packages` and `add_mcp_server` both go through admin approval. A new skill is a similar privilege jump (the agent is teaching itself a new behavior). Probably want a parallel `register_skill` MCP tool with the same approval flow.

### 8.6 What the upstream PR would actually contain

Roughly:

1. New mount: `groups/<folder>/skills/` → `~/.claude/skills/<group>/` RW.
2. Composer extension in `claude-md-compose.ts`: walk per-group skills for `instructions.md` files, add them to fragments.
3. (Optional) New MCP tool `register_skill` with admin approval — fire-and-forget pattern matching `install_packages`.
4. Documentation in `container/CLAUDE.md` or a new shared instruction fragment explaining when the agent should author a skill vs. just write to memory.
5. A Curator example: a `/spawn-curator` operator-side skill that creates a `create_agent` companion with the right `additionalMounts` and a CLAUDE.local.md describing the curation contract.
6. (Optional) A `recall_memory` MCP tool with simple grep-based retrieval over `groups/<folder>/memories/` and `groups/<folder>/conversations/`.

The minimum viable PR is items 1, 2, and 4. Items 3, 5, 6 are stretch.

---

## 9. Implications for Whizzard architecture

### 9.1 Patterns worth borrowing

- **The composed-at-spawn config pattern.** Hermes-style harnesses inside Whizzard could benefit from a "regenerate config on container start" model where the agent's instruction surface is composed from a shared base + per-instance fragments. NanoClaw's `composeGroupClaudeMd()` is a clean reference. Stage 7's adapter registry already has a similar shape (registry → harness-specific `prepare`); we could extend that to compose per-run instruction files into a known location the harness reads.
- **The single-MCP-server-with-side-effect-imports pattern.** NanoClaw's `mcp-tools/index.ts` is small, declarative, and trivially extensible. If Whizzard ever ships an "in-container helper" (e.g., a `whizzard` CLI inside the container that exposes audit-log read-back, or a status check), this is the right shape.
- **The two-DB-per-session split.** Eliminates SQLite write contention across the host-container boundary at zero cost. If we ever introduce IPC beyond env vars + log files (e.g. for streaming progress), this is worth knowing.
- **Mock provider for end-to-end loop testing.** A MockHarness that returns canned outputs lets us test the entire Whizzard runner without spawning Docker. Worth adding to the test harness.
- **Module-prefixed migrations.** If Whizzard ever ships an extension/plugin model, migrations contributed by extensions can use the `module-` prefix pattern to graduate cleanly into trunk without forcing re-migrations.
- **Per-session ephemeral state directory + per-permanent state directory split.** NanoClaw cleanly separates `data/v2-sessions/<id>/` (ephemeral, session-scoped) from `groups/<folder>/` (permanent, group-scoped). Whizzard's session log + future state stores should mirror this — ephemeral state in `data/sessions/<id>/`, permanent state in `~/.whizzard/<...>`.

### 9.2 Patterns to NOT borrow

- **Branch-based skill distribution.** Cool, defensible for NanoClaw's "fork and customize" UX. Wrong fit for Whizzard's "policy layer that wraps any harness" UX. Whizzard skills (if any) should be installable artifacts, not git grafts.
- **Multi-channel adapter framework.** Already covered in nanoclaw_research.md. Whizzard isn't an agent platform.
- **Per-agent-group container image rebuild.** NanoClaw rebuilds an image per agent group when packages are installed. Whizzard's containment model is meant to wrap a harness, not own the image lifecycle — image management stays Stage 9 (digest-pinned, host-managed).
- **`bypassPermissions: true` + `allowDangerouslySkipPermissions: true`.** NanoClaw can do this because the container is the boundary. Whizzard wraps harnesses; harness-level permission posture is a harness decision, not Whizzard's. Make sure adapters don't paper over the harness's own permission model.

### 9.3 Architectural validation

NanoClaw confirms several Whizzard design choices:

- **Mount registry + safety policy.** Their per-mount RO/RW + nested mount tricks (composed CLAUDE.md is RW group dir + nested RO `CLAUDE.md` mount) are the same pattern Whizzard uses for protected paths.
- **Per-session ephemeral container.** Same model. Different lifecycle reasons (ours: fresh containment per session; theirs: easy crash recovery), same outcome.
- **OneCLI-style credential isolation as the right answer for vault.** Already validated.

---

## 10. Open questions for Bryan

In rough priority order for the self-learning skill use case:

1. **Is the goal of the upstream PR (a) to add filesystem-resident self-authored skills to NanoClaw, or (b) to demonstrate a curator-agent pattern using existing primitives?** (a) requires real surgery on the composer + new mounts; (b) might be doable purely with `create_agent` + `additionalMounts` + documentation, no code changes. Different shapes.
2. **Is "self-learning" mostly about authoring skill files, or mostly about memory accumulation and retrieval?** NanoClaw already does most of the memory side (CLAUDE.local.md + conversations folder). The skill-authoring side is the bigger architectural change. Deciding the priority shapes the PR scope.
3. **Should the curator be inline (same agent, same turn, same context budget) or a separate agent (`create_agent` companion)?** NanoClaw's architecture pushes hard toward separate-agent-companion (`create_agent` exists, scheduling exists, agent destinations exist). Inline curation would be cheaper but fights the model.
4. **Does Whizzard need its own equivalent of the "skill" concept eventually?** If the answer is "no, harnesses bring their own skill models," then everything we learn here is about NanoClaw's PR, not Whizzard's design. If the answer is "yes, Whizzard plugins should be installable extensions," then the branch-grafting model is something to evaluate explicitly (probably reject) for our own purposes.
5. **How does the self-learning loop interact with the OneCLI vault?** If a self-authored skill needs new API access (e.g., an embedding API for memory retrieval), it has to go through the same `add_mcp_server` + admin approval flow. Worth checking that the curator pattern doesn't introduce a credential side-channel.
6. **Do we want a `recall_memory` MCP tool to be embedding-backed or grep-backed for v1?** Grep-backed is trivial and lands today; embedding-backed adds a dependency (vector DB? local model?) that NanoClaw has so far avoided. The decision likely lives downstream of question 2.
7. **Is there an opportunity to test the curator pattern via a Whizzard adapter rather than as a NanoClaw upstream PR?** Whizzard's harness model could host a "Hermes inside NanoClaw inside Whizzard" stack to evaluate the pattern without committing to NanoClaw's design first. Probably overkill but worth flagging.

---

## Bottom line

NanoClaw's internals are smaller and more declarative than they look from the outside. The skill installer is git-branch-grafting plus barrel-import side effects, not a registry. The composed CLAUDE.md is the closest existing analogue to a Hermes-style dynamic skill loader, and it's where a self-learning system would most naturally plug in. The agent-runner is a clean poll-loop + provider abstraction with one MCP server. The DB layer's two-files-per-session split is a smart trick worth remembering.

A Hermes-style self-learning skill is *plausible* as an upstream PR but is not a small change. The minimum surface is: new mount for per-group user-authored skills, composer extension to load their fragments, documentation about when to author vs. when to memorize. The curator pattern is largely free given `create_agent` already exists; the question is whether the curator-as-separate-agent model fits Hermes' inline-curation expectations.
