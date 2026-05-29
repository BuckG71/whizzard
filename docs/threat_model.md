# Threat Model

Canonical threat-model document for Whizzard v0.1.0. Synthesizes the
existing architectural commitments (decisions index, architecture
document, README scope-and-limitations, SECURITY.md disclosure
policy) into one structured reference for reviewers, contributors,
and adopters.

Status: drafted as Stage 20 deliverable 1 (Security Review &
Hardening Audit). See `docs/known_issues.md` for unresolved items.

---

## 1. What Whizzard is protecting

Whizzard's job is to bound what a running AI agent can do to the
machine it executes on. Concretely, Whizzard defends the following
host-side assets against actions taken (or instructed) by the agent:

1. **The host filesystem.** Files outside the declared mount
   registry — SSH keys, browser cookies, password-manager databases,
   cloud-credentials directories, source trees the user did not
   register, OS configuration files — must not be reachable from
   the agent's perspective.
2. **Credentials.** Provider API keys, OneCLI-vault contents, host
   environment secrets, and Whizzard's own `auth.json` / future
   token stores must not be accessible to the agent at runtime nor
   leak via the audit log.
3. **Network destinations.** Outbound HTTP traffic must respect the
   profile's network policy (off / on / allowlisted). The agent
   cannot reach destinations the user did not approve.
4. **Future Whizzard sessions.** The agent must not be able to
   modify Whizzard's own configuration in a way that loosens
   policies for sessions that have not yet launched.
5. **The audit log.** Once written, the session log is the post-hoc
   detection surface; the agent must not be able to redact or
   rewrite past entries.
6. **The host's Docker control plane.** The agent must not be able
   to spawn unconstrained sibling containers, modify or restart the
   Whizzard-launched container, or reach the host Docker daemon.

What Whizzard **does not** defend appears in §6 (Residual risks)
and the README "Scope and limitations" section.

---

## 2. Trust boundaries

```
┌────────────────────────────────────────────────────────────┐
│  HOST (control plane)                                      │
│                                                            │
│  Whizzard CLI · policy engine · config registry · logs     │
│  Docker daemon (full privileges)                           │
│  User's credential stores (OneCLI vault, host env)         │
│  User's filesystem (except registered mounts)              │
│  - - - - - - - - - - - - - - - - - - - - - - - - - - - -  │
│  Trust boundary: cell launch (one-way capability flow)     │
│  - - - - - - - - - - - - - - - - - - - - - - - - - - - -  │
│                                                            │
│  CELL (execution plane — hardened container)               │
│                                                            │
│  Agent runtime (Hermes, future adapters)                   │
│  Tool execution                                            │
│  Filesystem access — ONLY via registered mounts            │
│  Network — per profile policy                              │
│  Capabilities — none (--cap-drop=ALL)                      │
│  Root filesystem — read-only                               │
│  tmpfs at /home/whizzard (writable scratch)                │
│  Non-root user (UID 1000)                                  │
│  no-new-privileges set                                     │
│  Whiz in-cell MCP server (cooperation layer)               │
└────────────────────────────────────────────────────────────┘
```

The cell-launch boundary is **one-way**: capabilities can only
narrow after launch, never widen. A mid-session escalation requires
stop+restart at the host, mediated by Whizzard, never by the agent
acting alone (D-27).

### Within the cell — control layering (D-architecture)

Whizzard's controls compose in three concentric layers; this
threat model focuses on the **enforcement** layer (the outermost,
Whizzard-owned ring):

| Layer | Owner | Mechanism | This document's scope |
|---|---|---|---|
| Enforcement (outer) | Whizzard | Docker flags + kernel | **In scope** |
| Behavioral (middle) | Harness | LLM-mediated approval | Out of scope (per D-10 / D-24) |
| Cooperation (inner) | Whizzard (via MCP) | Structured request channel to host | **In scope** |

