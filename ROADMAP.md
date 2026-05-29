# Whizzard Roadmap

This document lays out what comes after the initial OSS release. Sequencing
is rough — order may shift in response to user feedback, contributor
interest, and the discoveries that come from real-world use.

Whizzard ships as `v0.1.0` because we expect to learn from users before
committing to a `v1.0` API. The roadmap below is the working plan for that
v1.0 milestone.

---

## v0.1.0 — Initial OSS release

The current shipping scope. The full MVP capabilities documented in the
README — capability containment, profile + mount registry, audit logging,
adapter contract, in-cell MCP server, session lifecycle (start / stop /
adjust / wake) — are all present.

Known un-addressed classes, disclosed in the README "Scope and limitations"
section, are tracked on this roadmap with mitigation paths.

---

## v1.0 — Primary goals

Each goal below is a substantial deliverable. Sketches here are intentionally
high-level; concrete designs land as decisions in
[`docs/decisions.md`](docs/decisions.md) when each goal enters active work.

### 1. Per-agent capability scoping

Today, capability profiles apply at the session level. v1.0 introduces
per-agent profiles within the same harness — different agents in the same
runtime can operate under different mount and network policies.

### 2. Discord / mobile control plane

Approve, deny, and observe sessions from a phone — useful when an agent
hits a request gate while you're away from the desk.

### 3. Multi-harness adapter rollout

Today's adapter contract supports Hermes and a generic shell. v1.0 expands
the catalog — OpenClaw, NanoClaw integration patterns, and a contributor
template for adding new harnesses.

### 4. MCP gateway direction

A second MCP server pattern — host-side, separate from the in-cell server
— for queries that need access to data the cell isn't trusted with.

### 5. Session duration as a first-class enforced primitive

Today's duration cap is a single bound at session start; v1.0 makes it a
manageable primitive (extend, suspend, resume) with audit-log visibility
into every change.

### 6. Image management at runtime

Pinning, mirroring, and lifecycle-management tooling for the container
images Whizzard launches. Surface for image trust decisions.

### 7. Quick-access presets

A curated catalog of bundled configurations — profile + mount + harness
defaults — for common scenarios ("review an untrusted task," "iterate on
my own project," "evaluate a new harness"). Each preset encodes a
deliberate security posture, not just a config bundle.

### 8. Repo onboarding — docs and setup scripts

Lower the barrier for new users adopting Whizzard in an existing project:
project-detection heuristics, opt-in setup scripts, profile-matching
suggestions.

### 9. Orchestrator integration API

A documented programmatic surface so external orchestrators (CI, agent
schedulers, task runners) can launch and govern Whizzard sessions without
shelling out to the CLI.

### 10. Writable mount quarantine and diff-merge

The biggest v1.0 addition. By default today, agent writes to a writable
mount are visible to the host immediately — and an agent can plant files
that execute later in the user's normal workflow (`.git/hooks/pre-commit`,
poisoned `package.json` postinstall scripts, source backdoors). v1.0
introduces an opt-in overlay-quarantine pattern: agent writes land in a
cell-private upper layer, host-side tools see the pre-session state, and
the user runs `whiz merge <session-id>` to review the diff before writes
apply to the host. Risk-class flagging (`.git/hooks/`, `.github/workflows/`,
lockfiles, build configs) bubbles the high-impact paths to the top of the
diff.

Open question for the v1.0 design conversation: should overlay-quarantine
be the default, or shipped as `--strict-overlay` opt-in? Default-direction
will be decided with user feedback in hand, not in isolation.

### 11. Network policy: per-destination allowlist

Today's network policy is a per-profile boolean: `on` (full outbound
access) or `off` (no network at all, including DNS). v1.0 adds a third
posture — an **allowlist** mode — where a profile declares the specific
destinations the cell is allowed to reach (model endpoint, package
index, configured webhooks). Everything else is dropped.

The likely mechanical shape extends the OneCLI proxy pattern Whizzard
already uses for credential mediation: the cell launches with
`--network none` at the Docker layer (no direct egress) and routes
outbound HTTPS through a host-side proxy that validates each
destination against the profile's declared list. Same isolation
primitive as `off`, with controlled egress added on top — no kernel
capability changes inside the cell, no iptables rules to maintain.

Sub-track: DNS gating. The current `off` posture blocks DNS as a
side-effect of `--network none`; the current `on` posture allows DNS
to anywhere. Allowlist mode needs an explicit answer for DNS (resolve
only listed hostnames? proxy DNS through the host?). See the README
"DNS-based exfiltration" residual-risk entry.

---

## How sequencing will evolve

Some of the v1.0 goals are loosely coupled; others share architecture.
The likely early-v1.0 cluster is presets (7), repo onboarding (8), and the
session-duration work (5) — these tighten the user-facing surface around
what already ships.

The middle cluster is the harness work — multi-harness rollout (3) and
per-agent scoping (1) — both of which extend the adapter contract.

The deep cluster is overlay-quarantine (10), orchestrator API (9), and
MCP gateway direction (4) — each introduces a new architectural surface.

Discord control plane (2) is mostly independent and could land in any
cluster depending on demand.

---

## Beyond v1.0

The post-v1.0 backlog (Phase 3, Phase 4 in
[`docs/vision_and_strategy.md`](docs/vision_and_strategy.md)) includes
broader scope: shadow environments for adversarial replay, deeper
threat-modeling automation, and a memory-governance product line that's
explicitly *not* part of Whizzard's runtime.

---

## Where contribution would land well

Reasonable starting points for contributors interested in the v1.0
direction:

- A new harness adapter following the contract in
  [`docs/architecture.md`](docs/architecture.md) and
  [`whizzard/adapters/`](whizzard/adapters/) (goal 3).
- Preset additions — concrete profile + mount + harness combinations for
  scenarios beyond what ships in v0.1.0 (goal 7).
- Documentation contributions to the onboarding flow (goal 8).

Open an issue first to align on direction before writing code.

---

## Roadmap stability

This roadmap is the *intent* as of `v0.1.0`. Items may move, expand,
contract, or be replaced as users tell us what matters and what they
actually use. v1.0 is the first formal stability commitment; everything
between `v0.1.0` and `v1.0` is iteration in public.
