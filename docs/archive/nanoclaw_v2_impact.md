# NanoClaw v2 — Impact on Whizzard

Memo capturing the load-bearing implications of NanoClaw's v2.0 rewrite (and ~v2.0.63 micro-versions) for Whizzard decisions, adapter plans, and positioning. Companion to the refreshed research artifact (`nanoclaw_research.md`).

Written: 2026-05-28.

---

## 1. Hardening differential (D-93) is intact

The most consequential finding: **v2 did NOT close any of the container-hardening gaps Whizzard exploits as its differentiator.** Verified by fetching `src/container-runner.ts` from `main` and inspecting `buildContainerArgs()`. Still no `--cap-drop`, no `--security-opt no-new-privileges`, no `--read-only`, no `--tmpfs`, no network restriction. The v2 rewrite was about architecture, entity model, and developer experience — not the container's internal security posture.

**D-93 needs no update.** The "isolation through scope reduction" vs "isolation through scope reduction + container-internal hardening" framing is still load-bearing and accurate.

The forward-deployed-engineer pitch ("Whizzard tightens the kernel surface NanoClaw leaves wide") is unchanged.

## 2. OneCLI is now mandatory — strengthens D-98 / D-134

In v1, OneCLI was the recommended credential path; in v2 it's the **only** path. The container spawn hard-fails (`throw new Error('OneCLI gateway not applied — refusing to spawn container without credentials')`) if `applyContainerConfig` returns false. There's no fallback to plaintext env.

**Implications:**
- D-98 (OneCLI vault as v1-must-have) is more strongly validated than the v1-era research suggested. We should reflect this when we get to Stage 12.
- D-134's scope clarification — "for gateway-style harnesses, OneCLI is delivery mechanism only" — is still right, but the production reference (NanoClaw) is now an even tighter implementation than what the original research described. Our Stage 12 failure-mode design should follow the v2 pattern: fail loud on OneCLI misconfiguration, do not fall back to plaintext env.
- New gotcha to handle: auto-created OneCLI agents default to `selective` mode (no secrets attached). Whizzard's OneCLI integration needs an explicit story here — either set `mode=all` at agent creation, document, or use per-secret assignment. Picking one before implementation prevents a predictable first-touch failure.

**Suggested decision-log attention:** D-134's Notes section could call out the v2 hard-fail behavior as the canonical reference implementation. No new decision needed — just a clarifying note.

## 3. Adapter integration shape — D-155's v1.0 timing still right, but design is non-trivial

The prior assumption ("Whizzard cell wraps NanoClaw's host process; NanoClaw's per-session containers run inside") still appears to be the correct shape, but v2 makes the design challenges more visible:

- NanoClaw v2 is a **long-running Node daemon** (router + delivery + host-sweep), not a single-turn invocation. The Whizzard cell wraps a daemon, which changes `session_log` semantics: one outer Whizzard session contains many inner NanoClaw turns. session-duration-enforcement design needs to think about this.
- NanoClaw v2 spawns its own per-session Bun containers via `src/container-runner.ts`. Inside a Whizzard cell, this is Docker-in-Docker (DIND) territory — the Whizzard cell either runs its own Docker daemon (DIND, cleaner isolation but more setup) or shares the host's Docker socket (lighter, but a known footgun).
- v2's `container_configs` lives in the central DB and is materialized to `groups/<folder>/container.json` at spawn time. The Whizzard adapter should consume the on-disk JSON, not the DB schema, to stay decoupled from NanoClaw's internal data model.
- Persistent state lives in `data/` (central DB + per-session DBs) and `groups/` (per-agent filesystems). The mount story is "you're trusting the contained NanoClaw with these directories" — the safety policy needs an explicit treatment here.

**Suggested decision-log attention:** D-155's "NanoClaw adapter at v1.0" line probably wants a follow-up decision when v1.0 design begins, specifically:
- DIND vs Docker-socket-share — likely DIND.
- Long-running cell semantics for `session_log`.
- v2-only (no v1.x compatibility surface).

Not a now-decision; flag for the v1.0 design conversation.

## 4. Positioning sharpens — D-172 stronger

NanoClaw v2 has further specialized as a **personal AI assistant platform**:
- "Skills over features" philosophy in trunk.
- Channels / providers on sibling branches, installed per fork via skills.
- AI-native install flow that hands off to Claude Code on failure.
- Fork-and-customize as the only intended distribution model.

This is unambiguously a *product*, not infrastructure. The complementarity argument with Whizzard (D-172) is sharper than it was: NanoClaw is one specific opinionated platform; Whizzard is the containment layer underneath any harness. The two don't compete for the same buyer or the same role in a deployment.

**Implication for the FDE pitch to the nanocoai team:** lead with this. "Your scope reduction is excellent and your credential isolation is best-in-class; the kernel surface inside the container is still wide because you chose to keep the codebase small. Whizzard adds the hardening you'd otherwise have to maintain, without touching anything about how NanoClaw works."

**Suggested decision-log attention:** D-172's notes section could absorb a one-line reference to NanoClaw v2's specialization as additional evidence — but D-172 itself doesn't need changing.

## 5. New patterns worth noting (not now-actions)

A few v2 design choices worth a callback in future design conversations:

- **Composed-CLAUDE.md pattern** — agent's `CLAUDE.md` is composed at spawn time from policy-controlled fragments + per-group local content, mounted RO so the agent can't tamper. Same "agent can't influence its own policies" thinking as our mount-registry approach. Useful prior art if Whizzard ever ships its own native harness (D-155 v2.0 line).
- **`ncl` admin CLI with two transports + approval gate** — same surface from host (Unix socket) and from inside the container (session DB transport with approval-gated writes), with per-agent `cli_scope` controlling whether the agent learns the CLI exists. Three modes: disabled / read-only-with-approval / scoped writes. This is the kind of clean separation D-26 would want if we ever expose an agent-side API.
- **Shared agent-runner source mounted RO across all agent groups** — separates "shared infra" from "per-instance state." A pattern worth borrowing for any Whizzard service that has versioned shared code with per-deployment state.
- **One-writer-per-DB-file with file-touch heartbeat** — clever way to preserve the single-writer invariant across cross-mount IPC. Not directly applicable to Whizzard's model but worth knowing about.

---

## Summary — what would change

- **No now-changes to decisions.** D-93, D-98, D-134, D-155, D-172 all hold as-written.
- **Suggested notes-additions** when next touched: D-134 (reference v2 hard-fail pattern), D-155 (flag v1.0 NanoClaw adapter design questions when that work begins), D-172 (note v2's further specialization as additional evidence).
- **Reference updates:** internal references to `qwibitai/nanoclaw` should move to `nanocoai/nanoclaw` (old URL still resolves, but new is canonical).
- **Stage 12 implementation reference:** v2's `OneCLI gateway not applied — refusing to spawn` hard-fail is the right reference for our own failure-mode design.
- **FDE pitch:** complementarity framing is unchanged and arguably sharper. Lead with hardening differential; secondary point on audit-grade logs + image-digest pinning + profile-driven network.