Whizzard explicitly does NOT recreate the harness's behavioral
interception; recreating them duplicates the harness's work and
expands attack surface without adding security (D-24). The harness
is treated as a trust principal for behavioral decisions and a
**potential adversary** for structural decisions — see §3.

---

## 3. Threat actors

This threat model addresses these adversary models, ordered by
realism for the v0.1.0 audience:

### 3.1 Misbehaving agent (primary)

A running agent issues commands intended to read, write, or exfiltrate
data outside the operator's intent. The agent may be:

- Acting on a confused chain of reasoning (most common)
- Following malicious user input (prompt injection)
- Following malicious tool output (indirect prompt injection through
  fetched documents, web pages, etc.)
- Trained or fine-tuned with adversarial objectives (rare)

The agent has access to whatever capabilities its profile + mounts
grant. It can issue arbitrary shell commands within the cell. It
cannot bypass the enforcement layer by issuing commands; that would
require a kernel-level escape (§6).

**Risk posture:** this is the threat Whizzard is designed against.
Every architectural decision in §4 maps to a containment guarantee
against this actor.

### 3.2 Compromised or buggy harness

The agent runtime (Hermes today; NanoClaw / others later) has a
bug or vulnerability such that an attacker can cause it to issue
commands the legitimate user did not approve. The harness's own
behavioral controls (approval flows, command intent gating) are
bypassed; what reaches Whizzard's enforcement layer is whatever
the harness allows.

**Risk posture:** this collapses to "misbehaving agent" at
Whizzard's enforcement layer — the threat is structurally identical
because Whizzard never trusted the behavioral layer to be the only
defense. The hardening differential (D-93) is the load-bearing
mitigation here: a compromised harness inside the cell still cannot
break out of the kernel-surface constraints Whizzard imposes.

### 3.3 Indirect injection via mounted content

A malicious actor places content into a directory the user later
registers as a mount. The content executes when the agent reads
it (e.g., a poisoned `package.json` `postinstall`, a `.git/hooks`
file, a malicious `Makefile` target, a binary the agent runs).

**Risk posture:** Whizzard does not prevent the agent from running
files it has read access to. The mount registry bounds *which*
files can reach the cell; the harness's behavioral layer is
responsible for "should I actually run this." Once the agent runs
something, it executes inside the cell's enforcement constraints
(see deferred-execution residual risk in §6 — addressed at v1.0
by D-135 overlay-quarantine).

### 3.4 Compromised supply chain

A dependency of Whizzard (or of the agent harness, or of the base
Debian image) ships malicious code that activates in the cell.

**Risk posture:** partially mitigated:

- Base image is digest-pinned (Stage 18 / D-74)
- Python deps are minimal (3: typer, rich, mcp); will get
  `pip-audit` in CI as part of Stage 20 deliverable 6
- Hermes pinned to a specific upstream commit (Dockerfile.hermes)
- PyPI Trusted Publishing for Whizzard's own releases (no API
  tokens stored as secrets)

Residual risks tracked in §6.

### 3.5 Compromised host

If the user's host is already controlled by an attacker (rootkit,
compromised OS, malicious admin), Whizzard can no longer defend
anything — the attacker controls the Docker daemon, the config
files, the audit log, and the user's keystrokes. This is explicitly
out of scope (SECURITY.md §Scope).

### 3.6 Insider / operator error

The legitimate user misconfigures Whizzard: registers an
overly-broad mount, runs a permissive profile against untrusted
content, approves a mid-session capability request without
reading the diff. Whizzard surfaces what is configured but cannot
prevent intentional self-foot-shooting.

**Risk posture:** mitigated by safety policy (hard-blocked mount
patterns including `/`, `$HOME`, `.ssh`, etc. per D-43), structured
approval prompts (D-163 Stage 13 adjust), and audit-log visibility.
Some classes of operator error (deferred-execution via writable
mount writes) are acknowledged residual risks.

---

