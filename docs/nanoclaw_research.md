# NanoClaw Research Notes

Deep-dive review of [qwibitai/nanoclaw](https://github.com/qwibitai/nanoclaw) to assess the same security/integration concerns we just walked through for Hermes. Specifically: container hardening, UID handling, credential model, mount policy, and how their design compares to what Whizzard provides.

Written: 2026-05-08.

---

## TL;DR

NanoClaw is **conceptually the closest existing thing to Whizzard**. They built containment for Claude-based agents and arrived at many of the same conclusions: non-root container user, ephemeral containers, mount allowlist outside the agent's reach, default blocked patterns for credential paths, project root mounted read-only.

Their **OneCLI Agent Vault is the single strongest design choice** in the project — it completely solves the API-credential problem, which is one of the hardest parts of agent containment. We already adopted this pattern as a backlog item; their implementation confirms the direction.

That said, **NanoClaw's container hardening is meaningfully weaker than Whizzard's**. They don't drop capabilities, don't use `--read-only`, don't use `no-new-privileges`, don't use tmpfs, and have no network policy (network is "unrestricted" per their security doc). These are real gaps that Whizzard's Stage 1-7 baseline already covers.

The product positioning is also different: NanoClaw is a **complete agent platform** (channels, sessions, scheduled tasks, multi-channel routing) that happens to use containers. Whizzard is **a containment layer** that runs whatever harness you point it at. Different products with overlapping but distinct value props.

---

## What NanoClaw is

From their README:

> An AI assistant that runs agents securely in their own containers. Lightweight, built to be easily understood and completely customized for your needs.

It's a fork-and-customize platform: clone the repo, run a setup script, get a containerized Claude-based agent reachable via Discord/Telegram/Slack/etc. Each user is expected to fork and modify their own copy.

**Stack:**
- Host process: Node.js / TypeScript (router, delivery, container-runner)
- Container: Bun + Claude Agent SDK (officially the Anthropic SDK, not Claude Code CLI)
- DBs: SQLite (per-session inbound.db + outbound.db)
- Runtime: Docker on macOS/Linux/Windows (WSL2)
- Optional: Apple Container, Docker Sandboxes (micro-VM), Ollama for local models
- Credentials: OneCLI Agent Vault

**Architecture:**

```
messaging apps → host process (router) → inbound.db → container (Bun, Claude Agent SDK) → outbound.db → host process (delivery) → messaging apps
```

The host process is always running. Per agent group, a container is spawned on-demand, runs one turn, exits. SQLite databases (one writer per file) handle IPC between host and container.

**Multi-channel isolation model:** three levels documented in `docs/isolation-model.md` — shared session, same agent / separate sessions, separate agents. Each level has different filesystem and conversation isolation.

---

## NanoClaw's container security — what they DO

From `docs/SECURITY.md` and `src/container-runner.ts`:

| Control | NanoClaw |
|---|---|
| Non-root user | UID 1000 (`node` user) by default |
| Ephemeral containers | `--rm` flag, fresh per invocation |
| PID 1 / signals | tini |
| Project root mount | **read-only** |
| Writable paths | mounted separately from project root |
| Mount allowlist | external — `~/.config/nanoclaw/mount-allowlist.json`, never mounted into containers, can't be modified by agents |
| Default blocked path patterns | `.ssh, .gnupg, .aws, .azure, .gcloud, .kube, .docker, credentials, .env, .netrc, .npmrc, id_rsa, id_ed25519, private_key, .secret` |
| Symlink resolution | resolved before validation (prevents traversal attacks) |
| Container path validation | rejects `..` and absolute paths |
| `nonMainReadOnly` flag | forces read-only for untrusted "non-main" groups |
| Per-session SQLite isolation | separate inbound/outbound DBs per session |
| Container labels | `nanoclaw-install=<slug>` for orphan cleanup scoped by install |
| **Credential isolation** | **OneCLI Agent Vault** — credentials NEVER enter the container |

The credential isolation is the standout. Worth its own section below.

### UID handling — interesting hybrid

From `src/container-runner.ts:467-472`:

```typescript
const hostUid = process.getuid?.();
const hostGid = process.getgid?.();
if (hostUid != null && hostUid !== 0 && hostUid !== 1000) {
    args.push('--user', `${hostUid}:${hostGid}`);
    args.push('-e', 'HOME=/home/node');
}
```

The logic:
- **Default**: container runs as UID 1000 (`node` user from the Dockerfile) — kernel-level UID isolation when host user happens to be UID 1000 (common on Linux)
- **If host UID is 0 (root)**: don't override — would be a privilege issue
- **If host UID is anything else** (e.g., macOS UID 501): override to `--user <host>:<host-gid>` — opt into UID parity

This is exactly the hybrid I proposed for Whizzard's Hermes adapter (option B). They do it universally, conditionally on host UID. It's a reasonable trade-off: maximum kernel boundary when possible, fall back to parity when needed for the bind-mount-write story.

### Read-only project root

This is a defensive idea worth borrowing eventually. They mount the host project root read-only and selectively mount writable paths (group folder, `.claude/`, `store/`, IPC dirs) on top. Rationale from `SECURITY.md`:

> This prevents the agent from modifying host application code (`src/`, `dist/`, `package.json`, etc.) which would bypass the sandbox entirely on next restart.

Whizzard doesn't have an equivalent today. We mount specific named paths from the registry; the host project (Whizzard itself) isn't mounted at all. So this attack surface is differently shaped — but worth keeping in mind if we ever support "mount the whole project workspace."

---

## NanoClaw's container security — what they DON'T do

This is where the gap with Whizzard shows up. Looking at `buildContainerArgs()` in `container-runner.ts:436-492`:

```typescript
const args: string[] = ['run', '--rm', '--name', containerName, '--label', CONTAINER_INSTALL_LABEL];
args.push('-e', `TZ=${TIMEZONE}`);
// provider env vars
// onecli gateway args (HTTPS_PROXY + certs)
// host gateway args
if (hostUid != null && hostUid !== 0 && hostUid !== 1000) {
    args.push('--user', `${hostUid}:${hostGid}`);
}
// mount args
args.push('--entrypoint', 'bash');
// image
args.push('-c', 'exec bun run /app/src/index.ts');
```

**What's missing compared to Whizzard:**

| Hardening | Whizzard | NanoClaw |
|---|---|---|
| `--cap-drop=ALL` | ✓ | ✗ (Docker defaults: CAP_NET_RAW, CAP_SETUID, CAP_SETGID, CAP_CHOWN, etc.) |
| `--security-opt no-new-privileges` | ✓ | ✗ |
| `--read-only` (root filesystem) | ✓ | ✗ (writable rootfs) |
| `--tmpfs /tmp:rw,...` | ✓ | ✗ |
| `--tmpfs /home/...` (writable home in tmpfs) | ✓ | ✗ |
| `--network none` (offline profiles) | ✓ profile-driven | ✗ network is "unrestricted" per `SECURITY.md` |
| Container image pinning by digest | Stage 9 (planned) | ✗ uses tag (`CLAUDE_CODE_VERSION=2.1.116`) |
| Session duration enforcement | session_log + planned enforcement | ✗ (containers are ephemeral per-invocation, but no time bound) |
| Two-gate broad-mount override | ✓ profile + CLI flag | ✗ uses main/non-main group distinction |
| Hard-block list at safety layer | ✓ (cannot be overridden) | mount allowlist concept is similar but different mechanic |
| Audit-grade session log | ✓ JSONL with mounts/image/overrides | basic logs only |

**Practical impact of these gaps:**

- **No capability dropping** means a NanoClaw container retains CAP_NET_RAW (raw sockets), CAP_SETUID/SETGID (uid manipulation in many syscalls), etc. A successful exploit inside the container has more privileges to work with.
- **No read-only root** means the agent can modify any file inside the container (the image's /etc, /usr, etc., as overlay layers). Persistent malware inside a single session is contained because the container is ephemeral, but mid-session lateral movement within the container is easier.
- **No `no-new-privileges`** means setuid binaries still grant elevation — niche, but a real attack class.
- **Network "unrestricted"** is the biggest semantic gap. Even with OneCLI proxying credentials, the container can establish arbitrary outbound connections to anywhere. This is a deliberate design choice (they need to reach LLM APIs) but it's much broader than Whizzard's profile-driven network policy.

### What this means

NanoClaw's approach is **"isolation through scope reduction"** — give the agent a small, well-defined surface (mounts + credentials via vault) and don't try to harden the inside of the container much. The threat model is something like: a misbehaving agent can do whatever it wants inside its container, but it can't see anything it shouldn't, can't make API calls without policy enforcement, and the container exits clean.

Whizzard's approach is **"isolation through hardening"** — same scope reduction (mounts + future vault) PLUS aggressive container-level hardening so even if something escapes the agent's intended sandbox, the container itself is constrained.

Both are defensible. NanoClaw's is simpler; Whizzard's is more defensive.

---

## OneCLI Agent Vault — the standout

The thing NanoClaw does that we should celebrate (and have already adopted as a backlog item): credentials never enter the container.

**Mechanism (from `container-runner.ts:454-460` + `SECURITY.md`):**

1. User registers credentials with OneCLI: `onecli secrets create`. Stored on host, managed by OneCLI.
2. NanoClaw spawns a per-agent OneCLI identity: `onecli.ensureAgent({ name, identifier })`.
3. NanoClaw calls `onecli.applyContainerConfig(args, { agent: identifier })` — this adds `HTTPS_PROXY` and CA certs to the container's args.
4. Inside the container, all outbound HTTPS goes through the OneCLI gateway as a proxy.
5. The gateway intercepts requests, matches by host/path, injects the real credential, forwards.
6. Hard fail: if `applyContainerConfig` returns false, NanoClaw refuses to spawn the container. No credentials = no agent.

**Per-agent policies:** each NanoClaw agent group gets its own OneCLI identity → different credential policies per agent → "your sales agent" vs "your support agent" can have different access. OneCLI supports rate limits and (per their roadmap) time-bound access and approval flows.

**Result:** the agent has zero credential material in environment, files, or `/proc`. It can use credentials by making API calls; it can't exfiltrate them because it never sees them.

This is the OneCLI Agent Vault pattern we wrote into our post-MVP backlog as "Vault-Mediated Credentials." NanoClaw is the proof-point that the pattern works in practice.

---

## Comparison table: Whizzard vs NanoClaw

| Concern | Whizzard | NanoClaw | Winner |
|---|---|---|---|
| Container user | Fixed UID 1000 | UID 1000 unless host UID differs | Tie (both reasonable) |
| Capability dropping | ALL dropped | Docker defaults | **Whizzard** |
| Read-only root | Yes | No | **Whizzard** |
| No-new-privileges | Yes | No | **Whizzard** |
| Mount allowlist | Stage 6 hard-block + override | External JSON allowlist | NanoClaw (allowlist outside project root is more defensive) |
| Default blocked credential patterns | Hard-block list (architecture.md) | Default blocked patterns + allowlist | Tie (similar coverage, different mechanics) |
| Symlink protection | Resolved during safety check | Resolved before validation | Tie |
| Network policy | Profile-driven (off/on/scoped) | "Unrestricted" | **Whizzard** |
| Image pinning | Stage 9 (planned: digest) | Tag-only | **Whizzard** (post-Stage-9) |
| Session duration enforcement | session_log + planned enforcement | Per-invocation only | **Whizzard** |
| Audit-grade session log | JSONL with overrides | Basic logs | **Whizzard** |
| Two-gate override | Profile + CLI flag, logged | Main/non-main groups | Different mechanics; both work |
| Credential isolation | Env-var injection (MVP), vault (planned) | **OneCLI Agent Vault (production)** | **NanoClaw** by a mile |
| Multi-channel messaging | Out of scope | Native (Discord, Telegram, Slack, etc.) | NanoClaw (different scope) |
| Per-agent isolation | Future (post-MVP §1) | Native (agent groups) | NanoClaw (different scope) |
| Per-session ephemeral container | Yes (each `whizzard run`) | Yes (per invocation) | Tie |
| Self-improvement / state | Mounted from host (skills, memories) | Per-group folder + sessions | Different model |
| Codebase size | Small (Stage 7 ~1500 LOC) | Small (one Node process, "a few source files") | Tie (both keep it small) |

---

## What this means for Whizzard

### Things to keep doing

- All the hardening (cap-drop, read-only, no-new-privileges, network policy). NanoClaw doesn't have these and the gap is real. We're more defensive at the container level, and that's a genuine differentiator.
- The mount registry + safety policy. NanoClaw's external allowlist is a similar idea, but ours is more layered (hard block + override + audit log).
- Image management + digest pinning (Stage 9). NanoClaw uses tags; we should not.
- Session duration enforcement (planned). NanoClaw doesn't have this.
- JSONL audit log with overrides. NanoClaw's logs are operational, not audit-grade.

### Things to learn from NanoClaw

- **OneCLI Agent Vault is production-proven.** Our decision to adopt this pattern is validated. Implementation note: when we get to that stage, integrating with OneCLI directly (rather than rolling our own vault) is probably the right call. NanoClaw uses `@onecli-sh/sdk` — pre-built integration we could use.
- **Mount allowlist outside the project root** is a meaningfully defensive pattern. Our `~/.whizzard/config/mounts.json` is similar, but the broader principle — never let the agent get write access to the directory that defines its own permissions — is worth elevating in our docs as an architectural principle alongside the existing config write-protection invariant.
- **Read-only project root** is a defensive layer worth considering for power-user setups. If we eventually support "containerize my own dev project," mounting the project root RO with selective writable subdirs follows NanoClaw's pattern.

### Things NanoClaw has that we don't (and probably shouldn't try to build into Whizzard)

- Multi-channel messaging integration (Discord, Telegram, etc. routing). This is "agent platform" work. Whizzard's job is to *contain* whatever harness implements that — Hermes does it natively, NanoClaw does it natively. Whizzard doesn't need its own.
- Per-agent group / per-session DB architecture. NanoClaw's choice of two-SQLite-per-session is clever for their architecture but isn't what Whizzard needs to build.
- Fork-and-customize philosophy. NanoClaw's intended UX is "you fork the repo and modify it for your needs." That's a different distribution model than Whizzard's. Reasonable for them; not a fit for us.

### How NanoClaw fits as a harness in Whizzard

NanoClaw is a **runs-in-Docker-natively** harness. From a Whizzard perspective:

- NanoClaw can run as a Whizzard harness, where Whizzard provides the container hardening (cap-drop, read-only, network policy) on top of NanoClaw's existing isolation
- The contained NanoClaw still uses OneCLI for credential injection
- Whizzard adds the layers NanoClaw is missing

The Whizzard NanoClaw adapter would be conceptually similar to the Hermes adapter:
- Inject NanoClaw's host-side process configuration
- Mount the right directories
- Pass through OneCLI gateway env (HTTPS_PROXY, certs)
- Launch via NanoClaw's existing entrypoint

Differences from Hermes:
- NanoClaw expects to be the host-side process (router, delivery), not a single contained process
- May not be a clean fit for "single container" containment without significant adaptation
- Probably better as a v1+ adapter — not MVP scope

### Confirming our positioning

The investigation reinforces what's been true the whole time: **Whizzard is the policy/hardening layer that complements harness-native containment, not a replacement for it.**

- Hermes ships Docker support that's mostly deployment convenience (no real containment).
- NanoClaw ships Docker support with good scope-reduction (mount allowlist, OneCLI vault) but weak hardening (no cap-drop, no read-only, unrestricted network).
- Whizzard adds the hardening layer that both lack, plus its own scope-reduction primitives that complement (rather than duplicate) what's harness-native.

A user who wants the strongest overall posture runs: NanoClaw's harness model + OneCLI Agent Vault + Whizzard's container hardening. Each layer contributes something the other doesn't.

---

## Open questions

1. **Should Whizzard integrate with OneCLI directly for MVP credential injection?** NanoClaw uses `@onecli-sh/sdk`. We could too, even before our own "vault" backlog item lands, if OneCLI is already on the user's system. Worth discussing.
2. **Should we adopt "mount allowlist outside project root" as a Whizzard architectural principle?** Currently config lives in `~/.whizzard/config/`. NanoClaw's external `~/.config/nanoclaw/mount-allowlist.json` adds an extra layer. We're closer to NanoClaw than to Hermes here, but worth being explicit.
3. **Should there be a NanoClaw adapter on the Whizzard roadmap?** Probably v1 or later, once the Hermes adapter is solid. NanoClaw's host-side architecture makes it more involved than Hermes.
4. **Is there an opportunity for collaboration with NanoClaw upstream?** Their security model lacks the hardening Whizzard provides; they might benefit from Whizzard wrapping their container spawns. Worth a friendly conversation if we ever get to public release.

---

## Bottom line

NanoClaw is the closest peer to Whizzard. They got two big things right that we're already trying to get right: scoped mounts with an external allowlist, and credential isolation via OneCLI Agent Vault. They didn't do the container-level hardening that Whizzard does. We're complementary, not redundant.

The Stage 8 plan (Hermes adapter) doesn't change based on this investigation. The OneCLI vault validation strengthens our backlog priorities — vault-mediated credentials should be a v1 feature for sure, not a v2+ aspiration.
