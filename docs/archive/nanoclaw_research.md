# NanoClaw Research Notes (v2)

Deep-dive review of [nanocoai/nanoclaw](https://github.com/nanocoai/nanoclaw) — refreshed to cover the v2.0 architectural rewrite (shipped 2026-04-22) and subsequent micro-version refinements through ~v2.0.63. Replaces the v1-era artifact written 2026-05-08.

Original purpose preserved: assess container hardening, UID handling, credential model, mount policy, and how NanoClaw's design compares to what Whizzard provides — with NanoClaw's v2 changes called out where they alter prior conclusions.

Written: 2026-05-28.

---

## TL;DR

NanoClaw v2 is a substantial architectural rewrite — entity model, two-DB-per-session split, channels/providers extracted to sibling branches, an `ncl` admin CLI, container_configs in the DB rather than on disk — but **the security posture of the container itself is essentially unchanged from v1**. v2 still spawns a Docker container with no capability dropping, no `--read-only`, no `--security-opt no-new-privileges`, no tmpfs, and no network restrictions. The v2 rewrite was about architecture and developer experience, not container hardening.

That means the **Whizzard hardening differential (D-93) survives the v2 rewrite intact**. Whizzard remains meaningfully stronger at the container-internal threat model.

Two things v2 sharpens in NanoClaw's favor:

- **OneCLI Agent Vault is now mandatory.** v1 made it optional alongside `.env`; v2 hard-fails the container spawn if the OneCLI gateway can't be applied. Credentials never enter the container, full stop. This strengthens our adoption thesis (D-91 / D-98 / D-134) and removes any ambiguity about the pattern's production-readiness.
- **A real admin CLI (`ncl`) exists.** v1 had ad-hoc commands and an `is_main` group convention; v2 has explicit users, roles, scoped permissions, and a CLI that traverses the same central DB whether invoked from the host (Unix socket) or from inside a container (session-DB transport with approval gating). This is a more mature model than what we had described before.

Product positioning is unchanged: NanoClaw is **an opinionated personal AI assistant platform** that happens to use containers; Whizzard is **a containment layer** that runs whatever harness you point it at. The complementarity argument (D-172) still holds — and arguably is stronger now that NanoClaw v2 has further specialized as a personal-platform shape rather than a generic harness.

---

## What NanoClaw is (current state)

From the v2 README:

> An AI assistant that runs agents securely in their own containers. Lightweight, built to be easily understood and completely customized for your needs.

Still fork-and-customize as a distribution model, with a sharper "skills over features" philosophy in v2: trunk ships **registry + infrastructure only**; channel adapters (Discord, Slack, Telegram, WhatsApp, iMessage, Teams, Matrix, Webex, GitHub, Linear, etc.) and alternative providers (OpenCode, Codex, Ollama) live on the `channels` and `providers` branches respectively, installed per-fork via `/add-<channel>` / `/add-<provider>` skills.

**Stack (v2):**
- Host process: Node 22 + pnpm 10 (router, delivery, container-runner)
- Container: Bun 1.3+ (the v1-era Node container moved to Bun for cold-start + supply-chain reasons)
- DBs:
  - Central: `data/v2.db` (entities, roles, wirings, container_configs, schema migrations)
  - Per-session: `data/v2-sessions/<agent_group_id>/<session_id>/inbound.db` (host writes, container reads) and `outbound.db` (container writes, host reads)
- Runtime: Docker on macOS/Linux/Windows (WSL2) by default; Apple Container is now **opt-in only** (`/convert-to-apple-container`); Docker Sandboxes (micro-VM isolation) remains an optional layer
- Credentials: **OneCLI Agent Vault — mandatory**, gateway pinned to 1.23.0
- Admin: `ncl` CLI (Unix socket on host, session-DB transport from inside containers, write ops gated by approval flow)

**Architecture (v2):**

```
messaging apps → host (router) → session inbound.db → container (Bun, Claude Agent SDK)
                                                       → session outbound.db → host (delivery) → messaging apps

   ↑ central data/v2.db: users, roles, agent_groups, messaging_groups, wirings, container_configs, sessions
```

The host is a long-running Node process. Per session, a container is spawned on-demand, polls its mounted `inbound.db`, runs Claude, writes to `outbound.db`, and exits when idle. Exactly **one writer per file** is the load-bearing invariant — and a heartbeat is a file `touch` rather than a DB write to keep that constraint clean.

**Three-level isolation model** (from `docs/isolation-model.md`):

1. **Shared session** — multiple messaging_groups → same agent_group, `session_mode='agent-shared'`. All channels converge on one conversation.
2. **Same agent, separate sessions** — multiple messaging_groups → same agent_group, `session_mode='shared'` (or `'per-thread'`). Same workspace/memory/CLAUDE.md across channels but independent conversation threads.
3. **Separate agent groups** — each messaging_group → its own agent_group with its own folder, memory, container.

The user chooses which level per channel pairing. This is a cleaner, more explicit framing than the v1 main/non-main distinction.

---

## v2 architectural shifts that affect this analysis

Summarizing the v2 changes that are load-bearing for our differential analysis, with implications:

| Change | Impact on Whizzard analysis |
|---|---|
| Entity model rewritten (users / roles / agent_groups / messaging_groups as separate entities; many-to-many wiring) | Doesn't change container hardening; clarifies that NanoClaw is now firmly a "personal agent platform" shape, sharpening D-172 complementarity argument. |
| Two-DB-per-session split (inbound + outbound, one writer each) | Cleaner host↔container IPC; **a Whizzard adapter would need to leave these mounts intact** — they're how the harness functions. |
| Channels / providers moved to sibling branches; skill-installed per fork | Whizzard remains harness-agnostic; we don't need to know which channels a NanoClaw install has wired. |
| Container runtime moved Node → Bun (host stays Node + pnpm) | Doesn't affect containment posture; matters only for image-build assumptions. |
| Apple Container removed from default setup, opt-in only | Whizzard would containerize the Docker path; Apple Container is irrelevant unless we adapt to it explicitly. |
| Shared-source agent-runner mounted read-only to every group | Reduces per-group write surface — confirms the "shared infra, scoped state" pattern. |
| Container config moved from `groups/<folder>/container.json` to `container_configs` DB table (v2.0.48) | A Whizzard adapter would still need to **read the materialized `container.json`** (NanoClaw still writes the JSON at spawn time so the runtime can pick it up). The DB is the source of truth, but the on-disk JSON is the surface Whizzard would consume. |
| New `ncl` admin CLI (v2.0.45) with approval flow for container-side writes | Doesn't affect containment, but is a clean pattern Whizzard could borrow from — approval-gated mutations from inside the container. |
| OneCLI gateway is the **sole** credential path; container spawn hard-fails if gateway not applied | Strengthens D-98 / D-134 substantially; NanoClaw is now the unambiguous proof-point. |
| Repo rename qwibitai → nanocoai (v2.0.63); per-install service slugging | Just a URL change; old name still resolves. Update internal references. |

---

## Container hardening posture

This section is the load-bearing one for our pitch and our differential.

### What v2 DOES (verified against `src/container-runner.ts` on `main`)

| Control | NanoClaw v2 | Source |
|---|---|---|
| `--rm` ephemeral containers | Yes | `container-runner.ts:408` |
| Non-root user | Default UID 1000 (`node` from base image); overrides to host UID on macOS via `--user $UID:$GID` + `HOME=/home/node` | `container-runner.ts:441–443` |
| Container label for orphan-cleanup | `nanoclaw-install=<slug>`, install-scoped | `container-runner.ts:408` |
| Per-mount read-only flag | Honored via `readonlyMountArgs()` helper | `container-runner.ts:448–451` |
| Shared agent-runner source mounted **read-only** for every group | Yes — `/app/src` is RO from `agent-runner-src/` | `container-runner.ts:313–315` |
| Global memory mounted **read-only** | Yes — `/workspace/global` is RO | `container-runner.ts:296–299` |
| Composed CLAUDE.md mounted **read-only** | Yes — agent can't tamper with the composition | `container-runner.ts:282–293` |
| Mount allowlist outside agent reach | Mount permissions live in `container_configs` table in central DB (per-group `additionalMounts`); not visible inside the container | `docs/SECURITY.md` + their CLAUDE.md |
| Default blocked path patterns | `.ssh, .gnupg, .aws, .azure, .gcloud, .kube, .docker, credentials, .env, .netrc, .npmrc, id_rsa, id_ed25519, private_key, .secret` | `docs/SECURITY.md` |
| Symlink resolution before validation | Yes | `docs/SECURITY.md` |
| Container path validation (rejects `..` and absolute paths) | Yes | `docs/SECURITY.md` |
| `.env` shadowed with `/dev/null` in project-root mount | Yes — explicit | `docs/SECURITY.md` |
| OneCLI gateway as sole credential path; hard-fail on misconfiguration | Yes — `throw new Error('OneCLI gateway not applied — refusing to spawn container without credentials')` | `container-runner.ts:432–434` |
| Heartbeat as file `touch`, not DB write | Yes — preserves single-writer invariant | `docs/v1-to-v2-changes.md` |
| Per-session DB pair (one writer each) | Yes | `docs/db-session.md` |
| Supply-chain controls on host (pnpm) | `minimumReleaseAge: 4320` (3-day hold), `onlyBuiltDependencies` allowlist | `docs/SECURITY.md` |

The "scope reduction" story is well-executed: minimal mounts, every mount that doesn't need to be writable is RO, the agent literally never sees credential material, and the container is ephemeral.

### What v2 still DOES NOT do

Reading the actual `buildContainerArgs()` in `src/container-runner.ts` lines 408–462, v2 still doesn't apply any of these:

| Hardening | Whizzard | NanoClaw v2 |
|---|---|---|
| `--cap-drop=ALL` | ✓ | ✗ (Docker default capability set retained: CAP_NET_RAW, CAP_SETUID, CAP_SETGID, CAP_CHOWN, etc.) |
| `--security-opt no-new-privileges` | ✓ | ✗ |
| `--read-only` (root filesystem) | ✓ | ✗ (writable rootfs) |
| `--tmpfs /tmp:rw,...` | ✓ | ✗ |
| `--tmpfs` for writable home | ✓ | ✗ |
| `--network none` for offline profiles | ✓ profile-driven | ✗ network is unrestricted (subject to OneCLI proxy for credential injection) |
| Image pinning by digest | Stage 9 (planned) | ✗ uses tags (`CLAUDE_CODE_VERSION`, `BUN_VERSION`, etc., pinned but tag-based) |
| Session duration enforcement | session_log + planned enforcement | ✗ (containers are ephemeral but no time bound) |
| Audit-grade JSONL session log w/ mounts, image, overrides | ✓ | ✗ — operational logs only |

I verified this directly by fetching `src/container-runner.ts` from `main` and grepping for the relevant flags; none appear. The function builds args in this order: `run --rm --name <n> --label <l>`, `-e TZ=...`, provider env, OneCLI proxy env (HTTPS_PROXY + certs), host gateway args, optional `--user` and `HOME`, per-mount `-v` flags, `--entrypoint bash`, image tag, `-c 'exec bun run /app/src/index.ts'`. No hardening flags.

### What this means for the differential

NanoClaw's design posture is still **"isolation through scope reduction"** — give the agent a small, well-defined surface and make sure credentials can't be exfiltrated, but don't try to harden the inside of the container. The threat model is something like: a misbehaving agent can do whatever it wants inside its container, but the blast radius is bounded by mounts (limited filesystem) + OneCLI (no credentials in scope) + ephemerality (no persistence). Network is unrestricted because the gateway is the policy point.

Whizzard's design posture is **"isolation through scope reduction PLUS aggressive container-internal hardening."** Same mount-and-credential scope-reduction story, but with the additional belt-and-braces of cap-drop, read-only rootfs, no-new-privileges, tmpfs, and profile-driven network policy — so even if an attacker gets execution inside the container, the kernel surface is meaningfully narrower.

Both are defensible designs. NanoClaw's is simpler and easier to maintain in a small codebase. Whizzard's is more defensive and pitches well to anyone whose threat model includes "what if the agent itself does something weird?" — exactly the FDE-style enterprise-pitch surface.

**D-93 holds.** The hardening differential is intact and is the right thing to keep emphasizing.

---

## Credential model — OneCLI is mandatory in v2

The thing that was the standout in v1 has been hardened in v2: credentials don't just *avoid* entering the container, the system *refuses to start* if it can't enforce that.

**Mechanism (verified via `src/container-runner.ts:417–434`):**

1. User registers credentials with OneCLI: `onecli secrets create`. Stored on host, managed by OneCLI gateway service (pinned to v1.23.0).
2. When NanoClaw spawns a container for an agent group, it calls `onecli.ensureAgent({ name, identifier })` to make sure a per-agent vault identity exists.
3. It then calls `onecli.applyContainerConfig(args, { agent: identifier })` to add `HTTPS_PROXY` and CA cert mounts to the container's args.
4. **Hard fail:** if `applyContainerConfig` returns false (gateway not running, identity broken, etc.), the call throws `'OneCLI gateway not applied — refusing to spawn container without credentials'`. The container is NOT spawned. The caller (router or host-sweep) catches this, leaves the inbound message pending, and retries on the next tick.
5. Inside the container, all outbound HTTPS traffic goes through the OneCLI proxy; the proxy matches by host/path, injects the real credential, forwards.

**Per-agent policies:** each agent group gets its own OneCLI identity → different credential policies per agent.

**Gotcha v2 surfaces explicitly in their own CLAUDE.md:** auto-created agents default to `selective` secret mode (no secrets attached). Fix is `onecli agents set-secret-mode --id <agent-id> --mode all` or assigning specific secret IDs. We should know about this for any Whizzard ↔ OneCLI integration.

**Implication for D-98 / D-134:** NanoClaw's v2 commitment to OneCLI-as-sole-credential-path is the unambiguous production proof that the pattern works at the level Whizzard wants. The pattern isn't experimental; it's the only credential path the project supports.

---

## Mount policy in v2

Per-agent-group container config lives in a `container_configs` DB table (since v2.0.48) rather than as a per-folder `container.json`. The table holds `additionalMounts`, apt/npm package lists, MCP server registrations, and the per-group image tag.

**At spawn time**, NanoClaw materializes the row to `groups/<folder>/container.json` (read-only mount into the container at `/workspace/agent/container.json`). The runner reads this JSON for its actual mount list.

So the model is:

- Source of truth: DB row
- Materialized form: `container.json` mounted RO into the container
- Agent can read the JSON (so it knows what mounts exist) but can't modify it (RO)
- Agent can't see the DB row directly

Mount allowlist semantics are preserved from v1 — same default blocked patterns, same symlink resolution, same container-path validation. The change is the source of truth and the management surface (`ncl groups config get/update` + self-mod MCP tools with approval flow).

For a Whizzard adapter, the relevant surface is the on-disk `container.json` and the `groups/<folder>/` directory — not the DB. We don't need to depend on the DB schema.

---

## The `ncl` admin CLI — new in v2.0.45

Worth noting because it's a clean pattern.

`ncl` is a CLI for managing entities in the central DB — agent groups, messaging groups, wirings, users, roles, container configs.

- **From the host**: Unix socket transport (`src/cli/socket-server.ts`). Direct DB access.
- **From inside a container**: session-DB transport (`container/agent-runner/src/cli/ncl.ts`). Writes are gated by approval flow — the agent emits a `cli_request` that the host evaluates and either auto-approves (read ops, scope-limited writes) or routes to an admin via OneCLI's manual-approval webhook.

This is genuinely well-designed: same surface, two transports, with the container-side transport going through the same approval gate the rest of the agent's privileged operations use. The `cli_scope` per-agent flag controls whether the agent learns about `ncl` at all.

Whizzard's analog at the moment is much smaller — we have a `whiz` CLI on the host, and no agent-side surface. If we ever want agents to be able to ask Whizzard for things (which D-26 deliberately holds off on), this is a clean pattern to study.

---

## Things to keep doing (Whizzard's side)

- **All the container hardening** (cap-drop, read-only rootfs, no-new-privileges, tmpfs, network policy). NanoClaw v2 didn't close any of these gaps — the differential is intact and is the right thing to keep emphasizing. D-93 stands.
- **Mount registry + safety policy.** NanoClaw's container_configs-in-DB approach is more centralized than ours but our layered approach (hard-block + override + audit log) covers the same ground from a different direction.
- **Image management + digest pinning** (Stage 9). NanoClaw still uses tags. We should not.
- **Session duration enforcement.** NanoClaw doesn't have this. Our session_log + planned enforcement remains a real differentiator.
- **JSONL audit log with overrides.** NanoClaw has operational logs, not audit-grade. Ours is.

## Things to learn from NanoClaw (v2)

- **OneCLI as sole credential path is now proven.** This validates D-98's promotion from post-MVP backlog to v1-must-have, and D-134's MVP-inclusion choice. When the Stage 12 OneCLI integration lands, the v2 behavior (hard-fail container spawn on gateway misconfiguration) is the right reference for our own failure-mode design — we should fail loud rather than silently fall back to plaintext env vars.
- **Selective vs all secret-mode gotcha.** Auto-created OneCLI agents start in `selective` mode (no secrets attached). Any Whizzard ↔ OneCLI integration needs to either set `mode=all` at agent creation, document the gotcha clearly, or use explicit per-secret assignment. We should pick one and ship it; surprises from the gotcha would burn first-touch users.
- **Per-agent vault identity is the right granularity.** NanoClaw maps `agent_group_id` → OneCLI identity. For Whizzard, the analog would be a per-harness-config identity (each `harnesses.json` entry has its own vault scope), which gives us per-deployment credential boundaries without needing a separate "agent" concept.
- **Approval-gated admin CLI from inside the container.** Not in scope for Whizzard MVP (D-26 holds), but a clean pattern if we ever expose agent-side mutation. Worth a callback in future design conversations rather than a doc change now.
- **The composed CLAUDE.md pattern.** NanoClaw composes the agent's `CLAUDE.md` at spawn time from `.claude-shared.md` (symlink to global) + `.claude-fragments/*.md` (modular) + `CLAUDE.local.md` (per-group), mounted RO so the agent can't tamper with the composition. We don't need to adopt this, but the principle — instructions assembled by the host from policy-controlled fragments, agent only sees the result — is the same kind of "the agent can't influence its own policies" thinking we already do for the mount registry.

## Things NanoClaw has that Whizzard should not try to build

Same conclusions as the v1 artifact, with v2 sharpening the case:

- **Multi-channel messaging integration** (Discord, Telegram, Slack, etc.). v2 made this more explicit by extracting channels to a sibling branch — this is NanoClaw's product surface, not infrastructure other people would want from a containment layer. Whizzard contains harnesses; the harnesses bring their own multi-channel infrastructure.
- **Per-session DB architecture with two-DB split.** Clever solution to NanoClaw's specific IPC needs; not what Whizzard needs to build for a generic containment layer.
- **Fork-and-customize distribution model.** NanoClaw's intent is "you fork the repo and tell Claude Code what to change." That fits their personal-platform shape. Whizzard is an installable Python package (D-155) — a different distribution model is the right choice for our product.
- **Skills-on-branches distribution** for channels and providers. Sharper version of fork-and-customize. Same rationale: not how Whizzard's adapters should be distributed (D-94).
- **`ncl`-style admin CLI from inside the container.** Out of scope per D-26 (Whizzard is not a cooperation layer for the agent).

---

## How NanoClaw v2 fits as a Whizzard harness

A Whizzard ↔ NanoClaw adapter would shape up like this:

- NanoClaw's host process (Node + pnpm) runs inside the Whizzard cell. Whizzard provides cap-drop, read-only rootfs, tmpfs, no-new-privileges, profile-driven network policy on the outer container.
- NanoClaw, from inside that cell, continues to spawn its own per-session containers — this is Docker-in-Docker territory. The maintainer's view (D-97 / D-155) is that this is post-MVP integration work, slated for v1.0.
- The contained NanoClaw still uses OneCLI for credential injection. Whizzard's OneCLI integration (D-134) is at the host process layer; NanoClaw's is at its inner-container layer. They don't conflict.
- The Whizzard adapter would need to: launch the Node host process with the right env, mount the right directories (data/, groups/, .env or OneCLI proxy config), and either run Docker-in-Docker for NanoClaw's session containers or share the host Docker socket (the latter is a known footgun — DIND is cleaner).

Differences from the Hermes adapter:

- NanoClaw is a long-running host process, not a single-turn invocation. The cell wraps a daemon, not a one-shot command. This changes session_log semantics (one outer Whizzard session contains many inner NanoClaw turns).
- NanoClaw expects to manage its own inner containers; Whizzard's cell needs to permit Docker socket access or DIND.
- NanoClaw's data/ directory is stateful across sessions; the Whizzard mount needs to be persistent and the safety story is "you're trusting the contained NanoClaw with this directory."

These are non-trivial design questions. D-155's v1.0 timing for the NanoClaw adapter still looks right.

---

## Confirming our positioning (D-172)

The v2 rewrite, if anything, sharpens our complementarity argument:

- **NanoClaw v2 is unambiguously a personal AI assistant platform.** "Skills over features," fork-and-customize, opinionated channel/provider ecosystem, AI-native install flow that hands off to Claude Code when things break. This is a product, not infrastructure.
- **Whizzard is unambiguously a containment layer.** Pip-installable, harness-agnostic, hardening-first, designed to wrap whatever harness you point it at.
- **Microsoft Rampart/Clarity** (D-172) sit at test and design phases for enterprise CI buyers. Different phase, different buyer.

Whizzard's positioning vs. NanoClaw remains: complementary, not competitive. A user running NanoClaw who also runs Whizzard gets the best of both — NanoClaw's harness-native scope reduction + OneCLI + ephemerality, plus Whizzard's container-internal hardening + audit-grade logs + profile-driven network policy + image-digest pinning.

The NanoClaw-team pitch is exactly this: "your scope reduction is excellent, but the kernel surface inside the container is still wide; Whizzard tightens that without changing anything about how NanoClaw works."

---

## Open questions

1. **Is NanoClaw v1.x still in scope for any Whizzard adapter work?** With v2 the dominant install path (and v1.x being a sunsetting migration target), the Whizzard adapter — when it lands per D-155 — should target v2 only. Worth confirming explicitly so we don't carry compatibility surface for v1's `~/nanoclaw` shape.
2. **OneCLI shared-instance vs per-product instance.** If a user runs both NanoClaw and Whizzard-with-OneCLI, do they share one OneCLI gateway (pinned to 1.23.0 by NanoClaw) or run two? The gateway listens on `127.0.0.1:10254` — only one can bind at a time. Likely a shared-instance question for D-134's implementation phase.
3. **Should Whizzard adopt NanoClaw's "shared agent-runner mounted RO" pattern for any harness we build natively?** D-155's "native harness at v2.0" line would benefit from this — separating "shared infra (RO)" from "per-instance state (RW)" is a clean architectural pattern.
4. **NanoClaw's `cli_scope` policy** (per-agent control over whether the agent learns the admin CLI exists at all) is interesting prior art for D-26 (Whizzard is not a cooperation layer). They distinguish "agent doesn't know about it" from "agent knows but every write needs approval" — same surface, three modes. Worth flagging for future agent-API discussions.

---

## Bottom line

NanoClaw v2 is a substantial rewrite of nearly everything *except* the container hardening posture, which remains v1-level. The Whizzard hardening differential (D-93) survives intact and is the right thing to keep pitching.

OneCLI Agent Vault is now the only credential path in v2 — there's no more `.env`-passthrough fallback. This validates D-98's promotion to v1-must-have and removes any ambiguity about the pattern's production-readiness; it should be reflected in how we describe D-134's implementation reference.

The product positioning argument (D-172) is sharper than before: v2 has further specialized as a personal-platform shape, making the case for Whizzard-as-containment-layer-not-platform unambiguous.

The Stage 8 / Stage 12 / Stage 14 design lines do not change based on v2. The NanoClaw adapter (D-155, v1.0) will need rethinking around NanoClaw's host-daemon shape and Docker-in-Docker requirements — that's a v1.0 design conversation, not an MVP one.