## 4. Mitigations (per asset)

This section maps each protected asset from §1 to the architectural
mechanisms that defend it. Each mechanism cites the decision (`D-NN`)
that establishes it.

### 4.1 Host filesystem outside the registered mounts

| Defense | Reference |
|---|---|
| Mount registry is the ceiling, not a default — paths not declared cannot be reached, period | D-11 |
| Mount validation rejects unsafe targets: `/`, `$HOME`, dotfile directories, credential paths, parent-of-registered traversal | D-42 / D-43 |
| Symlinks are resolved before validation; the cell sees the resolved path, not the original symlink target | D-43 |
| Cell rootfs is `--read-only`; writes go to declared rw mounts or to tmpfs at `/home/whizzard` | D-12 |
| `--cap-drop=ALL` + `--security-opt no-new-privileges` prevents using kernel capabilities or setuid binaries to bypass mount constraints | D-93 |
| Non-root cell user (UID 1000) means even an in-cell privilege escalation runs without host root | D-12 |
| Once a session starts, the mount list is locked for the session; no flag, agent request, or edit can change what's mounted (mid-session adjust requires stop+restart via D-27) | D-9 / D-11 / D-27 |

### 4.2 Credentials

| Defense | Reference |
|---|---|
| OneCLI vault integration: credentials never enter the cell as plaintext env vars; cell-side HTTP traffic is mediated by an OneCLI proxy that injects credentials at the wire | D-91 / D-98 / D-134 |
| Host env fallback path emits a warning visible in `active_capabilities()` so operators see when credentials originate from less-protected sources | D-89 / D-90 |
| Hermes `auth.json` and per-instance runtime state are excluded from profile clones (D-80); Stage 8 / catch-up review F-C-01 closed bypass paths | D-80 / D-86 |
| Whizzard's own config directory (`~/.whizzard/config/`) is structurally unreachable from the cell — no symlink, no parent-mount, no traversal trick reaches it | D-12 (config write-protection invariant) |
| Harness `secrets:` blocks must declare credential env var **names**, not values; plaintext values in `harnesses.json` are rejected at parse time | D-162 |
| Audit log writes redact known credential fields; no captured argv or env block emits secret values | Stage 5 / D-72 |

### 4.3 Network destinations

| Defense | Reference |
|---|---|
| Profiles include explicit `network_enabled` boolean; off-network profiles launch with `--network none` | D-39 |
| Default profile is "SAFE-NET" — network on with no mounts and no broad-mount override; explicit baseline rather than implicit default | D-38 |
| Allowlist-style network restriction (per-destination) is on the v1.0 roadmap; v0.1.0 ships boolean on/off | Per `ROADMAP.md` v1.0 primary goal |

### 4.4 Future Whizzard sessions

| Defense | Reference |
|---|---|
| Config write-protection invariant: agent-writable mounts cannot reach `~/.whizzard/config/` under any circumstances (validation layer, not policy layer) | D-12 |
| One-way capability flow: mid-session changes can only **narrow** permissions; widening requires stop+restart with operator approval | D-9 / D-27 |
| Mid-session adjust (`whiz adjust`) shows a structured diff before applying, with TTY approval for widening changes | D-163 / Stage 13 |

### 4.5 Audit log

| Defense | Reference |
|---|---|
| Audit log is append-only by Whizzard; the cell cannot reach the host-side `~/.whizzard/logs/sessions.jsonl` to rewrite past entries | Stage 5 / D-12 |
| In-cell agent events are merged into the host audit log **before** the `session_end` event is written, so temporal ordering is preserved even if the cell crashes mid-merge | Stage 9 / F-B-10 |
| Audit-log origin-forgery + cross-session request spoofing closed during the catch-up review (D-12 / D-9 alignment) | Catch-up review (2026-05-23) |

### 4.6 Host Docker control plane

| Defense | Reference |
|---|---|
| `/var/run/docker.sock` is never mounted into the cell — explicit rejection | D-9 |
| Whizzard rejects Docker-in-Docker for the same reason | D-164 |
| Cell runs as non-root with no Docker client and no permission to reach the host's Docker socket via any path | D-12 / D-93 |
| Future harnesses that themselves spawn containers (NanoClaw) use delegated nested-VM mechanisms (Docker Sandboxes / Sysbox) rather than docker-socket sharing — preserved at v1.0 | D-178 (planned for v1.0 per the NanoClaw build plan) |

---

## 5. Attack surfaces (and what defends them)

Surfaces an attacker could probe, with the controls that contend
with each:

### 5.1 Mount registration surface

**Surface:** `~/.whizzard/config/mounts.json` defines what paths
the agent can reach. A successful attack here is "register an
overly-broad mount."

**Path the attack would take:**
- An operator edits the file (no remote surface)
- The agent persuades the operator to add a mount via the `whiz
  adjust --add-mount` flow

**Defenses:** safety policy validates mount targets at load time;
hard-block list includes `/`, `$HOME`, dotfile dirs, credential
paths (D-43). The adjust flow shows the diff before applying
(D-163). Audit log records the override that landed.

**Residual:** the hard-block list is hard-coded, not configurable;
new credential file patterns (a future password manager) would
not be blocked until the list is updated. Tracked as Stage 20
work.

### 5.2 The in-cell MCP server

**Surface:** the agent talks to a Whiz MCP server inside the cell
that exposes read tools (`whiz_status`, `whiz_audit_self`) and
request tools (`whiz_request_mount`, `whiz_request_extend`).
Mutation requests are gated by host-side approval (D-26).

**Path the attack would take:**
- Agent attempts a request the cell-side MCP server should reject
- Agent fabricates an inbound message claiming to come from another
  cell or another session (cross-session spoofing)

**Defenses:** request channel uses per-session ephemeral
directories; host-side validation cross-references `session_id`
against the active-session table; broad-mount / profile-change
requests from the agent path are filtered before they reach the
adjust pipeline (`AGENT_DENIED_CHANGES` per Stage 13). Cross-
session request spoofing was closed during the catch-up review
(2026-05-23).

**Residual:** the in-cell `snapshot.json` is writable by the cell
under D-156; the host-side audit log remains the source of truth,
but the cell's "honest self-reflection" surface is compromisable.
Tracked in `known_issues.md` (Stage 20 disposition).

### 5.3 Container env / command construction

**Surface:** `whizzard.docker_cmd.build_run_argv` constructs the
`docker run ...` invocation by composing flags, env vars, mounts,
and the harness's `start_command` and `container_env`. Strings
from `profiles.json` / `harnesses.json` / CLI flags flow in.

**Path the attack would take:**
- Argv injection via crafted harness `start_command`
- Env-name injection via `container_env` (e.g. `LD_PRELOAD`, `PATH`)

**Defenses:** harness config is sourced from `harnesses.json`,
which is a Whizzard-owned trusted surface (D-153). Adapter code is
core-trusted (D-10). Argv is constructed by appending list elements,
not shell interpolation — no shell injection path exists.

**Residual:** no env-name denylist on adapter-supplied
`container_env` (catch-up review F-B-07). Defensive hardening, no
current attack path; Stage 20 audit will land it.

### 5.4 Profile / preset / harness config files

**Surface:** all four config files (`profiles.json`, `mounts.json`,
`harnesses.json`, `presets.json`) are read at session-start. Their
schema is strict; malformed content fails closed.

**Path the attack would take:** the agent persuades the operator
to add an overly-permissive profile or preset (e.g. a preset that
binds `/` ro).

**Defenses:** see §5.1 — same mount validation applies regardless
of which config file declares the mount. Profiles cannot grant
themselves capabilities the safety layer rejects (D-43).

**Residual:** described in §6.

### 5.5 The audit log read surface

**Surface:** `whiz status` and `whiz_audit_self` read
`sessions.jsonl`. A large or malformed log line could degrade
performance or cause a parse error mid-session.

**Path the attack would take:** the agent (via Stage 9
`whiz_emit_event`) writes a maliciously-large or malformed event
intended to disrupt downstream readers.

**Defenses:** the per-session event-file emission lives in a
cell-writable area and is merged at session_end. Malformed entries
are skipped, not crashed on (Stage 5 / Stage 9 hardening).

**Residual:** `whiz_audit_self` slurps the entire log on every
call (catch-up review F-E-05); a long-lived install would see
linear RAM growth. Tracked as deferred — same fix as the parallel
F-H-06 (`whiz status` reads entire log) — audit-log rotation +
streaming reads. Pre-OSS-launch impact is bounded because installs
won't be old enough to feel it.

### 5.6 Supply chain — Python deps

**Surface:** Whizzard depends on `typer`, `rich`, `mcp`. A
compromised upstream could land malicious code.

**Defenses:** declared in §3.4. `pip-audit` to be wired into CI as
Stage 20 deliverable 6.

**Residual:** until `pip-audit` ships in CI, supply-chain regressions
are detected only by reading dependency release notes.

### 5.7 Supply chain — Docker base + Hermes

**Surface:** `whizzard/_dockerfiles/Dockerfile` pulls `debian:12-slim
@sha256:0104...` (digest-pinned). `Dockerfile.hermes` installs
Hermes from a pinned GitHub commit.

**Defenses:** digest pinning (D-74); `whiz image check` warns on
stale images (D-178 / Stage 18). Hermes upstream commit is
manually bumped against Bryan's host HEAD (this conversation,
2026-05-28).

**Residual:** there is no automated upstream-change-detection for
Hermes; a bump that introduces a regression requires manual
review.

---

## 6. Residual risks (explicitly out of scope for v0.1.0)

This section is the technical-deep version of the README's "What
Whizzard does not address in v0.1.0" section. Each item names the
risk, the operational impact, and the mitigation roadmap.

### 6.1 Deferred-execution attacks via writable mounts

**Risk:** an agent with write access to a project mount can plant
files that execute later on the host: `.git/hooks/pre-commit`,
poisoned `package.json` `postinstall` scripts, source backdoors,
pinned-bad dependencies in lockfiles.

**Mitigation roadmap:** v1.0 ships `--strict-overlay` mode per
D-135. Writes go to a cell-private upper layer; a `whiz merge`
review gate lets the operator inspect and accept changes
explicitly before they land on the host filesystem.

### 6.2 DNS-based exfiltration

**Risk:** when network is allowed, an agent can encode data in
DNS lookups even to hostnames not in the (future) allowlist.

**Mitigation roadmap:** per-profile constrained-DNS option under
consideration for v1.0; not blocking. For high-stakes work today,
the `safe` or `quarantine` profile's `network_enabled=False`
posture blocks DNS too.

### 6.3 Container escape via kernel CVE

**Risk:** a kernel-level container escape (e.g. a runc CVE)
bypasses Whizzard's containment entirely.

**Mitigation roadmap:** out of scope. The project tracks runtime
advisories but does not invent novel sandboxing primitives.
NanoClaw's v1.0 integration introduces nested microVMs (Docker
Sandboxes / Sysbox) for the inner-container layer; that's an
additional layer of hardware-virtualized isolation that mitigates
some classes of escape, but the outer Whizzard cell still relies
on Docker's runtime.

### 6.4 Behavioral analysis of the agent

**Risk:** sophisticated refusal patterns, hidden communication
channels in tool outputs, steganography in agent writes.

**Mitigation roadmap:** out of scope. The behavioral-control layer
is the harness's job (D-24); Whizzard's value is structural
containment, not intent analysis.

### 6.5 Supply-chain attacks on Whizzard itself

**Risk:** a malicious PR merges; a compromised maintainer account
publishes a malicious release.

**Mitigation roadmap:**
- PyPI Trusted Publishing avoids stored API tokens (Stage 19 / M4)
- Branch protection on `main` is a launch-readiness BLOCKER; will
  enforce signed-commits + PR-review-required before public OSS
  launch (per `launch_readiness.md`)
- `pip-audit` in CI lands as Stage 20 deliverable 6
- Sigstore signature attachment is a fast-follow per
  `launch_readiness.md`

### 6.6 In-cell `snapshot.json` writable by the agent

**Risk:** the per-session capability snapshot the agent reads via
`whiz_status` lives in a cell-rw mount (`/run/whiz`). A compromised
harness could rewrite it to lie about the cell's capabilities.

**Mitigation roadmap:** split `/run/whiz` into a `:ro` snapshot
mount and a `:rw` events/requests mount, OR expose the snapshot
through the in-cell MCP server instead of as a file. Either is a
D-156 amendment. Stage 20 audit will land one of them.

### 6.7 Unlimited-profile enforcer can hang on docker client wedge

**Risk:** when both duration and idle limits are `None`, the
enforcer's `proc.wait()` has no timeout. If the docker client
process wedges while the container stays alive, the enforcer hangs
the host indefinitely.

**Mitigation roadmap:** add a periodic liveness probe on the
unlimited path. Catch-up review F-F-05; Stage 20 hardening pass.

### 6.8 Default-direction question for overlay-quarantine (D-135)

**Risk:** when D-135's `--strict-overlay` ships at v1.0, the
project must pick whether the default is opt-in or opt-out. An
opt-out default would protect more users by default but breaks
the v0.1.0 install path's "Whizzard writes to your mounts directly"
expectations.

**Mitigation roadmap:** decision deferred to v1.0 implementation
time; currently held open (per `launch_readiness.md`).

---

## 7. References

### Source documents

- `docs/architecture.md` — system structure, containment posture,
  safety policy
- `docs/decisions.md` — every architectural commitment is a `D-NN`
  entry; this document cites the load-bearing ones inline
- `docs/known_issues.md` — open tech-debt + deferred-feature index
- `SECURITY.md` — vulnerability reporting, response timelines,
  disclosure policy
- `README.md` §"Scope and limitations" — user-facing version of §6

### Key decisions cited here

| ID | Subject |
|---|---|
| D-9 | One-way capability flow (no docker socket; mid-session via stop+restart) |
| D-10 | Harness-neutral core |
| D-11 | Mount registry as permission model |
| D-12 | Config write-protection invariant; cell-as-non-root; rootfs read-only |
| D-24 | Whizzard does not recreate harness behavioral controls |
| D-27 | Mid-session = stop+restart |
| D-38 | Default profile is SAFE-NET baseline |
| D-39 | Profile `network_enabled` field |
| D-42 / D-43 | Mount safety validation; hard-block / override / allowed tiers |
| D-72 | Session-log emission and redaction |
| D-74 | Image management; digest-pinned base image |
| D-80 / D-86 | Hermes `auth.json` exclusion + generalization |
| D-89 / D-90 | `active_capabilities()` UX |
| D-91 / D-98 / D-134 | OneCLI Agent Vault integration |
| D-93 | Hardening differential (the load-bearing architectural commitment) |
| D-135 | Overlay-quarantine for writable mounts (v1.0) |
| D-153 | Harness-specific identifiers in adapter modules |
| D-156 | In-cell MCP server with launch-time snapshot |
| D-162 | Declarative `secrets:` field; no plaintext credentials |
| D-163 | Mid-session `whiz adjust` capability adjustment |
| D-164 | Image provenance; explicit rejection of DIND / docker.sock |
| D-178 | Image staleness check pulled into MVP |

---

*Last reviewed: 2026-05-29 (Stage 20 deliverable 1).*
