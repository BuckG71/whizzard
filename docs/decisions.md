# Whizzard — Decisions Index

## What this is

The canonical, append-only index of every decision made for the Whizzard project — architectural, scope, process, and framing. Source documents (vision, architecture, MVP plan, post-MVP, research notes, control surface, session handoff) remain authoritative for narrative and rationale; this file is the searchable index of the choices themselves. Decisions are append-only: superseded entries stay in place with a status update rather than being deleted, so cross-references stay stable. Decisions made in conversation but not yet reflected in source docs are flagged with `Source: conversation YYYY-MM-DD`.

> Naming note: as of 2026-05-09 (D-144), the project consolidated from a two-name framing ("Airlock = governance, Whizzard = orchestrator") to a single name "Whizzard". Pre-D-144 entries that reference "Airlock" describe what is now called "Whizzard core"; their substance is unchanged. Entries D-01 through D-08 are partially historical (placeholder repo and package names that have since changed).

## Status legend

- **active** — currently in force
- **superseded by D-NN** — replaced by a newer decision; the new ID is given
- **deprecated** — explicitly retired without a successor
- **open** — surfaced as a decision-shaped question but not yet resolved

---

### D-01: Repo placeholder name is `basicagentauth`

**Type:** naming

**Door Type:** two-way (repo names are renamable; this placeholder was itself superseded by D-145).

**Decision:** Public/private GitHub repo ships under the placeholder name `basicagentauth`.

**Rationale:** Real product names are still in flux; an opaque placeholder avoids premature naming commitments.

**Source:** docs/session_handoff.md

**Status:** superseded by D-145

### D-02: Internal package name is `whizzard` (replaces `warlock`)

**Type:** naming

**Door Type:** two-way (package can be renamed; was already renamed once from `warlock`).

**Decision:** Python package and CLI command are named `whizzard`.

**Rationale:** Original name `warlock` collided with an active 2026 ransomware family; renamed to avoid the collision.

**Source:** docs/session_handoff.md; pyproject.toml

**Status:** superseded by D-158

### D-03: Local working directory stays `airlock-warlock` mid-development

**Type:** naming

**Door Type:** two-way (working directories can be renamed between sessions; this was, per D-146).

**Decision:** Do not rename the working directory mid-session; it remains `airlock-warlock` despite the package rename.

**Rationale:** Renaming mid-session breaks Claude Code's working-directory binding.

**Source:** docs/session_handoff.md

**Status:** superseded by D-146 (rename happens between sessions, not mid-session)

### D-04: Two-name component split — Airlock vs. Whizzard

**Type:** naming

**Door Type:** two-way (verbal framing only; was superseded by D-144's single-name consolidation).

**Decision:** Airlock = governance/containment layer; Whizzard = orchestrator/runtime.

**Rationale:** Two-component naming maps to the split between policy enforcement and harness orchestration; keeps the layering explicit in user-facing language.

**Source:** docs/vision_and_strategy.md; docs/architecture.md

**Status:** superseded by D-144

### D-05: Verbal framing — "Whizzard operates. Airlock governs."

**Type:** naming

**Door Type:** two-way (verbal framing; superseded by D-144).

**Decision:** Adopt "Whizzard operates / Airlock governs" (alt: "Whizzard executes inside Airlock") as the canonical short framing.

**Rationale:** Keeps the directionality of capability flow visible in copy.

**Source:** docs/vision_and_strategy.md; docs/architecture.md

**Status:** superseded by D-144

### D-06: License is MIT

**Type:** naming

**Door Type:** one-way (license commitments are sticky once distributed under OSS).

**Decision:** Project licensed MIT.

**Rationale:** Default permissive license aligned with OSS-launch goals.

**Source:** pyproject.toml

**Status:** active

### D-07: Initial version is 0.1.0; Python 3.11+

**Type:** naming

**Door Type:** two-way (version and Python floor evolve naturally over the project's life).

**Decision:** Initial package version is 0.1.0; minimum Python is 3.11.

**Rationale:** Pre-1.0 signals MVP/under-construction status; Python 3.11 gives modern typing without forcing 3.12.

**Source:** pyproject.toml

**Status:** active

### D-08: WHIZZARD_HOME defaults to `~/.whizzard`

**Type:** architecture

**Door Type:** two-way (env-var override allows alternate layouts; default could change without breaking existing users).

**Decision:** Whizzard's host-side state directory is `~/.whizzard` (override via `WHIZZARD_HOME` env var).

**Rationale:** Standard dotfile convention; env-var override allows test isolation and alternate layouts.

**Source:** whizzard/config.py

**Status:** active

---

### D-09: One-way capability flow

**Type:** foundational

**Door Type:** one-way (THE foundational trust principle — agents self-granting capabilities would collapse the entire security premise of the system).

**Decision:** Agents request capabilities; Whizzard grants; agents never self-grant.

**Rationale:** Foundational trust model for the whole system; any feature that violates this breaks the security thesis.

**Source:** README.md; docs/architecture.md (Architectural Constants)

**Status:** active

### D-10: Whizzard core stays harness-neutral

**Type:** foundational

**Door Type:** one-way (the harness-neutral core is what makes the adapter pattern work; coupling core to a specific harness would force every other adapter to fight against the model).

**Decision:** Whizzard core must know nothing about Hermes, OpenClaw, NanoClaw, Discord, or MCP specifics. All harness-specific logic lives in adapters.

**Rationale:** Coupling core to any specific harness collapses the layering and makes future harnesses second-class.

**Source:** docs/architecture.md (Whizzard Core; pre-D-144 referred to as "Airlock Core")

**Status:** active

### D-11: The mount list IS the permission model

**Type:** foundational

**Door Type:** one-way (visible-mount-list-as-permissions is the entire UX model for capability grants; abstract policy would change what Whizzard *is*).

**Decision:** Capability grants are the literal, visible list of mounts and toggles a user sees before launch — not abstract policy declarations.

**Rationale:** Makes permissions human-readable, auditable at a glance, and reduces accidental exposure.

**Source:** docs/vision_and_strategy.md; docs/architecture.md

**Status:** active

### D-12: Config integrity is non-negotiable

**Type:** foundational

**Door Type:** one-way (an agent that can influence its own policies has effectively no policies; this is load-bearing for the trust model).

**Decision:** Agent-reachable mount paths must never include the Whizzard config directory, regardless of policy files.

**Rationale:** An agent that can write files Whizzard reads can influence its own policies, breaking the trust model. Cannot be relaxed by profiles or presets.

**Source:** docs/architecture.md (Config Write-Protection Invariant)

**Status:** active

### D-13: Time-bounded sessions are enforced, not advisory

**Type:** foundational

**Door Type:** one-way (an advisory cap is no cap; safety guarantees depend on the runtime actually terminating).

**Decision:** Session duration is a first-class capability primitive that Whizzard enforces; unlimited is explicit, never the silent default.

**Rationale:** A "soft" duration cap is a non-cap; safety hinges on the runtime actually terminating.

**Source:** docs/architecture.md; docs/post_mvp_spec.md §5

**Status:** active

### D-14: "Mount allowlist outside agent reach" is an architectural principle

**Type:** foundational

**Door Type:** one-way (architectural elevation of D-12; the allowlist being unreachable from agent-writable mounts is what makes mount-based permissions trustworthy).

**Decision:** The directory that defines an agent's permissions must be unreachable (and unwritable) from any agent-writable mount.

**Rationale:** Validated against NanoClaw's external `~/.config/nanoclaw/mount-allowlist.json` pattern; same principle as config write-protection but elevated as a general rule.

**Source:** docs/archive/nanoclaw_research.md (Things to learn from NanoClaw)

**Status:** active

### D-15: Useful + controlled + simple is the middle-ground positioning

**Type:** foundational

**Door Type:** one-way (product positioning; reversing would be a market repositioning, not a feature toggle).

**Decision:** The product target is the middle ground between unrestricted trust and unusably-restrictive sandboxes.

**Rationale:** Existing options force a binary choice; the durable opportunity is dynamic capability governance for daily-driver use.

**Source:** docs/vision_and_strategy.md (Long-Term Strategic Thesis)

**Status:** active

### D-16: This is NOT an agent platform / chatbot / coding assistant / Docker wrapper / generic AI sandbox / security utility

**Type:** foundational

**Door Type:** one-way (negative positioning; pivoting into one of the rejected categories would be a product rebrand).

**Decision:** Reject positioning as any of the listed categories.

**Rationale:** Sharper "what we are not" framing protects the actual positioning ("local capability governance layer for autonomous AI systems").

**Source:** docs/vision_and_strategy.md (Product Positioning)

**Status:** active

### D-17: Not competing with Claude Code / Codex / Cursor

**Type:** foundational

**Door Type:** one-way (target-audience positioning; competing with major harnesses would be a different product).

**Decision:** Whizzard targets local/open-source agents (Hermes, OpenClaw, NanoClaw) and solo-developer power users — not the major harness vendors.

**Rationale:** Major harness providers will likely absorb basic sandboxing; the durable opportunity is cross-agent, harness-neutral governance.

**Source:** docs/vision_and_strategy.md

**Status:** active

### D-18: Not initially targeting enterprise IAM, SOC2, centralized governance

**Type:** foundational

**Door Type:** one-way (v1 audience scope; enterprise governance is a different product shape, not a feature add).

**Decision:** Enterprise/compliance audiences are explicitly out-of-scope for v1.

**Rationale:** v1 audience is solo developers, AI power users, security-conscious tinkerers; enterprise governance is a different product shape.

**Source:** docs/vision_and_strategy.md (Intended Audience)

**Status:** active

---

### D-19: Four named components — Whizzard, Airlock, Execution Cell, Harness Adapter

**Type:** architecture

**Door Type:** one-way (vocabulary is now baked into docs and code; renaming components requires sweeping doc + code updates — D-144 already proved how much work even partial renaming is).

**Decision:** Component vocabulary is fixed at: Whizzard (orchestrator), Airlock (policy/containment), Execution Cell (the contained environment, Docker in MVP), Harness Adapter (integration layer). *(Three components after D-144 consolidation: Whizzard, Execution Cell, Harness Adapter.)*

**Rationale:** Stable vocabulary lets docs and code converge; alternatives (e.g., calling the cell "the container") leak implementation detail.

**Source:** docs/architecture.md (System Components)

**Status:** partially superseded by D-144 (the Airlock sub-component name is retired; the other three names remain)

### D-20: Three architecture layers — Whizzard Core, Adapter Layer, Execution Backend

**Type:** architecture

**Door Type:** one-way (layering is what makes the adapter pattern + harness-neutral core possible; reversing collapses both).

**Decision:** The system is organized as Whizzard Core (harness-neutral) → Harness Adapter Layer → Execution Backend. *(Pre-D-144: "Airlock Core" was the term for what is now "Whizzard Core".)*

**Rationale:** Clean seams allow swapping execution backends and adding adapters without touching core; matches the trust model.

**Source:** docs/architecture.md (Architecture Layers)

**Status:** active

### D-21: Host = control plane; container = execution plane

**Type:** architecture

**Door Type:** one-way (security-model foundation — putting policy controls inside the container puts them in the agent's reach).

**Decision:** Whizzard daemon, policy engine, config registry, logs, and the future Discord bot run on the host. Agent runtime, shell, filesystem access, and tool execution run inside the container.

**Rationale:** Mandatory for the security model — control surfaces above the agent's reach.

**Source:** docs/architecture.md (Host vs Container Boundary)

**Status:** active

### D-22: Docker is the MVP execution backend; Podman/Firecracker/etc. are future

**Type:** architecture

**Door Type:** two-way (Docker is the MVP-only choice; D-20's layer pattern is explicitly designed so alternative backends (Podman, Firecracker, Apple Virtualization) can land later without core changes).

**Decision:** MVP ships on Docker only; alternative backends (Podman, Firecracker, Apple Virtualization, cloud) are deferred.

**Rationale:** Docker is ubiquitous on dev machines and gives the needed isolation primitives; abstracting now without a second implementation is speculative.

**Source:** docs/architecture.md (Execution Backend Layer); docs/post_mvp_spec.md (Deferred Features)

**Status:** active

### D-23: Three concentric control layers — enforcement / behavioral / cooperation

**Type:** architecture

**Door Type:** one-way (mixing the control layers duplicates harness-native work or weakens the enforcement boundary; the discipline is the design).

**Decision:** Whizzard's controls compose as outer (enforcement, kernel/Docker) → inner (behavioral, harness-native) → innermost (cooperation, Whiz MCP server).

**Rationale:** Each layer has a different shape, owner, and enforcement mechanism; mixing them duplicates harness work or weakens the trust model.

**Source:** docs/architecture.md (Control Layering); docs/control_surface.md

**Status:** active

### D-24: Whizzard does not recreate harness-native behavioral controls

**Type:** architecture

**Door Type:** one-way (duplicating harness-native controls would create permanent maintenance debt; the discipline is part of how the adapter pattern earns its keep).

**Decision:** Dangerous-command approval, tool intent gating, `/yolo`, smart-mode aux LLM, and similar in-session interception remain harness-owned. Whizzard does not duplicate them.

**Rationale:** Both Hermes and NanoClaw ship robust behavioral layers; recreating adds surface area for no gain. Layering is the discipline.

**Source:** docs/architecture.md; docs/archive/hermes_research.md; docs/control_surface.md

**Status:** active

### D-25: MCP support is treated as a baseline harness capability

**Type:** architecture

**Door Type:** one-way for MVP (treating MCP per-adapter would explode the adapter contract; this assumption simplifies design).

**Decision:** Whizzard assumes all modern agent harnesses support MCP; the Whiz MCP server is a first-class design element, not a per-adapter capability flag.

**Rationale:** Avoids re-deriving the assumption per adapter; reflects observed reality across Hermes, NanoClaw, and Claude-based harnesses.

**Source:** docs/architecture.md; docs/control_surface.md (framing decisions, conversation 2026-05-09)

**Status:** active

### D-26: Cooperation layer never replaces enforcement layer

**Type:** architecture

**Door Type:** one-way (a running agent mutating its own enforcement boundary collapses the trust model).

**Decision:** Capability-change requests via the Whiz MCP server are mediated host-side; structural changes still require stop+restart of the container, not in-place mutation.

**Rationale:** Letting a running agent mutate its own enforcement boundary collapses the trust model.

**Source:** docs/architecture.md (Cooperation layer); docs/control_surface.md

**Status:** active

### D-27: Mid-session capability adjustment = stop+restart

**Type:** architecture

**Door Type:** one-way (in-place mutation would violate D-26 and reintroduce the boundary-bleed problem stop+restart was chosen to avoid).

**Decision:** When the user (or agent via MCP) requests a capability change mid-session, Whizzard wraps up the harness, terminates the container, and relaunches with new flags.

**Rationale:** Acceptable friction in exchange for a clean state model; avoids in-place mutation of an active enforcement envelope.

**Source:** docs/control_surface.md (framing decisions, conversation 2026-05-09)

**Status:** active

---

### D-28: Adapter is a Python `Protocol`, not an abstract base class

**Type:** architecture

**Door Type:** two-way (Protocol vs. ABC is an implementation choice; swapping would require updating every adapter but doesn't change the design).

**Decision:** `HarnessAdapter` is a `runtime_checkable` Protocol with positional methods — `start_command`, `container_env`, `working_dir`, `wrap_up`, `health_check_command` — plus a `name` attribute.

**Rationale:** Structural typing is lighter than ABCs and matches the small surface; `runtime_checkable` enables isinstance checks without inheritance.

**Source:** whizzard/adapters/base.py

**Status:** active

### D-29: `wrap_up` is required from MVP, not deferred to v1

**Type:** architecture

**Door Type:** two-way (could be deferred at MVP cost, but adding later forces a breaking interface change once Hermes needs it — chosen the cheap-now/expensive-later side).

**Decision:** Every adapter implements `wrap_up(grace_seconds)`; the generic shell adapter returns `NO_OP`.

**Rationale:** Adding the method later would force an interface change once the Hermes adapter needs it; cheap to define now.

**Source:** docs/architecture.md (Harness Adapter Layer); docs/mvp_build_plan.md (Stage 7)

**Status:** active

### D-30: WrapUpStatus enum has four values — SUCCESS / TIMEOUT / NO_OP / ERROR

**Type:** architecture

**Door Type:** two-way (the enum can be extended without breaking adapters; reducing or renaming values would be breaking).

**Decision:** Wrap-up outcomes are discrete and enumerated.

**Rationale:** Forces every adapter to map its shutdown semantics into a small known set; avoids ad-hoc string comparisons in the orchestrator.

**Source:** whizzard/adapters/base.py

**Status:** active

### D-31: Adapters must not sleep beyond `grace_seconds`

**Type:** architecture

**Door Type:** one-way (the grace bound is what makes wrap_up's contract trustworthy; relaxing it means termination could hang).

**Decision:** `wrap_up` implementations must return promptly with TIMEOUT if the harness has not acknowledged within the grace window.

**Rationale:** Wrap-up cannot be allowed to block container termination indefinitely; the grace bound is the contract.

**Source:** whizzard/adapters/base.py

**Status:** active

### D-32: Agent identity is the adapter's responsibility, not core's

**Type:** architecture

**Door Type:** two-way for now (cryptographic verification is a future problem per the rationale; today's trust model can tighten without breaking the API).

**Decision:** Whizzard core does not assume agent identity is available. Adapters tag tool execution with agent identity at the harness boundary; core trusts that claim.

**Rationale:** Per-agent policy needs identity; harnesses Whizzard does not own can't be required to expose it natively. Cryptographic verification is a future problem.

**Source:** docs/architecture.md (Agent Identity)

**Status:** active

### D-33: `harnesses.json` is a versioned schema with required + optional fields

**Type:** architecture

**Door Type:** two-way (`schema_version` is explicitly there so fields can be added or changed without breaking existing configs).

**Decision:** Required: `type`, `start_command`. Optional: `stop_command`, `wrap_up_command`, `wrap_up_grace_seconds`, `working_dir`, `health_check`, `startup_timeout_seconds`, `env`, `description`. Top-level `schema_version`.

**Rationale:** Versioning lets the schema grow without breaking configs; parser must accept and ignore optional fields from day one to avoid breaking changes later.

**Source:** docs/architecture.md (Harness Adapter Schema)

**Status:** active

### D-34: Two harness types — `shell` and `agent`

**Type:** architecture

**Door Type:** two-way (new types can be added with a schema_version bump; the current pair was the conservative MVP choice).

**Decision:** `harnesses.json` accepts `type: "shell"` (Stage 7) and `type: "agent"` (Stage 8+). Other types are rejected.

**Rationale:** Two types cover all current and planned adapters; new types can be added with a schema bump.

**Source:** whizzard/adapters/__init__.py; docs/stage_validation.md (Stage 7 Step 8)

**Status:** active

### D-35: Initial adapter slate = generic (MVP), Hermes / OpenClaw / NanoClaw (post-MVP)

**Type:** architecture

**Door Type:** two-way (sequencing of adapter deliveries; the order can shift without changing the architecture).

**Decision:** MVP ships only the generic shell adapter; Hermes is Stage 8; OpenClaw and NanoClaw are post-MVP.

**Rationale:** Prove the abstraction with a trivial adapter before any harness-specific work.

**Source:** docs/architecture.md; docs/post_mvp_spec.md §3

**Status:** superseded by D-155 (which locks in the core-maintained slate as Hermes at MVP, NanoClaw at v1.0, native harness at v2.0; OpenClaw moves to the community-maintained tier).

### D-36: MCP gateway adapter is post-v1 backlog

**Type:** architecture

**Door Type:** two-way (named-in-architecture-but-unscheduled; could be promoted into v1 if MCP-mediated tool routing becomes critical).

**Decision:** A future MCP gateway adapter is named in the architecture but not scheduled.

**Rationale:** Direction, not deliverable; pinning a date now is speculative.

**Source:** docs/architecture.md; docs/post_mvp_spec.md §4

**Status:** active

---

### D-37: Five built-in profiles — safe / default / build / power / quarantine

**Type:** architecture

**Door Type:** two-way (the bundled set can grow or shrink; adding profiles is non-breaking, removing requires considering existing user configs).

**Decision:** Bundled profile set is fixed at five named profiles with the documented capability shapes.

**Rationale:** Covers the major usage modes (offline, baseline, dev, power-user, untrusted) without overwhelming users with options.

**Source:** docs/mvp_build_plan.md (Stage 3); whizzard/config.py `_DEFAULT_PROFILES`; docs/session_handoff.md

**Status:** active

### D-38: Default profile is "SAFE-NET" — network on, no mounts, unlimited duration

**Type:** architecture

**Door Type:** two-way (default values; changing them is non-breaking but would surprise users who rely on the current shape).

**Decision:** The `default` profile is the always-on baseline: network enabled, no mounts pre-bound, no duration cap, broad-mount override disabled.

**Rationale:** Useful by default without unrestricted host access; unlimited duration on the productive baseline avoids unnecessary friction for the common case.

**Source:** docs/mvp_build_plan.md (Stage 3); whizzard/config.py

**Status:** partially superseded by D-157 on the `allow_broad_mount` field (now `true`). Other fields (network_enabled, duration_seconds, no-mounts-pre-bound) remain as captured here.

### D-39: Profile schema is JSON with a versioned envelope

**Type:** architecture

**Door Type:** two-way (`schema_version` is there exactly so the shape can evolve).

**Decision:** Profiles are stored in `~/.whizzard/config/profiles.json` with a `schema_version` field and a `profiles` map; required keys per profile are `network_enabled` and `duration_seconds` (null = unlimited).

**Rationale:** Versioned JSON is human-editable, parseable, and extensible; required fields force explicit choices.

**Source:** whizzard/config.py

**Status:** active

### D-40: Bundled defaults are in code, copied to user config on `init`

**Type:** architecture

**Door Type:** two-way (where defaults live is an implementation choice; could move to a bundled file later if customization patterns demand it).

**Decision:** Default profiles ship in the `whizzard.config._DEFAULT_PROFILES` dict; `whizzard profiles init` writes them to disk on demand.

**Rationale:** Always-available defaults work even with no user file; explicit `init` makes customization opt-in and prevents accidental clobber.

**Source:** whizzard/config.py; docs/stage_validation.md (Stage 3)

**Status:** active

### D-41: `profiles init` refuses to clobber without `--force`

**Type:** architecture

**Door Type:** two-way (safety UX choice; could be relaxed if a different non-destructive customization model emerged).

**Decision:** If `~/.whizzard/config/profiles.json` exists, `init` exits 1 with a message; `--force` overwrites silently.

**Rationale:** Protect user customizations by default while preserving an explicit reset path.

**Source:** docs/stage_validation.md (Stage 3 Step 3)

**Status:** active

### D-42: Mount registry schema mirrors the profile schema

**Type:** architecture

**Door Type:** two-way (schema design choice; mirroring is for consistency, could be diverged if mounts grew shape-specific needs).

**Decision:** Mounts are stored in `~/.whizzard/config/mounts.json` with a `schema_version` field and a `mounts` map; required keys per mount are `host_path` and `default_mode` ("ro" or "rw").

**Rationale:** Consistent shape with profiles; versioned for forward compatibility.

**Source:** whizzard/mounts.py

**Status:** active

### D-43: Mounts surface inside the container at `/mounts/<name>`

**Type:** architecture

**Door Type:** two-way (path convention is just a default; could be exposed as configurable later if needed).

**Decision:** Every named mount appears at `/mounts/<name>` inside the cell, regardless of host path.

**Rationale:** Predictable in-container path layout; agent does not need to know host-side path; works with the dry-run preview cleanly.

**Source:** whizzard/mounts.py (`CONTAINER_MOUNT_ROOT`); docs/stage_validation.md (Stage 2 Step 4)

**Status:** active

### D-44: `default_mode` caps the maximum permission per mount

**Type:** architecture

**Door Type:** one-way (registry-as-permission-ceiling is the trust model for mounts; CLI escalation would break D-11 visibility).

**Decision:** A mount registered "ro" cannot be requested "rw" via the CLI; the registry caps permissions, the CLI can only request equal or lower.

**Rationale:** Registry is the source of truth for the permission ceiling; CLI cannot escalate.

**Source:** whizzard/mounts.py (`resolve_mount_spec`); docs/stage_validation.md (Stage 2 Step 6)

**Status:** active

### D-45: Unknown mount names are rejected before launch

**Type:** architecture

**Door Type:** one-way (mounts are defined by their registry entry; accepting unknown names would mean treating them as something other than what mounts are).

**Decision:** A `--mount <name>` referring to an unregistered name produces a clean error and aborts before container start.

**Rationale:** Fail-loud at config time, not runtime; matches the "the registry IS the permission model" framing.

**Source:** whizzard/mounts.py; docs/stage_validation.md (Stage 2 Step 8)

**Status:** active

### D-46: Two-gate broad-mount override

**Type:** architecture

**Door Type:** one-way (both gates exist to reduce accidental override; collapsing to one collapses the defense layer).

**Decision:** Mounting a path on the override-required tier requires BOTH the profile's `allow_broad_mount: true` AND the CLI flag `--allow-broad-mount`. Either alone is insufficient.

**Rationale:** Profile sets the ceiling; CLI confirms the specific session intent. Two independent gates reduce accidental override.

**Source:** docs/architecture.md (Safety Policy); docs/session_handoff.md; docs/stage_validation.md (Stage 6 Steps 4-6)

**Status:** active

---

### D-47: Three safety tiers — hard block / override-required / allowed

**Type:** safety

**Door Type:** one-way (the three-tier model is what shapes the safety policy's API; collapsing to two tiers would erase the override-with-record concept).

**Decision:** Mount paths are classified into three tiers with distinct enforcement behavior.

**Rationale:** Cleaner than a binary block/allow; matches the real risk gradient (some paths are categorically wrong, some are user-judgment, most are fine).

**Source:** docs/architecture.md (Safety Policy)

**Status:** active

### D-48: Hard-block list is non-overridable

**Type:** safety

**Door Type:** one-way (the categorical-wrong premise is the whole reason these paths are on the list; if any flag could override, the list isn't categorical).

**Decision:** The hard-block list — `/`, `$HOME`, `~/.ssh`, `~/Library`, Keychains, browser profiles, Docker socket, Whizzard config dir — cannot be overridden by any flag, profile, or preset.

**Rationale:** Some paths are categorically wrong to mount; making them overridable means somebody will override them.

**Source:** docs/architecture.md (Safety Policy); docs/session_handoff.md

**Status:** active

### D-49: Override mechanism is intentional friction; no warning-only middle ground

**Type:** safety

**Door Type:** one-way (warning-only patterns are documented to degrade quickly; the friction is the feature).

**Decision:** The override-required tier is "block by default, require explicit user action, log every override." Warnings (which tend to be ignored) are not used.

**Rationale:** Warnings without enforcement degrade quickly; explicit-action gates create a record and force intent.

**Source:** docs/architecture.md (Safety Policy)

**Status:** active

### D-50: Parent-of-registered-mount is override-required

**Type:** safety

**Door Type:** one-way (silent widening is the failure mode we're defending against; demoting parents to allowed re-introduces it).

**Decision:** Mounting a path that is the parent directory of any other registered mount is treated as broad-folder override-required, even if the parent itself is not on a static block list.

**Rationale:** Mounting a parent unintentionally widens the agent's view to include all sibling mounts; treat it as a broad-mount decision.

**Source:** docs/architecture.md (Safety Policy); docs/stage_validation.md (Stage 6 Step 7)

**Status:** active

### D-51: Cloud-sync roots (iCloud Drive, Dropbox, OneDrive) are override-required

**Type:** safety

**Door Type:** one-way (off-machine propagation is the failure mode; demoting cloud-sync to allowed re-introduces it).

**Decision:** Cloud-sync roots are on the override-required tier, not the allowed tier.

**Rationale:** A write inside a sync root propagates off-machine; that warrants explicit user intent.

**Source:** docs/architecture.md (Safety Policy)

**Status:** active

### D-52: Symlink targets are resolved before validation

**Type:** safety

**Door Type:** one-way (resolving before checking is what makes the block list trustworthy against symlink-rewriting attacks).

**Decision:** Safety check resolves symlinks before classifying a path against the block lists.

**Rationale:** Otherwise an attacker can register a symlink whose target is a hard-blocked path; resolve-then-check defeats this.

**Source:** docs/architecture.md (Safety Policy); docs/archive/nanoclaw_research.md (comparison table)

**Status:** active

### D-53: Override usage is recorded in the session log

**Type:** safety

**Door Type:** one-way (D-49 specifically requires logging every override; reversing would empty out that half of the policy).

**Decision:** Any override applied to a session is written to `session_start` under `overrides_used` with the reason string.

**Rationale:** Required for the "log every override" half of D-49; makes overrides post-hoc auditable.

**Source:** docs/architecture.md; docs/stage_validation.md (Stage 6 Step 6)

**Status:** active

### D-54: Dry-run is subject to the same safety gates as live runs

**Type:** safety

**Door Type:** one-way (dry-run-as-preview only works if it surfaces real errors; turning it into a bypass would silently hide safety violations).

**Decision:** Safety errors fire under `--dry-run` exactly as they do under live execution.

**Rationale:** Dry-run is a preview, not a bypass; surfacing errors there is the whole point.

**Source:** docs/stage_validation.md (Stage 6 Step 8)

**Status:** active

---

### D-55: Container runs as fixed UID 1000 by default

**Type:** safety

**Door Type:** two-way (UID 1000 is the default; D-56 already proved scoped per-mount UID parity can layer on without breaking the model).

**Decision:** Default in-container user is `whizzard` at UID 1000.

**Rationale:** Non-root containment without per-host configuration; matches the established Linux convention.

**Source:** docs/stage_validation.md (Stage 1); docs/session_handoff.md

**Status:** active

### D-56: Hermes adapter uses scoped UID parity for the profile mount

**Type:** safety

**Door Type:** two-way (carved out for Hermes's self-improvement writes; the pattern can be reused or retracted per adapter as needed).

**Decision:** When the Hermes adapter is in use, the container UID matches the host UID for the Hermes profile mount specifically; other mounts and the rest of the container retain the default UID 1000.

**Rationale:** Hermes self-improvement requires write access to host-side memories/skills/state.db; on raw Linux without Docker Desktop's transparent UID translation, fixed UID 1000 makes those writes fail. Scoped parity preserves writes for the profile mount only.

**Source:** docs/session_handoff.md (Stage 8 design state, item 4)

**Status:** active

**Notes:** Logged in `session_start`. Mirrors NanoClaw's hybrid pattern (UID 1000 unless host UID differs).

### D-57: `--cap-drop=ALL` is mandatory

**Type:** safety

**Door Type:** one-way (all-capabilities-dropped baseline minimizes the in-container kernel surface; relaxing adds attack surface for negligible benefit).

**Decision:** All Linux capabilities are dropped in every cell.

**Rationale:** Defense in depth; even if an exploit lands inside the container, it has no extra capabilities to leverage.

**Source:** docs/session_handoff.md; docs/control_surface.md (§3); docs/archive/nanoclaw_research.md (comparison)

**Status:** active

### D-58: `--security-opt no-new-privileges` is mandatory

**Type:** safety

**Door Type:** one-way (defeats setuid-driven privilege escalation; removing re-opens that path with no offsetting benefit).

**Decision:** All cells run with `no-new-privileges` set.

**Rationale:** Defeats setuid-binary privilege elevation paths.

**Source:** docs/session_handoff.md; docs/control_surface.md (§3)

**Status:** active

### D-59: Read-only root filesystem with tmpfs scratch

**Type:** safety

**Door Type:** one-way (read-only root is the structural prevention of in-container persistence; tmpfs gives the agent everything it needs without that drawback).

**Decision:** Root filesystem is `--read-only`. `/tmp` and `/home/whizzard` are tmpfs.

**Rationale:** Prevents persistent in-container modification; tmpfs gives the agent the writable space it needs without persisting it.

**Source:** docs/session_handoff.md; docs/stage_validation.md (Stage 1 Step 4); docs/control_surface.md (§3)

**Status:** active

### D-60: Network policy is profile-driven, on/off only in MVP

**Type:** safety

**Door Type:** two-way (on/off was the MVP-scoped choice; D-132 is the explicit path to richer egress allowlists post-MVP via a sidecar proxy).

**Decision:** MVP supports `--network none` (off) or default bridge (on), set per profile. Egress allowlists by host/port are post-MVP.

**Rationale:** Profile-driven on/off is sufficient for the MVP threat model; granular egress requires a sidecar proxy that's a real architectural commitment.

**Source:** docs/architecture.md; docs/control_surface.md (§2)

**Status:** active

### D-61: Whizzard does not use host networking by default

**Type:** safety

**Door Type:** one-way (host networking — Hermes's own Docker default — defeats containment; matching it would surrender the network boundary).

**Decision:** Cells do not run with `--network host`.

**Rationale:** Hermes's own Docker setup uses `network_mode: host` for convenience; that defeats containment. Whizzard explicitly does not.

**Source:** docs/archive/hermes_research.md (Existing Docker setup)

**Status:** active

### D-62: Image base must be hardened (non-root, minimal)

**Type:** safety

**Door Type:** one-way (image hardening is part of the security surface, not a deployment afterthought; degrading the base would move in the wrong direction).

**Decision:** The execution image is built from a minimal base with non-root default user.

**Rationale:** Hardened base is part of the security surface, not a deployment afterthought.

**Source:** docs/control_surface.md (§7); docs/stage_validation.md (Stage 1)

**Status:** active

### D-63: Custom seccomp / AppArmor / SELinux profiles are out of scope for MVP

**Type:** safety

**Door Type:** two-way (deferred for MVP audience; could be promoted if the v1 audience expands to include personas that need it).

**Decision:** MVP relies on Docker default seccomp. AppArmor/SELinux are deprioritized indefinitely.

**Rationale:** Linux-only and enterprise-shaped; v1 audience does not include the personas who need this.

**Source:** docs/control_surface.md (§3 and "What's explicitly out of scope")

**Status:** active

---

### D-64: Session log is JSONL with paired start + end records

**Type:** architecture

**Door Type:** two-way (JSONL with paired records is the chosen format; switching would require updating tools that tail/parse the log, but the file format itself is replaceable).

**Decision:** Sessions are logged as one `session_start` and one `session_end` JSONL record per session, sharing a `session_id`. File path: `~/.whizzard/logs/sessions.jsonl`.

**Rationale:** JSONL is append-friendly, line-parseable, and tail-friendly. Paired records make sessions trivially reconstructable.

**Source:** docs/mvp_build_plan.md (Stage 5); docs/stage_validation.md (Stage 5)

**Status:** active

### D-65: Session ID is a UUID assigned pre-launch

**Type:** architecture

**Door Type:** two-way (UUID is the convention; could switch to ulid or similar without semantic loss — but existing log entries would coexist).

**Decision:** Session ID is a UUID generated before the container starts; surfaced in the banner and stamped on the container as a label (`whizzard.session_id=<uuid>`).

**Rationale:** Allows the container to be located via Docker filters and tied to its log entries even if the host process crashes mid-session.

**Source:** docs/stage_validation.md (Stage 5 Step 1)

**Status:** active

### D-66: Session log captures image_id, container_id, profile, mounts, network, argv, expiry reason, exit status

**Type:** architecture

**Door Type:** two-way (the captured-field set can be extended without breaking parsers; removing fields would break audit-trail expectations).

**Decision:** Required fields in the session log are enumerated in Stage 5; image_id is the resolved sha256 digest, container_id is captured via `--cidfile`.

**Rationale:** "Audit-grade" needs to include enough to reconstruct what ran and what could be done with it; image_id closes the "stale image" risk loop.

**Source:** docs/mvp_build_plan.md (Stage 5)

**Status:** active

### D-67: Pre-flight failures do NOT write a session log entry

**Type:** architecture

**Door Type:** two-way (logging-or-not for pre-flight failures is a UX choice; either path is implementable, current choice keeps the audit trail clean).

**Decision:** If pre-launch validation (unknown profile, missing image, safety violation) fails, no session log entry is written.

**Rationale:** No session ran; logging would clutter the audit trail with non-events. The CLI error message is the audit record.

**Source:** docs/stage_validation.md (Stage 5 Step 7)

**Status:** active

### D-68: Termination flow is wrap_up → SIGTERM → 5s grace → SIGKILL

**Type:** architecture

**Door Type:** two-way (sequencing and timing are tunable defaults; the wrap_up → escalating-signals shape is the load-bearing pattern, specifics are adjustable).

**Decision:** Session termination sequence: invoke `adapter.wrap_up(grace_seconds)`; then SIGTERM; then a fixed 5s final grace; then SIGKILL.

**Rationale:** Gives the harness its native shutdown path, then a deterministic kill path bounded by configured grace + 5s.

**Source:** docs/mvp_build_plan.md (Stage 5 termination flow)

**Status:** active

### D-69: Each step in the termination flow is logged with timestamps

**Type:** architecture

**Door Type:** two-way (logging granularity is adjustable; full timestamps were chosen because wind-down is the riskiest moment).

**Decision:** wrap-up command sent, response received or timeout, duration consumed, and whether SIGTERM was sufficient or SIGKILL was required are all logged.

**Rationale:** Wind-down is the riskiest moment; full timestamps make it auditable.

**Source:** docs/mvp_build_plan.md (Stage 5)

**Status:** active

### D-70: Dry-run does NOT write to the session log

**Type:** architecture

**Door Type:** two-way (dry-run-as-preview-only is a deliberate UX choice; could be enabled with a flag if a future use case appears).

**Decision:** `--dry-run` previews the docker invocation but writes nothing to `sessions.jsonl`.

**Rationale:** Dry-run is informational; session log is for actual sessions.

**Source:** docs/stage_validation.md (Stage 5 Step 1)

**Status:** active

### D-71: Dry-run does NOT check image existence

**Type:** architecture

**Door Type:** two-way (current choice favors scripting flexibility; could be tightened with a flag if false-positive previews become a problem).

**Decision:** `--dry-run` prints the full preview even if the referenced image is not built locally.

**Rationale:** Dry-run is for previewing intent; gating on image presence undermines its usefulness during scripting and dry-run-before-build flows.

**Source:** docs/stage_validation.md (Stage 4 Step 5)

**Status:** active

---

### D-72: Dockerfile lives at `docker/Dockerfile`

**Type:** architecture

**Door Type:** two-way (conventional location; relocating would only break the README's documented layout).

**Decision:** Single Dockerfile at the repo's `docker/` directory.

**Rationale:** Conventional location; one image, one file.

**Source:** README.md (Repository layout); docs/mvp_build_plan.md

**Status:** active

### D-73: Image tag is `whizzard-base:latest` for MVP

**Type:** architecture

**Door Type:** two-way (the tag is configurable via --image; the default is convention, easy to change without breaking the build).

**Decision:** The execution image is tagged `whizzard-base:latest`.

**Rationale:** Predictable, scriptable; conventional `:latest` tag for the dev image.

**Source:** docs/stage_validation.md (Stage 1 Step 2)

**Status:** active

### D-74: `whizzard image build` and `whizzard image status` are MVP commands

**Type:** architecture

**Door Type:** two-way (subcommand naming is reorganizable as image management grows post-MVP).

**Decision:** MVP exposes image management as `image build` (rebuild local image) and `image status` (show current image id, build date, base digest).

**Rationale:** Image provenance must be visible day one; rolling these into a subcommand keeps them discoverable.

**Source:** docs/mvp_build_plan.md (Stage 9 / re-numbered Stage 11)

**Status:** active

### D-75: Image staleness check is post-MVP

**Type:** architecture

**Door Type:** two-way (deferred to v1; could be pulled into MVP if image-rot becomes a user-facing problem early).

**Decision:** `whizzard image check` against a configurable staleness threshold, plus optional auto-rebuild policy per profile, ships in v1.

**Rationale:** Useful but not necessary to prove the MVP thesis.

**Source:** docs/post_mvp_spec.md §6

**Status:** active

### D-76: Image management was Stage 9, becomes Stage 11

**Type:** architecture

**Door Type:** two-way (stage numbering is doc-tracking only; renumbering is a doc edit, not a code change).

**Decision:** The image management stage is renumbered to Stage 11; Stage 9 becomes "Whiz MCP server (read-only subset)" and Stage 10 becomes "Presets."

**Rationale:** B+D value-prop framing pulled MCP read-only and presets into MVP scope; image management is no longer the gating MVP item.

**Source:** docs/control_surface.md (Recent framing decisions, conversation 2026-05-09); conversation 2026-05-09

**Status:** active

### D-77: Base image will be digest-pinned (planned, post-MVP)

**Type:** architecture

**Door Type:** two-way (planned for Stage 11; could be done earlier if floating-tag rot bites before then).

**Decision:** The base image reference in the Dockerfile will be pinned by digest (not floating tag) once Stage 11 lands.

**Rationale:** Tag-based pulls can silently change; digest pinning closes that gap. NanoClaw's tag-only choice is explicitly something Whizzard should not borrow.

**Source:** docs/mvp_build_plan.md (Stage 9); docs/control_surface.md (§7); docs/archive/nanoclaw_research.md

**Status:** active

---

### D-78: Hermes integration only through the adapter layer

**Type:** adapter

**Tags:** hermes

**Door Type:** one-way (collapsing the adapter abstraction would make Whizzard a Hermes wrapper and block every other harness integration).

**Decision:** Hermes is integrated via the adapter contract; Whizzard is not a Hermes wrapper.

**Rationale:** Coupling Whizzard to Hermes (vs. integrating through the adapter abstraction) collapses the layering and blocks future harnesses.

**Source:** docs/mvp_build_plan.md (Stage 8); docs/architecture.md

**Status:** active

### D-79: Whizzard mounts a single Hermes profile directory as HERMES_HOME

**Type:** adapter

**Tags:** hermes

**Door Type:** one-way (HERMES_HOME is Hermes's single relocation knob; per-subdir mounting loses the isolation guarantee and adds per-file decisions).

**Decision:** The Hermes adapter mounts one Hermes profile directory (`~/.hermes/profiles/<name>/`) into the cell as the contained Hermes's `HERMES_HOME`. It does not mount per-subdirectory.

**Rationale:** `HERMES_HOME` is Hermes's single relocation knob; mounting one profile subsumes per-file decisions and isolates the contained Hermes from the host's default profile.

**Source:** docs/archive/hermes_research.md; docs/session_handoff.md (Stage 8 settled, item 1)

**Status:** active

### D-80: Credentials are injected via env vars; auth.json never enters the cell

**Type:** adapter

**Tags:** hermes

**Door Type:** one-way (auth.json in the cell means refresh tokens in the cell; the env-var path is what keeps host credentials at the boundary).

**Decision:** API credentials reach the contained Hermes as `<PLATFORM>_TOKEN` env vars via a `--expose-key NAME` flag; `auth.json` is not mounted.

**Rationale:** Hermes's `_apply_env_overrides()` officially supports env-var credential override; this is not a workaround. Keeps host credentials at the boundary.

**Source:** docs/archive/hermes_research.md; docs/session_handoff.md (Stage 8 settled, item 2)

**Status:** active

**Notes:** Vault-mediated credentials (D-100) are the eventual replacement; `--expose-key` migrates transparently.

### D-81: Hermes's approval system is the inner gate; Whizzard does not duplicate it

**Type:** adapter

**Tags:** hermes

**Door Type:** one-way (duplicating Hermes's approval system would add maintenance debt for no security gain — both gates are needed and they live at different layers by design).

**Decision:** Hermes's dangerous-command detection, manual/smart approval modes, and `/yolo` remain in force inside the cell. Whizzard's safety policy is the outer gate (mounts, network, container). The two stack.

**Rationale:** Different layers, different decisions; Hermes already does this well.

**Source:** docs/archive/hermes_research.md; docs/session_handoff.md (Stage 8 settled, item 3)

**Status:** active

### D-82: Whizzard does not ship as a Hermes plugin

**Type:** adapter

**Tags:** hermes

**Door Type:** one-way (a plugin runs *inside* Hermes; Whizzard runs Hermes inside a sandbox — reversing inverts the directionality the entire model is built on).

**Decision:** Whizzard is not implemented as a plugin loaded inside Hermes (`~/.hermes/plugins/`).

**Rationale:** A plugin runs *inside* Hermes; Whizzard runs Hermes inside a sandbox. The directionality is wrong.

**Source:** docs/archive/hermes_research.md (Plugins are NOT a path)

**Status:** active

### D-83: Wrap-up is `/quit` via `docker exec`

**Type:** adapter

**Tags:** hermes

**Door Type:** two-way (the specific `/quit via docker exec` mechanism is implementation-flexible; the load-bearing intent is the graceful-shutdown-before-SIGTERM pattern, which the Stage 8 implementation honors via `docker stop --time=<grace>`).

**Decision:** Hermes adapter sends `/quit` into the running container via `docker exec` to trigger graceful wind-down; SIGTERM is fallback.

**Rationale:** `/quit` is Hermes's native interactive wrap-up; `docker exec` is the available channel into a running container.

**Source:** docs/architecture.md (harnesses.json `wrap_up_command`); docs/session_handoff.md (Stage 8 settled, item 6)

**Status:** active

### D-84: Two operating modes — interactive and gateway

**Type:** adapter

**Tags:** hermes

**Door Type:** two-way (mode set could be expanded or pruned; current pair covers all real Hermes use cases as first-class).

**Decision:** The Hermes adapter supports both interactive (`hermes chat`) and gateway (`hermes gateway run`) modes.

**Rationale:** Both are real Hermes use cases; user has indicated gateway will be more common but interactive must remain available.

**Source:** docs/session_handoff.md (Stage 8 settled, item 7)

**Status:** active

### D-85: Whizzard profiles and Hermes profiles are orthogonal

**Type:** adapter

**Tags:** hermes

**Door Type:** one-way (collapsing the two profile concepts would force one to be a subset of the other; they describe genuinely different things at different layers).

**Decision:** Whizzard's "profile" (capability bundle: network, duration, broad-mount) and Hermes's "profile" (full HERMES_HOME directory) are different concepts at different layers and may both be specified per launch.

**Rationale:** Each describes a different thing; collapsing them would lose expressiveness.

**Source:** docs/archive/hermes_research.md (Concrete answers, Q3)

**Status:** active

### D-86: Hermes profile creation UX

**Type:** adapter

**Tags:** hermes

**Door Type:** two-way (CLI verb shape is a default; can be revisited with a flag rename or alias if the conversational model evolves).

**Decision:** A Whizzard-native verb `whiz hermes profile create <name>` provisions the contained Hermes profile (Option C — Whizzard does not auto-create on first launch, and does not require the user to invoke `hermes profile create` directly). Flags:

- `--clone-from <profile-name>` — seed the new profile from an existing host-side Hermes profile (config, SOUL.md, memories — explicitly **excluding** `auth.json` per D-80).
- `--no-clone` — create an empty profile.

Bare `whiz hermes profile create <name>` defaults to `--clone-from default` when a host-side `default` profile exists; if no host Hermes profile exists, it gracefully degrades to `--no-clone` and announces which path it took. Explicit `--clone-from <name>` for a missing profile is an error.

All three existing-user migration shapes are first-class supported paths:
- **Parallel** — host-side Hermes keeps running; cell profile is a separate sibling. Drift between host and cell profiles is expected and documented.
- **Migrate** — user transitions away from host-side Hermes after seeding; the host install becomes vestigial.
- **Clean cell** — no host-side Hermes; the cell profile is the user's first and only Hermes.

**Rationale:** Option A (auto-create on first launch) silently mutates state and has a typo failure mode — `whiz hermes whizard-cell` mistyped spawns a bogus profile and runs. Option B (require user to call `hermes profile create` directly) violates "Whiz easier than yolo" and couples Whizzard tightly to Hermes CLI shape across versions. The Whizzard-native verb keeps the surface in Whizzard's hands while delegating the actual profile-directory creation to Hermes underneath. Graceful clone-default-or-empty behavior makes the bare command Just Work for both clean-cell and existing-user paths without forcing the user to know which flag to pass first. Explicit `auth.json` omission preserves D-80 (credentials never enter the cell). Treating all three migration shapes as first-class means the docs give each substantive coverage rather than picking one as canonical — drift management becomes a real section, not a footnote.

**Source:** docs/HANDOFF.md (2026-05-14T14:14Z entry); docs/archive/hermes_research.md (Open question 1); conversation 2026-05-14

**Status:** active

### D-87: Concurrency exclusivity vs. host-side Hermes

**Type:** adapter

**Tags:** hermes

**Door Type:** one-way (`--force` was deliberately excluded for MVP per D-12 alignment; reversing would allow the concurrent same-profile corruption that the check protects against).

**Decision:** `whiz hermes <profile>` refuses to launch when a live gateway is already holding `<profile>`'s lock. The block applies symmetrically to host-vs-cell and cell-vs-cell contention.

**Detection:** Pre-launch, check `<HERMES_HOME>/gateway.lock`. If present, read `<HERMES_HOME>/gateway.pid` and probe pid liveness (signal 0). Live pid → block with a clear error message naming the profile and conflicting pid. Lock exists but pid is dead → treat as stale, ignore, and announce the cleanup as the launch proceeds.

**Mode coverage:**
- **Gateway mode** (D-88 default): `gateway.lock` pre-check is the enforcement point. This is the primary case.
- **Interactive mode** (`--interactive`): no `gateway.lock` is written, so Whizzard does not pre-check. Hermes's own SQLite WAL + fcntl locking on `state.db` handles contention. Defense in depth, not duplicate enforcement.

**No `--force` escape valve in MVP.** A user who legitimately needs a parallel session is steered to `whiz hermes profile create <sibling> --clone-from <profile>` (D-86) — the supported path is sibling profiles, not concurrent processes on one profile.

**Error UX:** The block message names the profile, the conflicting pid, and the two supported remediations (stop the host gateway / create a sibling profile via D-86).

**Rationale:** Concurrent writers to Hermes's `state.db` and gateway state files corrupt or deadlock the profile (hermes_research.md L31–41, L76). Using Hermes's existing `gateway.lock` rather than process scanning or SQLite-lock probing keeps detection cheap, robust to Hermes version drift, and consistent with the lifecycle files Hermes already maintains. Stale-pid auto-detection avoids leaving users blocked by crashed/forgotten host processes. No `--force` for MVP keeps the corruption-protection guarantee absolute — the cost of a false positive (rare, recoverable) is low; the cost of letting two processes mangle one profile is high. The interactive-mode carve-out leans on Hermes's own internal locking rather than re-implementing it at the Whizzard layer.

**Source:** docs/HANDOFF.md (2026-05-14T14:14Z entry); docs/archive/hermes_research.md (Open question 2, L41, L76, L200, L219); conversation 2026-05-14

**Status:** active

### D-88: Default mode (interactive vs. gateway) for the Hermes adapter

**Type:** adapter

**Tags:** hermes

**Door Type:** two-way (gateway-default reflects the dominant usage pattern; flipping to interactive-default is a UX choice, not an architectural change).

**Decision:** Gateway is the default. `whiz hermes <profile>` with no mode flag launches `hermes gateway run` inside the cell. Interactive (`hermes chat`) is opt-in via an explicit `--interactive` (or equivalent) flag. **Empty-platforms guard rail:** if the selected profile's `config.yaml` declares no active platforms, gateway-default refuses to start and emits a clear error message that points the user to either configure platforms or pass `--interactive` — gateway-default does not silently fall back to interactive, and does not start an empty daemon.

**Rationale:** Whizzard's center of gravity is users who run Hermes as a 24/7 platform-connected agent (Discord, Slack, etc.), not as a CLI chat tool. Virtually every Hermes installation Bryan has seen or anticipates uses a messaging app as the primary interface; making gateway the default aligns the path of least resistance with the dominant usage pattern, and is consistent with the post-MVP Discord control plane direction. This commits D-89 (platform credential declaration UX) and D-90 (in-session approval routing) to MVP-blocking polish — they are not deferrable, since gateway-default puts both surfaces on the day-one path. The empty-platforms refusal is preferred over silent fallback because gateway-vs-interactive is a meaningful behavior difference and a misconfigured profile should fail loudly, not silently land the user in the wrong mode.

**Source:** docs/session_handoff.md (Stage 8 open #3); docs/archive/hermes_research.md (Open question 3); conversation 2026-05-09

**Status:** active

### D-89: Platform credential declaration UX in gateway mode

**Type:** adapter

**Tags:** hermes

**Door Type:** two-way (could switch back to config.yaml parsing if Hermes ever exposes a clean active-platforms field; harnesses.json declaration is the current cleanest path that respects D-153).

**Decision:** The active platform set is declared in Whizzard's `harnesses.json`, not parsed from Hermes's `config.yaml`. Capability visibility, per-launch restriction, and OneCLI-mediated credential fetch follow.

1. **Source of truth: `harnesses.json` `platforms` field.** Each Hermes harness entry declares the platforms it injects credentials for, as a list of platform names (e.g., `"platforms": ["discord", "slack"]`). The Hermes adapter reads this list to determine which credentials to fetch from OneCLI at launch. Hermes's `config.yaml` remains the source of truth for *Hermes's own* runtime behavior — Whizzard does not parse it for platform inference.
2. **Pre-launch capability-visibility banner.** Before container start, Whizzard prints the active capabilities (e.g., `Active platforms: discord, slack`). Content comes from the `active_capabilities() -> list[str]` adapter Protocol method; core prints harness-neutrally. The Hermes adapter additionally reads exactly one narrow field from `config.yaml` — `approvals.mode` — to surface the approval posture and warn at the TTY-less-gateway misconfiguration (D-90). No broader `config.yaml` parsing.
3. **Per-launch restriction via `--platforms <comma-list>`.** The flag lives under the `whiz hermes` subcommand surface (Hermes-specific, not a core flag — see D-153). It can only shrink the set declared in `harnesses.json`; attempting to expand beyond that set errors before launch.
4. **Drift between `harnesses.json` and `config.yaml` is a user-error class, surfaced by Hermes itself.** If `harnesses.json` declares `discord` but `config.yaml` has no discord config, Hermes inside the cell fails-init discord cleanly and logs it. If `config.yaml` configures `mattermost` but `harnesses.json` doesn't list it, Whizzard doesn't inject `MATTERMOST_TOKEN`, and Hermes either fails-init mattermost or runs it with no credential — visible in Hermes logs. Whizzard does not pre-validate the relationship between the two files because doing so would require parsing `config.yaml` for inference, which option 3 (this decision) explicitly avoids.
5. **Credential source for MVP: OneCLI fetch at launch (per D-134).** The Hermes adapter shells out to OneCLI for each declared platform's credential at launch and injects the fetched values as env vars (`DISCORD_BOT_TOKEN`, etc.) into the cell. No long-lived host environment variables are required. D-91's literal "credentials never enter the container" guarantee does not apply to gateway-style harnesses (the agent itself opens the platform connection from inside the cell); for Hermes, OneCLI's role is delivery mechanism only — see D-134 for the scoping nuance.

**Rationale:** The original design intent (D-89 as captured 2026-05-14T14:14Z) treated `config.yaml` as the source of truth for platform declarations, on the assumption that Hermes maintains a clean parseable active-platforms field. Inspection of the real `config.yaml` during Action 3 of the Stage 8 build revealed that Hermes's platform activation is determined by a combination of top-level platform-named sections (with varying `enabled`-like flags, `{}` empty stubs, and non-trivial config dicts), `toolsets:` entries that map to platform-specific tool sets, and internal `check_<platform>_requirements()` logic — there is no single declarative source. Reproducing this logic in the Whizzard adapter would (a) duplicate Hermes-internal behavior, which D-153 explicitly forbids, and (b) be fragile against Hermes version drift. Moving the declaration to `harnesses.json` keeps Whizzard's capability surface explicit, human-readable in Whizzard's own terms (D-11), and entirely independent of Hermes's internal logic. The cost — two declarations, one for Whizzard's credential injection and one for Hermes's own runtime — is small relative to the alternative of either replicating Hermes logic or accepting silent mis-injection. The `--platforms` flag being Hermes-subcommand-scoped (not a core flag) avoids premature abstraction — when a second agent adapter lands, its analog can take whatever shape fits, without retrofitting a generic surface.

**Source:** docs/HANDOFF.md (2026-05-14T14:14Z entry); docs/archive/hermes_research.md (Open question 4, L200); ~/.hermes/config.yaml (real-install inspection 2026-05-14); conversation 2026-05-14.

**Status:** active (amended 2026-05-14 from earlier config-yaml-as-source-of-truth shape; the earlier shape was based on an incorrect assumption about Hermes's config.yaml structure).

### D-90: In-session approval routing in gateway mode

**Type:** adapter

**Tags:** hermes

**Door Type:** one-way (D-24 forbids recreating harness-native behavioral controls; Whizzard injecting `--yolo` or routing approvals would duplicate the harness layer).

**Decision:** Whizzard does not override or route Hermes's in-session approval system; it stays out of the harness-native behavioral control surface (per D-24). The Hermes adapter's posture toward Hermes approvals is:

1. **No mode override.** Whizzard does not inject `--yolo`, does not rewrite the approval-mode field, and does not provide a Whizzard-side equivalent. Whatever the user configured in Hermes (`manual` / `smart` / `off` / `cron`) is what runs.
2. **Pre-launch warning for incompatible mode + gateway combination.** If gateway mode is active (per D-88) and the Hermes adapter reads `manual` as the approval mode, Whizzard emits a clear warning pre-launch: gateway mode has no TTY for interactive y/n prompts; the agent may stall on dangerous-command detection. The warning suggests `smart` mode (Hermes's auxiliary-LLM pre-evaluator), `off` mode (the cell's outer boundary is trusted to constrain), or waiting for Hermes's platform-routed approvals if/when they ship upstream.
3. **Approval mode appears in the capability banner.** The pre-launch banner introduced in D-89 (`Active platforms: discord, slack`) is extended to include the approval mode line, so the user sees the full capability posture before container start.
4. **No Whizzard `--yolo` flag.** Yolo is a Hermes concept; users who want it set it in their Hermes config or pass Hermes's own flag through.

**Rationale:** D-24 ("Whizzard does not recreate harness-native behavioral controls") is the load-bearing principle. Hermes already owns dangerous-command detection, approval-mode policy, and — eventually — platform-routed approval UX. Recreating any of that in Whizzard would duplicate the surface and create drift hazards as Hermes evolves. The narrow value-add Whizzard *can* provide is visibility (D-11: capability grants are human-readable) and a warning at the TTY-incompatibility failure mode, which is a predictable misconfiguration that would otherwise stall the agent silently. Surfacing the approval mode in the banner means the user sees the full capability posture in one place pre-launch, consistent with D-89's visibility principle. Bounding Whizzard's role to "warn, don't override" preserves the cooperation-layer-doesn't-replace-enforcement-layer principle (D-26).

**Source:** docs/HANDOFF.md (2026-05-14T14:14Z entry); docs/archive/hermes_research.md (Open question 5, L92-102, L172-176, L222); conversation 2026-05-14.

**Status:** active

---

### D-91: Adopt the OneCLI Agent Vault pattern (validated)

**Type:** adapter

**Tags:** nanoclaw

**Door Type:** one-way (vault-mediated credentials are the architectural direction; specific vault provider could change, but the pattern is load-bearing for credential isolation in agent-uses-external-API cases).

**Decision:** Whizzard's vault direction is the OneCLI Agent Vault pattern — credentials never enter the container; outbound HTTPS is routed through a host-side gateway that injects credentials per request.

**Rationale:** NanoClaw's production implementation validates the pattern; integrate with OneCLI rather than building from scratch.

**Source:** docs/post_mvp_spec.md (Vault-Mediated Credentials); docs/archive/nanoclaw_research.md

**Status:** active

### D-92: Mount allowlist outside the project root is an explicit principle

**Type:** adapter

**Tags:** nanoclaw

**Door Type:** one-way (elevation of D-14 from emergent to named principle; reversing would un-name the rule and let future drift erode the boundary).

**Decision:** Elevate "the allowlist that defines an agent's permissions must live outside any agent-writable mount" to a named architectural principle, not just an emergent property of the current config layout.

**Rationale:** NanoClaw's external `~/.config/nanoclaw/mount-allowlist.json` is a deliberate defensive choice; making it a named principle prevents future drift.

**Source:** docs/archive/nanoclaw_research.md (Things to learn from NanoClaw)

**Status:** active

### D-93: Whizzard's container hardening is stronger than NanoClaw's, intentionally

**Type:** adapter

**Tags:** nanoclaw

**Door Type:** one-way (the hardening differential IS Whizzard's value-add over harness-native containment; weakening collapses the differentiator).

**Decision:** Keep `--cap-drop=ALL`, `--read-only`, `no-new-privileges`, tmpfs mounts, and profile-driven network policy as Whizzard differentiators; NanoClaw lacks these and the gap is real.

**Rationale:** Whizzard's value-add over harness-native containment is exactly this hardening layer.

**Source:** docs/archive/nanoclaw_research.md

**Status:** active

### D-94: Whizzard does not adopt NanoClaw's branch-based skill distribution

**Type:** adapter

**Tags:** nanoclaw

**Door Type:** two-way (distribution-model choice; could be revisited if a similar grafting model becomes attractive for some other reason).

**Decision:** If Whizzard ever supports skills/extensions, they will be installable artifacts, not git-branch grafts.

**Rationale:** NanoClaw's branch-grafting model fits their fork-and-customize UX; Whizzard's "policy layer that wraps any harness" UX needs a different distribution shape.

**Source:** docs/archive/nanoclaw_internals.md §9.2

**Status:** active

### D-95: Whizzard does not adopt NanoClaw's multi-channel adapter framework

**Type:** adapter

**Tags:** nanoclaw

**Door Type:** one-way (multi-channel is harness territory by design; building it in Whizzard would duplicate work the contained harness already does).

**Decision:** Multi-channel messaging (Discord/Telegram/Slack routing into agents) is harness territory, not Whizzard territory.

**Rationale:** Whizzard contains harnesses; harnesses bring their own multi-channel infrastructure.

**Source:** docs/archive/nanoclaw_internals.md §9.2

**Status:** active

### D-96: Whizzard does not adopt `bypassPermissions` posture for adapters

**Type:** adapter

**Tags:** nanoclaw

**Door Type:** one-way (adapter discipline; the bypass flag would erase the harness's own permission model, which Whizzard's outer gate is not a replacement for).

**Decision:** Adapters must not paper over a harness's own permission model with bypass flags.

**Rationale:** NanoClaw can use `bypassPermissions: true` because the container is its boundary. Whizzard wraps existing harnesses; harness-level permission posture is the harness's call.

**Source:** docs/archive/nanoclaw_internals.md §9.2

**Status:** active

### D-97: NanoClaw adapter is post-v1, not MVP

**Type:** adapter

**Tags:** nanoclaw

**Door Type:** two-way (sequencing choice; could be promoted into v1 if Hermes lands solidly and NanoClaw integration becomes a higher priority).

**Decision:** A NanoClaw harness adapter is on the long-term roadmap but not in MVP or v1 scope.

**Rationale:** NanoClaw's host-side architecture (router/delivery as host process) is more involved than Hermes; defer until Hermes adapter is solid.

**Source:** docs/archive/nanoclaw_research.md (How NanoClaw fits as a harness)

**Status:** superseded by D-155 (which commits NanoClaw to v1.0 specifically, rather than vague "post-v1").

### D-98: OneCLI vault as v1-must-have (promoted from post-MVP backlog)

**Type:** adapter

**Tags:** nanoclaw

**Door Type:** two-way (was post-MVP, promoted to v1-must-have based on NanoClaw's production validation; could revert if priority shifts, though the validation argument would still apply).

**Decision:** Vault-mediated credentials are promoted from "post-MVP backlog" to "v1-must-have" based on NanoClaw's production validation.

**Rationale:** Production-proven pattern; the gap between env-var injection (MVP) and vault-mediated (v1) is the difference between "credentials in process env" and "agent literally cannot exfiltrate."

**Source:** docs/session_handoff.md; docs/archive/nanoclaw_research.md (Bottom line); docs/control_surface.md (§5)

**Status:** active

---

### D-99: MVP definition is "9 capabilities" (numbered list in mvp_build_plan)

**Type:** scope

**Door Type:** two-way (the 9-capability list is the touchstone; D-99's Notes already document scope expansion under D-103/104/76 — the list can keep evolving).

**Decision:** The MVP is operational when it can do nine specified things — generic shell launch, named mounts, ro/rw modes, profile-driven network, safety policy, dry-run, session logs, generic adapter, image management.

**Rationale:** Concrete acceptance test; the MVP succeeds when it becomes a daily-driver permission harness.

**Source:** docs/mvp_build_plan.md (MVP Definition)

**Status:** active

**Notes:** The stage list expanded after the 2026-05-09 framing change (D-103, D-104, D-76); the original 9-capability statement remains the touchstone.

### D-100: MVP build order is Stage 1 → Stage 11

**Type:** scope

**Door Type:** two-way (already superseded by D-138 — proves the door swings).

**Decision:** Stages run in order: shell, mounts, profiles, dry-run, logging, safety, generic adapter, Hermes, MCP read-only, presets, image management.

**Rationale:** Each stage builds on the previous; rearranging would force out-of-order dependencies.

**Source:** docs/mvp_build_plan.md (Build Order); docs/control_surface.md (renumbering)

**Status:** superseded by D-138

### D-101: MVP is a personal daily-driver milestone, not the OSS-launch milestone

**Type:** scope

**Door Type:** two-way (milestone-naming choice; conflating MVP with OSS-launch is conceptually possible but tends to bloat MVP or rush OSS — current separation is intentional).

**Decision:** The current MVP is a local-testing milestone for personal use. OSS-launch is a later, broader milestone.

**Rationale:** Conflating the two would either bloat MVP or rush an OSS release without enough operational evidence.

**Source:** docs/control_surface.md (Recent framing decisions, conversation 2026-05-09)

**Status:** active

### D-102: Day-1 OSS value prop is the B+D combination

**Type:** scope

**Door Type:** two-way (positioning frame; B+D is the current narrative — alternatives are conceivable, though this one explicitly justified pulling presets into MVP per D-103).

**Decision:** OSS positioning is "B" (define what your agent can touch, see, and do by shaping the environment, not approving every action) plus "D" (switch between named, scoped agent contexts faster than you can type the docker command).

**Rationale:** The combined frame is sharper than either alone; D specifically pulls preset support up into MVP scope.

**Source:** docs/control_surface.md (Recent framing decisions, conversation 2026-05-09)

**Status:** active

### D-103: Presets pulled into MVP as Stage 10

**Type:** scope

**Door Type:** two-way (presets-in-MVP was a deliberate pull; could retreat to post-MVP if the B+D framing weakens, though doing so would weaken the value prop too).

**Decision:** Presets (named bundles of profile + harness + mounts + duration + env) are now MVP scope as Stage 10, not post-MVP §7.

**Rationale:** D in the B+D value prop is delivered through preset-driven switching; without presets, "switch contexts faster than typing docker" is hollow.

**Source:** docs/control_surface.md (framing decisions, conversation 2026-05-09)

**Status:** active

### D-104: Whiz MCP server (read-only subset) pulled into MVP as Stage 9

**Type:** scope

**Door Type:** two-way (read-only MCP-in-MVP was deliberate; could defer to post-MVP if the cooperation-layer story doesn't need day-one validation).

**Decision:** A read-only Whiz MCP surface — `whiz_status`, `whiz_audit_self`, `whiz_emit_event`, `whiz_list_presets` — is MVP scope as Stage 9.

**Rationale:** Cooperation layer is a first-class part of the design; the read-only subset has no enforcement implications and lands cheaply.

**Source:** docs/control_surface.md (framing decisions, conversation 2026-05-09); docs/control_surface.md §13

**Status:** active

### D-105: Explicit non-MVP features (named list)

**Type:** scope

**Door Type:** two-way (this is the negative-scope list; items can be pulled into MVP as evidence justifies — D-137 already did this for the personal-use threshold).

**Decision:** GUI, Discord control plane, MCP gateway adapter, per-agent orchestration, breaker engine, shadow-home system, file-tree mount picker, AI risk scoring, and VM orchestration are explicitly out of MVP.

**Rationale:** Keeps MVP narrow; each item has its own post-MVP home.

**Source:** docs/mvp_build_plan.md (Explicit Non-MVP Features)

**Status:** active

### D-106: MVP design discipline — useful, understandable, secure-enough, low-friction, extensible

**Type:** scope

**Door Type:** two-way (the priority order is the discipline; could be reordered or extended, but the 'secure-enough not maximally-secure' clause is the load-bearing one).

**Decision:** The MVP success criteria are these five qualities, in that priority order.

**Rationale:** Forces narrow scope; "secure enough" is deliberate (vs. "maximally secure") to keep the MVP shippable.

**Source:** docs/mvp_build_plan.md (Design Discipline)

**Status:** active

### D-107: Dry-run preview must include duration

**Type:** scope

**Door Type:** two-way (could remove duration from the preview if it became obvious elsewhere; explicit display reinforces D-13's enforced-not-advisory framing).

**Decision:** The dry-run output must explicitly show the effective session duration limit.

**Rationale:** Time-bounded sessions are a primary safety primitive; the user has to see when termination will hit before they launch.

**Source:** docs/mvp_build_plan.md (Stage 4)

**Status:** active

### D-108: Banner shows profile, network, duration, broad-mount override, image, mounts, harness, session ID

**Type:** scope

**Door Type:** two-way (the banner field set is enumerated; can extend to surface more capability info — D-89/D-90 already added platforms and approval-mode lines).

**Decision:** The pre-launch and dry-run banner enumerates these fields.

**Rationale:** "What you see is what is granted" — visible permissions are the affordance.

**Source:** docs/vision_and_strategy.md (UX / Mental Model); docs/stage_validation.md (multiple stages)

**Status:** active

### D-137: All five personal-use candidate items pulled into MVP

**Type:** scope

**Door Type:** two-way (the 'all five' choice was deliberate to clear D-101's personal-use threshold; could be revisited if effort estimates blow up dramatically before each lands).

**Decision:** All five additional control items surfaced as MVP candidates — mid-session stop+restart with capability adjustment, request-side MCP tools, OneCLI vault integration, Discord/mobile control plane, idle timeout — are pulled into MVP scope.

**Rationale:** MVP must clear the personal daily-driver threshold (D-101); these are the items below that threshold. Rather than rank-order them, taking all of them in MVP makes the milestone fully usable for personal daily use.

**Source:** conversation 2026-05-09

**Status:** active; resolves D-130

### D-138: MVP build order is extended to 17 stages

**Type:** scope

**Door Type:** two-way (already superseded by D-143 — proves the door swings; stage numbering shifts as scope evolves).

**Decision:** MVP build order is Stage 1 → Stage 17. New stages relative to D-100: Stage 11 = OneCLI vault integration, Stage 12 = stop+restart mechanism + local TTY approval flow, Stage 13 = Whiz MCP server request-side tools, Stage 14 = duration + idle timeout enforcement, Stage 15 = Discord control plane (read-only), Stage 16 = Discord control plane (write + approve flow), Stage 17 = image management (was Stage 11; defers to last).

**Rationale:** Dependency-respecting ordering for the expanded MVP. Vault lands at Stage 11 because it's the strongest single argument for Whizzard's security thesis. Stop+restart precedes request-side MCP because the tools depend on the mechanism. Discord splits into read-only and write/approve stages so the simpler read piece can validate the bot framework before the higher-risk approval flow lands. Image management defers to the end as polish-relative-to-functionality.

**Source:** conversation 2026-05-09

**Status:** superseded by D-143

### D-139: Discord control plane write + approve flow is in MVP

**Type:** scope

**Door Type:** two-way (read-only-first was a staging suggestion within Channel B; pulling full write/approve into MVP is reversible if Stage 16 effort overruns).

**Decision:** The Discord control plane write/approve flow — start, stop, extend, switch profile, approve mount addition, with single-use time-bounded tokens validated against the initiator's Discord ID — is in MVP scope as Stage 16.

**Rationale:** The original "read-only first" framing was a staging suggestion within Channel B (the Whiz control plane), not a permanent constraint. Bryan wants full Discord-mediated session management at MVP, not deferred to v1. Promotes part of post_mvp_spec.md §2 into MVP; the rest of §2 remains v1.

**Source:** conversation 2026-05-09

**Status:** active

### D-140: MVP capability set is extended beyond the foundational nine

**Type:** scope

**Door Type:** two-way (the original 9-capability list (D-99) remains the touchstone; the extension is documented and can grow further or shrink as scope dictates).

**Decision:** MVP capability set is the original 9 capabilities (D-99) plus: mid-session capability adjustment via stop+restart, agent-facing MCP cooperation surface (read-only and request-side), OneCLI vault credential isolation, Discord/mobile control plane (read + write/approve), idle timeout enforcement.

**Rationale:** D-101 established that MVP is the personal daily-driver threshold; D-137 commits the additional items. This decision is the named extension to the original capability list.

**Source:** conversation 2026-05-09

**Status:** active; extends D-99

### D-141: Whizzard adopts a hybrid generalization path — agent-focused at MVP, explicit "general" mode at OSS-launch

**Type:** scope

**Door Type:** two-way (chose option C from a three-way; could pivot to option A (stay agent-focused) or option B (general from start) if OSS-launch evidence demands it).

**Decision:** Whizzard's MVP remains agent-focused (Hermes/NanoClaw harness adapters anchor the audience). At OSS-launch, an explicit "general process" mode is added: `harnesses.json` schema accepts any executable, presets shaped for non-agent OSS tools (e.g., "try-untrusted-cli"), marketing positions both agent and general use cases. The architectural foundation already supports this — most stages are harness-neutral; only the Whiz MCP cooperation layer (Stages 9, 14) is agent-specific.

**Rationale:** Three options were considered: A) stay agent-focused with sibling project later, B) general from the start, C) hybrid — agent at MVP, general at OSS-launch. C wins because it preserves MVP focus (sharp use cases drive design) while leaving the broader OSS-tool audience addressable when polish lands. B risks losing focus pre-MVP; A leaves a real gap on the table — there's no good cross-platform low-friction security-shaped container layer for individual developers (firejail/bwrap are Linux-only and config-tedious; Docker alone has no policy/preset/audit layering; devcontainers and Distrobox aren't security-shaped).

**Source:** conversation 2026-05-09

**Status:** active

### D-142: Slash command surface — A, B, C in MVP; D post-MVP

**Type:** scope

**Door Type:** two-way (D was deferred for design-after-experience reasons; could be promoted if the adapter contract requirements firm up sooner — Stage 8 was designed with D's requirements in mind to allow this).

**Decision:** Four slash-command surfaces were considered:

- **A. Host CLI brevity** (`whiz` alias alongside `whizzard`, subcommand shortcuts like `whiz r` / `whiz s` / `whiz p`, smart defaults such as "launch most recent preset" with no args) — in MVP, folded into Stage 10 alongside presets
- **B. Discord and other gateway slash commands** (`/whizzard status`, `/whizzard start`, `/whizzard extend`, etc.) — in MVP at Stages 16–17
- **C. Host-side Claude Code slash commands** (`.claude/skills/` bundle for `/whiz launch`, `/whiz status`, `/whiz adjust`, etc., wrapping the underlying CLI) — in MVP as new Stage 11
- **D. In-agent-chat slash command interception by harness adapter** (user types `/whiz extend 30m` inside their Discord conversation with the agent; adapter intercepts before the agent sees it; forwards to Whiz host-side) — post-MVP

**Rationale:** A, B, C are small, near-orthogonal, and directly reduce daily-driver friction. D is more architecturally consequential — it requires a new adapter contract method (input-side intercept hook), transport-level user authentication, and opt-in design — and benefits from being designed after the Hermes adapter (Stage 8) and Discord control plane (Stages 16–17) are stable. Stage 8 will be designed with D's contract requirement in mind so it's not retrofitted.

**Source:** conversation 2026-05-09

**Status:** active

### D-143: MVP build order extended to 18 stages

**Type:** scope

**Door Type:** two-way (stage count shifts as scope evolves; D-100 → D-138 → D-143 is the visible history of this door swinging).

**Decision:** MVP build order is now Stage 1 → Stage 18. Stage 10 expands to include CLI brevity (D-142 A); new Stage 11 is Host-side Claude Code Slash Commands (D-142 C); subsequent stages renumber by +1: Stage 12 = OneCLI vault (was 11), Stage 13 = stop+restart + local TTY approval (was 12), Stage 14 = Whiz MCP request-side (was 13), Stage 15 = duration + idle timeout (was 14), Stage 16 = Discord control plane read-only (was 15), Stage 17 = Discord control plane write+approve (was 16), Stage 18 = image management (was 17).

**Rationale:** Slash command surface decisions per D-142. CLI brevity (A) is pure UX with the same theme as presets — folding into Stage 10 keeps stage count from inflating without sacrificing clarity. Claude Code slash commands (C) merit their own stage because the deliverable is a distinct `.claude/skills/` bundle with its own test surface. Image management still defers to last (D-138 rationale unchanged).

**Source:** conversation 2026-05-09

**Status:** active; supersedes D-138

### D-144: Consolidate naming to single "Whizzard" — drop the Airlock/Whizzard split

**Type:** scope

**Door Type:** two-way (verbal framing rather than architectural; the layering survived consolidation — only the user-facing component name went away — could be split again with a doc + UX refresh).

**Decision:** Drop the two-component naming split. The whole project is named "Whizzard" — orchestrator, policy engine, and containment layer all under one name. The "Airlock" sub-component name is retired. Architecture layers within Whizzard remain (Whizzard Core / Harness Adapter / Execution Backend), but they're internal layering rather than separately-named user-facing components. "Whizzard" itself remains a working placeholder; long-term name TBD.

**Rationale:** The Airlock/Whizzard split was elegant verbally ("Whizzard operates / Airlock governs") but added cognitive load with no benefit — both names mapped to the same codebase, the same `.whizzard` config dir, the same CLI binary. Users had to learn two names to describe one thing. Consolidation simplifies the mental model. The architectural separation between core / adapter / backend is preserved as internal layering inside the architecture doc.

**Source:** conversation 2026-05-09

**Status:** active; supersedes D-04, D-05, partially D-19

### D-145: GitHub repository will rename from `basicagentauth` to `whizzard`

**Type:** scope

**Door Type:** two-way (GitHub repo renames are non-destructive — they leave forwarding aliases; could be renamed again if 'Whizzard' itself gets replaced).

**Decision:** The GitHub repository will be renamed from the placeholder `basicagentauth` to `whizzard`. Rename happens between Claude sessions (executed by the user via `gh repo rename whizzard` from the local working dir, plus `git remote set-url origin git@github.com:BuckG71/whizzard.git`).

**Rationale:** Consolidate naming with D-144. The placeholder repo name added confusion when discussing the project. "Whizzard" is the working name across docs, code, and config; the repo name should match.

**Source:** conversation 2026-05-09

**Status:** active; supersedes D-01

### D-146: Local working directory rename `airlock-warlock` → `whizzard` happens between sessions

**Type:** scope

**Door Type:** two-way (local directory rename is between-session-only per D-03; reversible at any future session boundary).

**Decision:** The local working directory at `/Users/bg1971/ai-sandbox/airlock-warlock` will be renamed to `/Users/bg1971/ai-sandbox/whizzard`. The rename is executed between Claude Code sessions (not mid-session), to avoid breaking the current session's working-directory binding. Steps: end current Claude session; remove the `crazy-ellis-b21769` worktree (`git worktree remove`); rename the parent directory; start a new Claude Code session pointed at the new path.

**Rationale:** D-03 prohibited mid-session rename for binding-stability reasons; that constraint doesn't apply between sessions. Consolidates the local layout with D-144 and D-145. After rename, Claude Code's auto-memory will live at a new encoded path (`-Users-bg1971-ai-sandbox-whizzard/`); the user must copy memory files from the old path or recreate them.

**Source:** conversation 2026-05-09

**Status:** active; supersedes D-03

---

### D-109: v1.0 has eight named goals

**Type:** scope

**Door Type:** two-way (the v1 goal list is a planning anchor; the Notes already document tension where MVP scope has absorbed some v1 items — the list will keep evolving).

**Decision:** v1.0 goals are: per-agent capability scoping, Discord/mobile control plane, multi-harness rollout, MCP gateway direction, session duration as enforced primitive, image management at runtime, quick-access presets, repo onboarding.

**Rationale:** Stable list anchors post-MVP planning.

**Source:** docs/post_mvp_spec.md (v1.0 Primary Goals)

**Status:** active

**Notes:** Item 7 (presets) and parts of item 5/6 are now MVP scope post-2026-05-09 framing changes (D-103, D-104). The v1.0 list still names them as v1 goals; the tension is documented but not resolved in the source docs.

### D-110: Per-agent policy with local approval before Discord exists

**Type:** scope

**Door Type:** two-way (sequencing-of-deliverables choice; could be relaxed if Discord-only approval becomes safe enough on its own, but the local-first stance protects v1 build-phase usability).

**Decision:** `approval_required: true` on agent policies must have a local terminal-prompt approval path that exists before any Discord bot ships. `--pre-approve` flag for scripted contexts.

**Rationale:** Without local approval, the policy setting is unusable during the v1 build phase; Discord approval is additive, not foundational.

**Source:** docs/post_mvp_spec.md §1 (Approval Flow — Local Path)

**Status:** active

### D-111: Discord control bot is policy-restricted

**Type:** scope

**Door Type:** one-way (the restricted-control-plane stance is what makes the bot safe to expose; widening it would change what the bot is).

**Decision:** The Discord bot may start/stop/revoke sessions, request approvals, display status/logs, switch profiles, launch presets — but may NOT execute arbitrary shell, mount arbitrary paths, grant unrestricted permissions, or expose secrets.

**Rationale:** Bot is a control plane, not an execution path; treating it as anything else widens the attack surface.

**Source:** docs/post_mvp_spec.md §2 (Control Plane Responsibilities)

**Status:** active

### D-112: Discord prefers slash commands over `!` legacy commands

**Type:** scope

**Door Type:** two-way (syntax preference; could fall back to legacy `!` if slash commands hit Discord API friction, though slash is the modern path).

**Decision:** Slash commands are the preferred Discord syntax; legacy `!` is optional support.

**Rationale:** Structured inputs, lower parser surface, mobile-friendly, autocomplete; slash commands are the platform's native gesture.

**Source:** docs/post_mvp_spec.md §2 (Discord Command Model)

**Status:** active

### D-113: Discord approval tokens are single-use, time-bounded, identity-bound

**Type:** scope

**Door Type:** one-way (all three properties — single-use, time-bound, identity-bound — close specific abuse vectors; relaxing any one re-opens a path).

**Decision:** "approve NNNN" tokens must be single-use, expire within ~5 minutes, and only accepted from the Discord user who initiated the request.

**Rationale:** Prevents token replay and prevents other server members from approving on someone else's behalf.

**Source:** docs/post_mvp_spec.md §2 (Approval Security Requirements)

**Status:** active

### D-114: Duration hierarchy is session-flag → preset → agent-policy → profile-default

**Type:** scope

**Door Type:** two-way (the resolution order is the design choice; could be reordered, though current order matches the 'specific overrides general' convention).

**Decision:** Effective duration is resolved in this priority order, with "no duration" meaning unlimited (logged as such).

**Rationale:** Allows fine-grained override at the moment of launch while preserving sane policy defaults.

**Source:** docs/post_mvp_spec.md §5 (Duration Hierarchy)

**Status:** active

### D-115: Adapter `pre_terminate` hook ships in v1

**Type:** scope

**Door Type:** two-way (could pull into MVP if a harness needs structured state checkpointing earlier; v1 placement is the current best estimate of when it's needed).

**Decision:** v1 adds an adapter-level `pre_terminate` callback distinct from `wrap_up`, allowing structured state checkpointing (e.g., serializing conversation history).

**Rationale:** Wrap-up is harness-native shutdown; pre-terminate is for cross-session continuity. Different concerns.

**Source:** docs/post_mvp_spec.md §5 (v1 Additions to Duration Handling)

**Status:** active

### D-116: Full session checkpointing (serialize/resume) is v2

**Type:** scope

**Door Type:** two-way (could pull into v1 if the use case becomes pressing; checkpointing scope tends to slide as harness adapters mature).

**Decision:** v1 ships only the hooks for checkpointing; full serialize-and-resume across sessions is v2.

**Rationale:** Hook surface is the small piece; the actual serialize/resume is a much larger commitment.

**Source:** docs/post_mvp_spec.md §5

**Status:** active

### D-117: Quick-access presets are a security feature, not just usability

**Type:** scope

**Door Type:** two-way (framing decision; the security argument is the rationale, but the implementation is the same either way — the frame can shift without code changes).

**Decision:** Frame presets as security infrastructure, because secure workflows fail when they are too painful.

**Rationale:** If governance is harder than the bypass, users bypass; low-friction safe paths are part of the safety architecture.

**Source:** docs/post_mvp_spec.md (Operational Philosophy)

**Status:** active

### D-118: Repo onboarding (docs + setup script) is part of v1, not optional polish

**Type:** scope

**Door Type:** two-way (could defer onboarding polish to v1.x as a separate release; current scoping ties it to v1 because misconfiguration is a security failure).

**Decision:** v1 ships a getting-started guide, setup script/Makefile target, worked example, profile docs, and a "what is and isn't protected" note.

**Rationale:** Misconfiguration weakens containment; bad setup docs are a security failure, not a docs failure. The setup path should be opinionated.

**Source:** docs/post_mvp_spec.md §8

**Status:** active

### D-119: Phase 3 Breaker uses deterministic heuristics initially, not AI scoring

**Type:** scope

**Door Type:** two-way (current implementation is deterministic for debuggability; AI scoring stays explicitly out of scope but could be added as a later layer if heuristics prove insufficient).

**Decision:** Initial Breaker implementation uses deterministic heuristics for behavioral interruption; autonomous AI behavioral scoring is explicitly out of initial scope.

**Rationale:** Determinism is debuggable and trustworthy; AI scoring introduces a second AI system inside the safety boundary.

**Source:** docs/vision_and_strategy.md (Phase 3 Breaker, Initial implementation recommendation)

**Status:** active

### D-120: Phase 4 Shadow Home does NOT prove safety

**Type:** scope

**Door Type:** two-way (framing of Phase 4 capability; could escalate the safety claim if implementation evidence supports it, but the current under-claim is intentional).

**Decision:** Frame the Shadow Home / decoy environment as a behavior-observation tool, not a safety proof. A malicious system could behave benignly during testing.

**Rationale:** Setting expectations correctly; over-claiming on shadow execution would mislead users about residual risk.

**Source:** docs/vision_and_strategy.md (Phase 4, Important Limitation)

**Status:** active

### D-121: Mount-picker / file-tree browser is post-v1 backlog and human-only

**Type:** scope

**Door Type:** two-way for the picker itself; one-way for the agent-blind-to-host-tree principle that backs it (the picker is opt-in polish, the principle is load-bearing).

**Decision:** A graphical mount picker is post-v1; agents themselves never browse the host filesystem tree.

**Rationale:** Agent-driven filesystem browsing leaks the structure agents are meant to be blind to.

**Source:** docs/post_mvp_spec.md (Mount Picker / File Tree Browser)

**Status:** active

### D-122: Session replay / audit visualization is post-v1

**Type:** scope

**Door Type:** two-way (polish item; the JSONL log is the substrate, visualization can ship anytime).

**Decision:** Visual session replay (commands, mounts, network, approvals, breaker events) is post-v1 backlog.

**Rationale:** JSONL is sufficient for daily use; visualization is polish.

**Source:** docs/post_mvp_spec.md (Session Replay)

**Status:** active

### D-123: AppArmor/SELinux, time-of-day windows, bandwidth caps, multi-party approval, identity-provider integrations are deprioritized indefinitely

**Type:** scope

**Door Type:** two-way (deprioritized for the current audience; could be added as enterprise-facing features if the target audience expands).

**Decision:** These items appear in the control surface but are explicitly deprioritized.

**Rationale:** Enterprise-shaped; OSS Whizzard targets individual / security-conscious developer personas.

**Source:** docs/control_surface.md (What's explicitly out of scope)

**Status:** active

---

### D-124: MVP focus rule — push back on doc tweaks until MVP is operational

**Type:** process

**Door Type:** two-way (process discipline tied to MVP focus; lifts once MVP is operational, by definition).

**Decision:** Until MVP is operational, the assistant pushes back on documentation-only edits and steers toward implementation. Backlog additions are an explicit exception.

**Rationale:** Doc churn substitutes for shipping; the rule keeps focus on the implementation that proves the thesis.

**Source:** /Users/bg1971/.claude/projects/-Users-bg1971-ai-sandbox-airlock-warlock/memory/feedback_mvp_focus.md (referenced from auto-memory)

**Status:** active

### D-125: One topic at a time

**Type:** process

**Door Type:** two-way (working-style preference; can be relaxed if the conversation mode shifts, but the user has been consistent on this).

**Decision:** Surfacing a multi-item list is fine, but discuss and resolve them one at a time before moving on.

**Rationale:** Avoids parallel half-resolved threads; matches the user's working style.

**Source:** memory/feedback_one_at_a_time.md (referenced from auto-memory)

**Status:** active

### D-126: Don't push to close items

**Type:** process

**Door Type:** two-way (interaction discipline; specific to the user's preferred conversational rhythm).

**Decision:** Stop ending responses with "ready to close X?" prompts; topics close naturally when both parties feel done.

**Rationale:** Closing prompts add friction without speeding resolution.

**Source:** memory/feedback_dont_push_to_close.md (referenced from auto-memory)

**Status:** active

### D-127: Session-handoff doc convention

**Type:** process

**Door Type:** two-way (session-handoff conventions have evolved through D-149 → D-150; the door is observably swinging).

**Decision:** When approaching the context-window limit, write a comprehensive handoff document (`docs/session_handoff.md`) including verbatim recent turns so a fresh session can resume without re-deriving context.

**Rationale:** Cross-session continuity for a long-running design conversation.

**Source:** docs/session_handoff.md (the document itself, plus conversation 2026-05-08 framing)

**Status:** active

### D-128: Plan-vs-task distinction (plan = stable; task = in-flight)

**Type:** process

**Door Type:** two-way (working convention; the source-docs-vs-conversation distinction could be reorganized if doc tooling changes).

**Decision:** Source docs (plans) remain authoritative for narrative and rationale; in-flight conversation captures the moment-to-moment decisions, which are then promoted to docs only when stable.

**Rationale:** Avoids constant doc churn; lets conversation move quickly without losing decisions.

**Source:** docs/control_surface.md (Recent framing decisions); docs/decisions.md (this file's preamble)

**Status:** active

### D-129: Decisions are append-only with status updates, not deletion

**Type:** process

**Door Type:** one-way (append-only with stable cross-references is what makes 'D-NN superseded by D-MM' citations safe; deletion would break links across docs and code).

**Decision:** This decisions document is append-only; superseded entries stay in place with their status changed, not removed.

**Rationale:** Stable cross-references; lets future work cite "D-NN as superseded by D-MM" without breaking links.

**Source:** docs/decisions.md (this file's preamble); conversation 2026-05-09

**Status:** active

### D-147: Merge doc-only commits into main immediately

**Type:** process

**Door Type:** two-way (workflow choice; could move to PR-based review if the project grows multiple maintainers, but currently the user develops solo on main).

**Decision:** Doc-only commits (anything touching only `docs/**`, `README.md`, comment-only changes) are fast-forward merged into `main` immediately after commit, without separate confirmation. Code changes still pause for explicit confirmation. Mixed commits follow the code-change path.

**Rationale:** Doc changes are reversible via `git revert`. Holding them adds friction without proportional safety benefit. The user develops directly on main; PR ceremony is not the workflow.

**Source:** memory/feedback_merge_doc_changes.md; conversation 2026-05-09

**Status:** active

### D-148: Pause at UX-shaped stages to design before coding

**Type:** process

**Door Type:** two-way (process commitment for specific stage types; can be relaxed if the affordances become well-rehearsed, but currently they're each first-time UX decisions).

**Decision:** Stages whose primary deliverable is a user-facing surface — profiles, presets, CLI shortcuts, slash commands, Discord control plane — open with a design conversation before implementation. List candidate affordances, rank by frequency × friction-saved, cut anything below the bar, confirm the slate before code lands. Currently applies to MVP Stages 10 (Presets + CLI ergonomics), 11 (Claude Code slash commands), 16, 17 (Discord), and any future stage introducing user-facing surfaces.

**Rationale:** UX surfaces compound. Bad shortcuts become muscle memory; missing presets become daily papercuts. Once shipped, these are hard to change without breaking habits. Friction at these surfaces undermines the project's core value prop. Throughput on these stages matters less than getting affordances right.

**Source:** memory/feedback_ux_pause_at_design_stages.md; conversation 2026-05-09

**Status:** active

### D-149: `session_handoff.md` is overwriteable, not append-only

**Type:** process

**Door Type:** two-way (already superseded by D-150 — proves the door swings; conventions for the handoff file have evolved as the file's role evolved).

**Decision:** `docs/session_handoff.md` captures the current snapshot needed to start a fresh Claude Code session and is rewritten end-to-end each session. It is not a log; do not append. Prior versions are recoverable via `git show <hash>:docs/session_handoff.md` if a rollback is ever needed. Other docs (notably `decisions.md`) remain append-only — this convention applies only to the handoff file.

**Rationale:** A growing handoff file is a worse handoff: stale guidance accumulates, the new-session instructions get buried, and the document loses its "read this first" character. Git already preserves history; the working file should optimize for the next session reading it cold, not for completeness across all sessions. Decisions and validation checklists live in their own append-only docs, so historical context is not lost by overwriting the handoff.

**Source:** docs/session_handoff.md (D-149-pending note); conversation 2026-05-09

**Status:** superseded by D-150

### D-150: `HANDOFF.md` is append-only — supersedes D-149

**Type:** process

**Door Type:** two-way (could revert to overwriteable if entries grow too long to keep accumulated; current 250-word target per entry makes accumulation viable).

**Decision:** The handoff doc, renamed `docs/HANDOFF.md`, is append-only. New entries go at the top; prior entries are preserved verbatim. Each entry follows the structure defined by the `/handoff` skill (Goal / Active task / Tried & rejected / Resume protocol) with a target length under 250 words.

**Rationale:** D-149's overwriteable framing was correct for the prior `session_handoff.md` format, which captured comprehensive narrative context (~3000 words) where accumulated entries would have bloated the file unusably. The new HANDOFF format under the `/handoff` skill captures different and much shorter content (~150–250 words/entry), so the bloat concern that justified overwrite no longer applies. Append-only enables cross-session decision archaeology and matches the behavior of every other long-lived doc in the project (`DECISIONS.md`, `STAGE_VALIDATION.md`).

**Source:** conversation 2026-05-09; `/handoff` skill spec

**Status:** active

### D-151: Markdown filenames in this project are uppercase

**Type:** process

**Door Type:** two-way (filename convention; could revert to mixed-case with a rename pass, though current state has a pending bulk-rename to align legacy lowercase files).

**Decision:** All markdown filenames in the Whizzard repository are uppercase by convention. Examples: `README.md`, `HANDOFF.md`, `DECISIONS.md`, `ARCHITECTURE.md`, `MVP_BUILD_PLAN.md`. Underscores separate words within the name. Bulk rename of existing lowercase files and the corresponding cross-reference updates are tracked as a separate cleanup commit.

**Rationale:** Consistency with the common GitHub convention for top-level repo docs (`README`, `CONTRIBUTING`, `LICENSE`, `CHANGELOG`), extended uniformly to all project markdown to remove case-recall friction when typing references. The pattern is also visually distinctive against code files in directory listings.

**Source:** conversation 2026-05-09

**Status:** active

**Notes:** Bulk rename pending as a separate commit; cross-references in code/docs must be updated atomically with the rename to avoid broken links.

### D-152: Defense-in-depth against bundled-test-file Skill attacks

**Type:** process

**Door Type:** two-way for specific defenses (the test-runner config and review steps are tunable); one-way for the underlying principle that the developer toolchain is part of the attack surface.

**Decision:** (1) `pyproject.toml` declares `norecursedirs = [".agents", ".claude", ".cursor"]` in addition to `testpaths = ["tests"]`, so pytest cannot auto-discover test files inside skill / agent / IDE state directories even if `testpaths` is later broadened. (2) Any Anthropic Skills (or equivalent agent-extension bundles) installed into this repository must be pinned to a specific commit hash, not a branch. (3) Before merging any commit that introduces files under `.agents/`, `.claude/skills/`, or `.cursor/skills/`, reviewers must check for the file shapes that ride the developer-toolchain execution surface — `*.test.*`, `*.spec.*`, `conftest.py`, `__tests__/`, `*.config.*` — and treat any presence as a finding requiring justification.

**Rationale:** Per Gecko Security's disclosure (VentureBeat, 2026-05-09), public Anthropic Skill scanners inspect the agent-execution surface (`SKILL.md`, agent-invoked scripts) but not the developer-toolchain surface (test files auto-discovered by Jest/Vitest/pytest with full local permissions). Whizzard's structural containment addresses the agent-execution side but does not bound the developer toolchain — `npm test` / `pytest` runs on the host, not inside a cell. The MVP scope does not extend to sandboxing developer tooling, so we defend project hygiene through configuration and review. Audit at decision time: `.claude/` contained only `.DS_Store` and `settings.local.json`; `.agents/` and `.cursor/` did not exist; no findings.

**Source:** VentureBeat 2026-05-09 (Gecko Security disclosure on Anthropic Skill scanner blind spot); conversation 2026-05-09

**Status:** active

**Notes:** `.agents/` is *not* added to `.gitignore` because Skills are intended to be committed and shared per upstream convention; the defense lives in test-runner config and pre-merge review.

### D-153: Harness-specific identifiers appear only in adapter modules

**Type:** architecture

**Door Type:** one-way (harness-isolation rule; reversing would require re-introducing harness identifiers into core).

**Decision:** Harness-specific paths, filenames, environment variable names, schema field names, and CLI flag names appear only in adapter modules (`whizzard/adapters/<harness>.py`) and the corresponding adapter subcommand surface in `whizzard/cli.py`. Whizzard's core modules — `config.py`, `docker_cmd.py`, `mounts.py`, `safety.py`, `session_log.py`, `harness_config.py` — must not reference Hermes/OpenClaw/etc.-specific identifiers (examples: `config.yaml`, `state.db`, `gateway.lock`, `HERMES_HOME`, `DISCORD_BOT_TOKEN`, `--platforms`). Permitted core knowledge: the harness *type* names registered in `harnesses.json` (currently `"shell"` and `"agent"` per D-34) and the adapter Protocol method names (D-28). Those are the abstraction surface; everything below them is adapter-private.

**Rationale:** D-10 ("Whizzard core stays harness-neutral") is a stance; this decision makes it a reviewable, lint-checkable rule. Without an explicit isolation rule, harness-specific identifiers drift into core as convenient shortcuts ("just read `config.yaml` here, we only have Hermes anyway"), and reverting that drift later becomes a real refactor. Naming the files subject to the rule — and the categories of identifier the rule covers — keeps the adapter pattern load-bearing for the lifetime of the project, including future post-MVP adapters (OpenClaw, NanoClaw, etc.). The adapter Protocol (D-28) is the contract between core and adapters; this is the rule that protects the contract from erosion.

**Source:** conversation 2026-05-14 (during D-89 resolution; Bryan's question on whether config.yaml dependency violates D-10).

**Status:** active

**Notes:** Enforcement is per-PR review for MVP. A lint check (grep-based) is plausible post-MVP if drift becomes a recurring issue.

### D-154: Upstream-change detection and adapter maintenance pipeline

**Type:** process

**Door Type:** two-way (the pipeline shape is described but not yet built; could be adjusted as adapter-rot patterns become observed; the human-in-loop boundary on fix/ship is the load-bearing piece, the rest is implementation detail).

**Decision:** Each Whizzard adapter ships with an automated upstream-change-detection pipeline that follows a "detect/test/report (automated) → fix/ship (human-in-loop)" pattern:

1. **Detection (automated, cron-scheduled).** A scheduled CI workflow (e.g., GitHub Actions daily) per adapter polls the upstream harness: latest release tag and latest HEAD of upstream main. Both are tracked but treated differently — releases are the ship signal, main is the early-warning signal. Pre-release / beta tracking is opt-in per adapter.
2. **Testing (automated).** When a new upstream version is detected, the pipeline spins up an ephemeral test harness in CI: a fresh container with Whizzard + adapter + the new upstream version installed, then runs the adapter test suite. The substrate is layered:
   - **Smoke** — does the adapter import and instantiate without error?
   - **Unit** — do adapter Protocol methods return the expected shapes (`start_command`, `container_env`, `wrap_up`, etc.)?
   - **Integration** — can a container be started, a one-shot prompt run, and a clean shutdown achieved?

   Smoke + unit are required; integration is required for at least one mode (interactive is cheaper to substrate than gateway, which needs platform credentials).
3. **Reporting (automated).**
   - **Tests pass clean:** open a PR that bumps the adapter's tested-against-version range in `pyproject.toml`. Auto-merge is permitted for version-range-only changes (no code diff).
   - **Tests fail:** open an issue or draft PR with the failure log, the upstream commit log since the last passing version, and any obvious suspect (renamed symbol, removed function, schema-field change). The report must be triage-ready — a human shouldn't have to re-do detective work the bot could have done.
4. **Fixing (human, possibly AI-assisted).** A maintainer reads the failure report and writes the patch — Claude, Codex, or similar tooling may assist, but the patch goes through normal PR review. The pipeline does **not** auto-generate or auto-merge code changes that touch adapter logic. This boundary is load-bearing.
5. **Shipping (gated by tag).** Adapter releases are tagged by humans; CI publishes on tag. The only auto-ship case is the version-range-only PR (no code change), and even that is opt-in once the signal is trusted (default: human-gated for the first ~6 months per adapter).

**Supporting practices the pipeline assumes:**

- **Version-pinning policy.** Each adapter declares a tested-against-version range in `pyproject.toml` (e.g., `hermes >= 1.0, < 2.0`). When upstream ships a new major version, `pip install whizzard[<adapter>]` keeps existing users on the validated range until the adapter is updated. Caps blast radius when automation falls behind. Works with the monorepo + extras direction in D-131's notes.
- **Severity-based filtering.** The detection layer filters on paths and release notes / labels to reduce noise: a CVE patch escalates to a fast-path security-labeled issue; a non-API refactor shouldn't trigger anything.
- **Upstream relationships.** Long-term, friendly contact with upstream maintainers (Hermes, OpenClaw, NanoClaw, etc.) catches breaking changes before they ship — more valuable than any automation. The pipeline is a backstop, not a substitute.

**Rationale:** Adapter rot is a real maintenance burden for any project that bridges to actively-developed upstreams. Without automation, the rot happens silently until a user files a bug — slow, embarrassing, and corrosive to trust. Without *safe* automation, the rot happens loudly via shipped-broken releases — worse. The shape above maximizes automation where it's cheap and reversible (detection, testing, reporting) and keeps humans in the loop where stakes are high (code changes touching safety-relevant adapter logic, version releases). Whizzard's positioning as a safety tool makes the auto-fix / auto-ship boundary load-bearing: a bot patching adapter code on a weak test suite is the failure mode that erodes the project's trust premise — and is hard to recover from once it ships. Version pinning is the complementary defense; it bounds the blast radius of *any* failure (automation falling behind, missed upstream change, bad release) by keeping users on the last validated version until a maintainer signs off. Severity-based filtering and upstream relationships further compress the response window for the cases that matter most (security) and reduce noise for the cases that don't (cosmetic refactors).

**Source:** conversation 2026-05-14 (during D-90 wrap-up; Bryan's question on OSS maintainability for adapter repos).

**Status:** active

**Notes:**
- Implementation is a post-MVP / OSS-launch concern; this decision frames the policy now so MVP code is structured to enable it later — adapter tests should be organized into smoke / unit / integration tiers, and `pyproject.toml` should declare version ranges per adapter from the start.
- Related to D-131 (OSS-launch milestone scope); this pipeline is one of the operational ingredients OSS launch requires.

### D-155: Core-maintained adapter slate is small and curated; native harness lands at v2.0

**Type:** scope

**Door Type:** two-way for the slate composition and maintenance policy (both reorganizable); the v2.0 native-harness commitment becomes closer to one-way once that product ships and acquires users.

**Decision:** Whizzard's core-maintained adapter slate is fixed at three harnesses across the project's planned releases:
- **MVP** ships Whizzard core + the generic shell adapter + the Hermes adapter.
- **v1.0** adds the NanoClaw adapter (supersedes D-97, which had it as vague "post-v1").
- **v2.0** adds a Whizzard-native secure-by-design harness (working name "Whizzard Harness"; a proper product name is deferred to closer to v2.0 implementation to avoid overloading "Whizzard" between the wrapper and the harness component).

Any other harnesses — OpenClaw, Claude Code, Codex, Cursor, etc. — are not core-maintained. The adapter Protocol (D-28) is the open contract; third parties can ship adapters as separate packages (e.g., `whizzard-adapter-<name>`) at their own release cadences. The core team supports the three named harnesses; the ecosystem maintains the long tail.

**Rationale:** Wrapper projects scale linearly in upstream-change-detection and adapter-maintenance burden as they expand their supported harness set — the "Linux-distro maintainer trap." Capping the core-maintained slate at three keeps the burden tractable for a solo or small-team project. The choice of slate reflects three different things: Hermes is the user's daily-driver and the Stage 8 work; NanoClaw is the closest peer and pairs well with Whizzard's hardening differential (D-93); the native harness is the secure-by-design hedge against the wrapper-only positioning being long-term unsustainable, and provides a reference implementation of what "secure agent harness" means. The community-adapter path (Protocol-as-contract, third-party packages) preserves cross-harness reach for users who want it, without committing the core team to maintaining adapters for harnesses they don't use. The "not an agent platform" stance (D-16) is preserved — a single native harness sitting alongside the wrapper isn't an agent platform, it's a complementary product.

**Source:** conversation 2026-05-14 (during the maintenance-burden discussion that explored harness-vs-wrapper positioning).

**Status:** active; supersedes D-35 and D-97.

**Notes:**
- The native harness commitment is deferred to v2.0 deliberately — it doesn't block MVP or v1.0 launches, and gives time for the wrapper position to prove out before adding a second product to the surface.
- Naming for the native harness needs to be settled before v2.0 implementation to avoid product-name overloading.
- The three-harness cap reflects current maintenance capacity; the slate can grow if overhead proves manageable in practice (additional contributors, mature upstream-change automation per D-154, or community-adapter learnings that surface a high-value harness worth core-team adoption).

### D-156: Whiz MCP server runs in-cell with launch-time snapshot

**Type:** architecture

**Door Type:** two-way for Stage 9 (the in-cell MCP server is structurally separable — the agent's MCP-client config can be redirected to a host-side socket later if pressure shifts), but becomes effectively one-way once Stage 13/14 mutating tools layer on the event-file request channel and downstream adapters wire to it.

**Decision:** The Whiz MCP server runs as a Python child process inside the execution cell. At cell launch, Whizzard writes a state snapshot — profile, mounts, network policy, expiry, harness, session_id — into a mounted location the cell reads. The MCP server serves Stage 9 read-only tools from this snapshot plus mounted live-appended audit logs. `whiz_emit_event` writes to a per-session ephemeral event file inside the cell; Whizzard's termination flow merges those events into the host-side audit log on session_end. Future Stage 13/14 mutating tools (`whiz_request_mount`, `whiz_request_extend`) use the same event-file pattern: the agent writes a "request" event to a known path, Whizzard host-side reads it (inotify or short-interval polling) and processes; responses flow back as events the agent sees.

**Rejected: host-side MCP server with cell connecting via Unix socket or localhost port.** Reasons:

- New host-cell IPC surface adds attack surface and lifecycle complexity (socket-file management, permissions, cross-platform fragility — Unix sockets work clean on Linux/macOS but not Windows).
- Per-session authorization required to prevent cross-session state leakage; the in-cell snapshot model gets this isolation for free, structurally.
- Long-lived host daemon adds host-side state Whizzard doesn't currently have (Whizzard is CLI-driven; introducing a daemon is a larger lift than the value justifies here).
- Live host-side state can leak information across sessions if not carefully scoped; the snapshot model is naturally per-session.
- Doesn't buy advantages that matter for Stage 9's read-only tool set — snapshot semantics are *correct*, not limiting (the cell IS what was launched).

**Rationale:** The in-cell model aligns with D-21 (host = control plane, container = execution plane) — the MCP server is just another in-cell tool, not a new control-plane component. Architecturally simpler, avoids cross-platform IPC complexity, gets per-session state isolation structurally rather than through authorization logic. The "live state" advantage of the host-side model doesn't translate into actual Stage 9 benefits: `whiz_status` returning launch-time state is correct; `whiz_audit_self` reads from a mounted live-appended log without IPC; `whiz_emit_event` event-merging at session_end is fine for non-time-critical agent reflections. The Stage 13/14 extensibility concern has a clean in-cell-compatible answer in the event-file request channel pattern, which scales to mutating tools without rewriting Stage 9.

**Source:** conversation 2026-05-14 (Stage 9 pre-implementation design discussion, post-build-plan alignment).

**Status:** active

**Notes:**
- Per D-153, the MCP-server implementation lives in adapter-or-utility space, not Whizzard core. The Hermes adapter owns the wiring to point Hermes's MCP-client config at the in-cell server. Generic shell adapter doesn't use the MCP server (no agent).
- The in-cell server is structurally separable. If future pressure (e.g., Stage 14 mutating tools requiring synchronous host responses that the event-file channel can't deliver cleanly) makes host-side MCP attractive, the agent's MCP-client config changes; the rest of the design holds.
- Image bloat is marginal — Python is already in the execution image (Hermes is Python). MCP SDK is small.

### D-157: Default profile gains `allow_broad_mount: true` (supersedes D-38 on this field)

**Type:** safety

**Tags:** profiles

**Door Type:** two-way (default values are non-breaking to change; OSS-launch will likely require revisiting this to ship a more conservative public default — see Notes).

**Decision:** The bundled `default` profile's `allow_broad_mount` flag changes from `false` to `true`. All other fields (network_enabled=true, duration_seconds=None, description as SAFE-NET-style productive baseline) are unchanged. The two-gate broad-mount override (D-46) is preserved at the same strength: `allow_broad_mount: true` on the profile is gate one; the `--allow-broad-mount` CLI flag (or a preset declaring it) is gate two. Both gates still required.

**Rationale:** The user's daily-driver use case (D-101 personal-use threshold; Hermes Migrate plan per D-86) requires mounting `~/Documents/Claude/projects` and `~/ai-sandbox`. The first sits inside `~/Documents/`, which is a probable cloud-sync root (D-51 → override-required tier). Under the prior default-profile shape (`allow_broad_mount: false`), every launch using `default` would have the profile gate closed against broad-mount overrides, making the user's primary preset unusable without switching to `power` (which has a 1hr duration cap and is poorly framed for always-on use). Flipping the default's `allow_broad_mount` to `true` opens the profile gate so a preset (or per-launch CLI flag) can attach broad mounts when explicitly authorized. The two-gate model is preserved — opening profile gate alone does not auto-attach broad mounts; the second gate (CLI flag or preset declaration) is still required.

**Source:** conversation 2026-05-15 (Stage 10 design conversation, design item #1 — preset bundle for daily-driver `hermes` preset).

**Status:** active; supersedes D-38 on the `allow_broad_mount` field specifically.

**Notes:**
- D-38's broader framing of the default profile as "SAFE-NET baseline" still holds for the other fields (network on, no mounts pre-bound, unlimited duration). The change is scoped to one field.
- For OSS-launch this almost certainly needs to be revisited. A reasonable shape: the bundled `default` profile reverts to `allow_broad_mount: false` for public users, and Bryan's personal-config layer keeps the `true` setting locally. Currently MVP is the personal-use threshold (D-101), so the simpler approach of one bundled default that matches Bryan's workflow is acceptable.
- The slate gains a small gap with this change: there is no longer a profile that is "network on, unlimited duration, allow_broad_mount=false." Users wanting that posture today would either override per-launch (don't pass `--allow-broad-mount`) or use `build` (network on, 2hr cap). Filling the gap is a post-MVP concern.

---

## Open / unresolved

(Status: open across the document — collected here for visibility. Full entries above.)

- **D-131** — OSS-launch milestone scope
- **D-132** — Sidecar-proxy mechanism in OSS-launch
- **D-133** — Failure-mode semantics across new controls
- **D-135** — Read-only project-root mounting as a Whizzard pattern
- **D-136** — NanoClaw upstream collaboration

### D-130: Personal-use MVP threshold — additional ○ items to pull in

**Type:** scope

**Door Type:** two-way (already superseded by D-137 — the user chose 'all five' to clear the personal-use threshold).

**Decision:** Which additional surface items rise to MVP for the personal-use threshold (candidates: stop+restart capability adjustment, request-side MCP tools, OneCLI vault, Discord read-only status, idle timeout) is unresolved.

**Source:** docs/control_surface.md (Open items #1)

**Status:** superseded by D-137

### D-131: OSS-launch milestone scope

**Type:** scope

**Door Type:** two-way (still open; the OSS-launch scope decision is intentionally deferred until MVP operational evidence informs it).

**Decision:** The OSS-launch milestone scope (distinct from MVP) is unresolved; needs definition once MVP is operational.

**Source:** docs/control_surface.md (Open items #2)

**Status:** open

**Notes (2026-05-14, repo-structure sub-question):**

One input toward eventual scope: how to structure the OSS repo(s) so that updates to one harness don't compromise other users' installs. Three options considered:

1. **Single repo, single package (current state).** Simple, but every adapter's runtime deps are pulled in on `pip install whizzard`, including for users who only want generic shell.
2. **Single repo, Python packaging extras.** `pip install whizzard` ships core + generic shell; `pip install whizzard[hermes]` adds Hermes adapter and its deps; `pip install whizzard[openclaw]` likewise. Adapter modules guard top-level imports of harness-specific libraries; tests use `pytest.importorskip` so absent extras don't fail CI. One issue tracker, one docs site, one PyPI listing. Adapter Protocol changes (D-28) remain atomic across all adapters in a single PR.
3. **Multi-repo (core + per-adapter).** Independent release cadences per adapter, hard maintainer-ownership boundaries. Costs: cross-repo Protocol-change coordination, version-skew risk between core and adapter, fragmented discoverability for new users, multiplied CI/issue-tracker/release infrastructure.

**Current lean:** Option 2 (monorepo + extras) at OSS launch. The adapter pattern (D-28) plus the isolation rule (D-153) already provide architectural change isolation — repo separation primarily adds independent release versioning and dep isolation, both achievable via extras with significantly less coordination overhead at the project's current scale (one main maintainer, MVP slate of 1–3 adapters). Option 3 becomes attractive *post-launch* if specific pressure shows up: third-party adapter maintainers needing repo autonomy, or genuine adapter-vs-core release-cadence conflicts.

**Why this lean preserves optionality:** D-153 plus the adapter Protocol mean adapter modules are already structurally separable — own file, own optional-dep block, no core imports leaking harness-specific identifiers. If a repo split is needed later, it is a mechanical move (lift the adapter file + its `pyproject.toml` block into a new repo) rather than a refactor. Staying in one repo at launch does not lock in the choice.

**Open sub-question:** does the OSS-launch milestone include adopting an extras-based packaging structure (`whizzard[hermes]`) at launch time, or wait until a second adapter actually lands and forces the question?

**Source:** conversation 2026-05-14 (during D-89 discussion; Bryan's question on adapter repo isolation).

### D-132: Sidecar-proxy mechanism in OSS-launch

**Type:** architecture

**Door Type:** one-way (sidecar proxy is an enabling architectural primitive — choosing to add it commits to a richer in-cell network surface; choosing not to forecloses several adjacent capabilities).

**Decision:** Whether to introduce a sidecar-proxy mechanism in OSS-launch (which unlocks egress allowlists, MCP tool shaping, traffic logging, vault generalization) is unresolved.

**Source:** docs/control_surface.md (Open items #3)

**Status:** open

### D-133: Failure-mode semantics across new controls

**Type:** architecture

**Door Type:** one-way (whichever shape lands — single policy or per-feature — becomes load-bearing for every control's enforcement semantics; reversing requires re-evaluating all of them).

**Decision:** Whether to define a single framework-level violation policy (kill / pause / quarantine / continue+log) or per-feature policies is unresolved.

**Source:** docs/control_surface.md (Open items #4)

**Status:** open

### D-134: OneCLI direct integration for MVP credential injection

**Type:** adapter

**Door Type:** two-way (OneCLI is the chosen MVP delivery mechanism; the credential-injection layer is replaceable — D-91's vault generalization is the post-MVP direction, host env vars are a fallback if OneCLI ever became unavailable).

**Decision:** Whizzard integrates with OneCLI directly for MVP credential injection. The Hermes adapter (and any future agent adapter that needs platform credentials) fetches secrets via OneCLI at adapter launch time rather than reading from long-lived host environment variables. The integration is a shell-out to the `onecli` CLI from the adapter; no embedded SDK in the Python codebase.

**Scope clarification re: D-91.** D-91 specifies "credentials never enter the container; outbound HTTPS routed through a host-side gateway that injects per request." That pattern fits "agent uses external API" use cases (NanoClaw's primary shape). It does not fit "agent IS the gateway" use cases (Hermes), where the agent itself opens the platform connection from inside the cell and consumes the credential at WebSocket setup time — no outbound HTTPS request exists to proxy. For gateway-style harnesses, OneCLI's role is **delivery mechanism only**: fetch on launch, inject as env var into the cell, container exits and the env var dies with it. This preserves OneCLI's security value (no long-lived host env var, per-launch credential lifetime, central revocation/rotation via OneCLI) without claiming the literal "never enter container" guarantee that D-91 cannot deliver for gateway-style harnesses.

**Pattern:**
1. At adapter launch, Whizzard reads the harness profile config (e.g., `<HERMES_HOME>/config.yaml`) for active platforms.
2. For each active platform, the adapter shells out to OneCLI (exact CLI surface — likely `onecli secrets get <name>` or equivalent — to be confirmed against the installed OneCLI version during implementation).
3. Fetched credentials are passed into the container as env vars (`DISCORD_BOT_TOKEN`, etc.) at container start.
4. No host-side long-lived env vars are required.

**Failure modes:**
- OneCLI not installed → clear "install OneCLI" error pre-launch.
- Requested secret not in vault → clear error naming the platform and the secret key; user instructed to register the secret first via OneCLI.
- OneCLI returns non-zero unexpectedly → fail loud, do not launch.

**Rationale:** D-91 (active) committed to OneCLI as the architectural direction. The open question in D-134 was *when* (MVP or post-MVP). Resolving toward MVP-inclusion: (a) gets users off the "DISCORD_BOT_TOKEN permanently exported in your shell rc" failure mode immediately, (b) makes per-launch credential lifetime the default behavior from day one rather than a migration users have to opt into later, (c) aligns Whizzard's positioning as a safety tool with what users would reasonably expect at first contact, and (d) the implementation cost is bounded — shell-out to an external CLI is a small wrapper function, not a deep dependency. NanoClaw is the proof-point that OneCLI integration works in practice (nanoclaw_research.md L153–170, L211).

**Source:** docs/archive/nanoclaw_research.md (L153–170, L211, L254); D-91 (vault direction); D-89 (platform credential UX); conversation 2026-05-14.

**Status:** active

**Notes:**
- Confirms the architectural intent of D-91 while accurately scoping where its literal "never enter container" guarantee applies.
- Adds OneCLI as an MVP pre-condition for the Hermes adapter. Users installing `whizzard[hermes]` need OneCLI on their PATH; the adapter surfaces a clear error if it's missing.

### D-135: Read-only project-root mounting as a Whizzard pattern

**Type:** architecture

**Door Type:** two-way (the pattern is opt-in by design; can be added or removed as a recommendation without breaking existing setups).

**Decision:** Whether Whizzard should support / recommend NanoClaw's read-only project-root + selective writable subdirs pattern for "containerize my own dev project" use cases is unresolved.

**Source:** docs/archive/nanoclaw_research.md (Things to learn from NanoClaw)

**Status:** open

### D-136: NanoClaw upstream collaboration

**Type:** process

**Door Type:** two-way (relationship-building is iterative; could deepen into formal collaboration or stay informal depending on how the projects align).

**Decision:** Whether to pursue collaboration with NanoClaw upstream (offering Whizzard hardening as a complement to their scope-reduction model) is unresolved.

**Source:** docs/archive/nanoclaw_research.md (Open question 4)

**Status:** open

### D-158: Product rename Whizzard → Osmotiq; sequenced after MVP, before Hermes migration

**Type:** process

**Tags:** naming, sequencing, post-mvp, hermes

**Door Type:** two-way (the rename itself is mechanical and revertible via git; the sequencing trigger can be moved earlier or later as conditions warrant).

**Decision:** Rename the product from "Whizzard" (placeholder per D-02) to **Osmotiq** (CLI binary: `oiq`; domain `osmotiq.ai` already owned). Execute as a single batch-script sweep covering package dir (`whizzard/` → `osmotiq/`), CLI binary (`whiz` → `oiq`), env vars (`WHIZZARD_HOME` → `OSMOTIQ_HOME`), config dir (`~/.whizzard/` → `~/.osmotiq/`), session-log paths, doc references, decisions.md cross-refs, README, pyproject.toml, and skill files. Trigger: after MVP is operational (D-101 threshold met) but BEFORE migrating the daily-driver Hermes instance onto Whizzard.

**Rationale:** "Whizzard" was always a placeholder — D-02 itself renamed from "warlock" to dodge a ransomware-family collision, with the understanding that a real product name would come later. Osmotiq retains the osmosis metaphor (selective permeability across a membrane), which is conceptually apt for capability governance: capabilities flow one-way through a membrane (D-9), and the mount list IS the permission boundary (D-11). Three syllables, modern "-iq" suffix, `.ai` TLD signals product space. `oiq` is a 3-char CLI with no obvious collisions in common dev tooling. Domain already owned, so decision cost is zero. Sequencing window rationale: (1) MVP-focus principle — the rename doesn't unblock technical work, so doing it earlier diverts from critical path; (2) debug rename issues against a known-working Hermes setup *before* the production Hermes migration introduces additional unknowns; (3) avoids touching live config paths mid-MVP-build (`gateway.lock`, `HERMES_HOME`-adjacent dirs); (4) external-facing name not needed until OSS-launch prep, which is downstream of Hermes migration. Bundle with D-151 (uppercase → lowercase markdown filenames) into the same sweep to amortize disruption.

**Source:** This conversation (2026-05-16); supersedes D-02 on the active package name.

**Notes:** Whether to also acquire `osmotiq.com` later is separable from this decision and not blocking. During ongoing MVP work the CLI binary remains `whiz`; it renames to `oiq` as part of the same sweep.

**Status:** active; supersedes D-02 on the active package name.

### D-159: Programmatic launch API for orchestrator integration (post-MVP)

**Type:** scope

**Tags:** post-mvp, api, integration

**Door Type:** two-way (the decision to add an API surface is reversible at the doc/spec stage; once a specific shape ships in v1.0 release notes the door becomes one-way for *that shape*, but this decision commits only to having an API, not to its exact contract).

**Decision:** Post-MVP, OIQ exposes a programmatic launch surface (Python library first) so external orchestrators can spawn and supervise cells without shelling out to the CLI. Minimum v1.0 surface: `oiq.launch(harness=..., preset=..., session_id=..., on_exit=...)` returning a session handle, plus `oiq.status(session_id)` for health/lifecycle polling and `oiq.terminate(session_id, grace_seconds=...)` for explicit shutdown. Exact contract, error semantics, and sync/async split are left to a focused design pass before v1.0; this decision commits only to *having* a programmatic entry point at v1.0.

**Rationale:** Symphony (OpenAI's task-board agent orchestrator, ship-as-SPEC.md, InfoQ 2026-05) demonstrates the orchestration layer that sits above harnesses: watch issue tracker → spawn agent → supervise → restart on crash. OIQ's CLI-only entry point forces orchestrators to shell out, parse stderr, and re-invent structured session handling — brittle, slow, and hostile to integration. A library surface lets supervisors integrate cleanly: each task gets a cell, the supervisor polls status, restarts are session-id-keyed. This positions OIQ as "the containment layer beneath your orchestrator" rather than a standalone CLI tool, which is the durable framing per D-10 (harness-neutral core) and the long-term thesis in vision_and_strategy.md. Scope-bound to post-MVP: no MVP user is running an orchestrator yet (D-101 personal-MVP threshold), and exposing an API prematurely risks freezing a shape we have not validated against real orchestrator integration pressure.

**Source:** conversation 2026-05-18 (assessment of InfoQ "OpenAI Symphony Agents" article, 2026-05); see docs/post_mvp_spec.md §9.

**Status:** active

### D-160: ADAPTER_SPEC.md as contributor-facing adapter Protocol artifact at OSS-launch

**Type:** process

**Tags:** oss-launch, adapter

**Door Type:** two-way (a spec document can be rewritten, deprecated, or replaced; carrying an explicit SPEC_VERSION keeps the door two-way even after publication by making every change visible and intentional).

**Decision:** At OSS-launch, formalize the adapter Protocol (D-28) as a standalone `ADAPTER_SPEC.md` document at the repo root — separate from `whizzard.adapters.base` (which remains the canonical Python implementation). The spec describes contract semantics in language-neutral terms: lifecycle hooks, `container_mounts`, `container_env`, `mcp_env`, `wrap_up` timing, preflight expectations, error surfaces, and the `harnesses.json` schema. Carries a `SPEC_VERSION` independent of the package version. Treated as a release-gate artifact: any change requires an explicit version bump and changelog entry.

**Rationale:** Symphony's SPEC.md-first model (ship the spec, let adopters implement) is a proven pattern for contributor-driven ecosystem growth — OpenAI shipped Symphony as a SPEC.md plus an Elixir reference impl, not a product, and explicitly positioned it as "a reference implementation that developers can adapt and tailor." OIQ's adapter Protocol already exists as code (D-28, `whizzard/adapters/base.py`), but a Python Protocol class is not a contributor-facing artifact: it's tied to one language binding, embedded in the source tree, and contributors have to read the code to understand the contract. A standalone spec lowers contribution friction (read one file, build an adapter in any language), and protects the contract from accidental breakage by making it a versioned artifact the maintainer team must consciously update. Aligns with the curated-slate principle (D-155): we don't want to ship every adapter, we want third parties to be able to ship them safely against a stable contract.

**Source:** conversation 2026-05-18 (assessment of InfoQ "OpenAI Symphony Agents" article, 2026-05); see docs/post_mvp_spec.md §3 (Multi-Harness Rollout).

**Status:** active

### D-161: Stage 11 ships as `docs/examples/<harness>/` recipes, not as code in OIQ core

**Type:** process

**Tags:** oss-launch, integration, mvp

**Door Type:** two-way for the docs deliverable (example recipes can be revised, restructured, or removed); approaching one-way for the *rejected alternatives* (re-introducing a host-side MCP server or a per-harness emitter framework would require fresh security review and architectural justification, not just a rewrite).

**Decision:** Stage 11 — "zero-friction Whiz operation from inside any agent harness" — ships as copy-paste integration recipes in `docs/examples/<harness>/`, not as harness-specific code in OIQ core. Two production-grade examples land at this stage (`docs/examples/claude_code/` and `docs/examples/hermes/`) because Claude Code is the MVP user's daily-driver harness and Hermes is the MVP target adapter. A `docs/examples/README.md` index plus a root-README "Using OIQ inside your agent harness" section invites community-contributed recipes for Codex, Cline, OpenClaw, NanoClaw, and others. The CLI shipped in Stage 10 (`whiz r`, `whiz s`, smart defaults) is the harness-neutral surface; every recipe just shells out to it.

**Rationale:** The original Stage 11 framing was "bundle of `.claude/skills/` recipes" — single-vendor lock-in that violated D-10 (harness-neutral core). Two intermediate alternatives were considered and rejected during the design conversation (2026-05-18):

- **Rejected: host-side MCP server for harness UX.** Would have exposed `oiq.launch`, `oiq.status`, etc. as MCP tools any harness could call. Rejected on security grounds: a host-side MCP socket is a privilege-escalation surface — if a cell could ever reach it (e.g., a misconfigured bind-mount), the cell could spawn a maximally-permissive sibling cell and escape the in-cell read-only constraint of D-156. Also solves a problem only the *agent* has (structured tool surface), not the user — the user can already type `oiq r hermes` in any terminal. Zero net user benefit, real new attack surface.
- **Rejected: canonical `commands.yaml` + per-harness emitter framework.** Would have defined commands once in OIQ and emitted harness-specific wrappers via per-harness emitters. Over-engineered for an MVP user-base of one: the CLI is already the harness-neutral interface, and per-harness wrappers can be authored directly in `docs/examples/` without a generation layer. Adds two layers of indirection (canonical schema + emitter) for negligible benefit at MVP scale; break-even would be at 3+ supported harnesses, which is post-OSS-launch territory.

The chosen shape (docs/examples + CLI) preserves D-10 by NOT shipping harness-specific code in OIQ core — recipes are documentation, not product. The OSS-contribution path for new harnesses is "add a directory under `docs/examples/<harness>/`," which is the lowest-friction contribution shape available. Stage 11 becomes a documentation-and-examples stage, not a code-build stage; no new pip dependencies, no core code changes.

**Source:** conversation 2026-05-18 (Stage 11 D-148 design pause); see docs/mvp_build_plan.md §Stage 11 (carries the pivot in prose with the same rejected-alternatives note).

**Status:** active

### D-162: LLM-provider credential injection via declarative `secrets:` harness-config block

**Type:** safety

**Tags:** integration, hermes

**Door Type:** two-way for the field shape — the `secrets:` schema can be revised, OneCLI integration can be replaced, env-var names can be standardized. The prohibition on mounting `auth.json` (preserved from D-80) is closer to one-way; re-enabling it would require fresh security review of harness-managed credential schemas and an explicit per-harness opt-in override.

**Decision:** Harness configs declare the LLM-provider and platform credentials needed inside the cell via a `secrets:` field — a flat list of env-var names. At launch, the adapter fetches each value (OneCLI per D-134 where supported; host env-var fallback) and injects into the cell's environment. Plaintext credential values MUST NEVER appear in harness config files — only env-var names. Mounting `auth.json` (or any other harness-managed credential blob) into the cell remains prohibited by default per D-80.

**Rationale:** Stage 8's platform-token convention (D-89 amended, `<PLATFORM>_BOT_TOKEN`) covers platform credentials only. LLM-provider credentials (Anthropic, OpenAI, OpenRouter, GitHub Copilot, etc.) need an analogous injection path. Generalizing to a `secrets:` block with arbitrary env-var names is the smallest extension of the existing pattern that handles both cases uniformly. Validated empirically in the M7 smoke (2026-05-19): a Hermes inside an OIQ-wrapped cell with no `auth.json` present picked up `ANTHROPIC_API_KEY` from the cell's environment and made a successful Claude API call.

Rejected: **Mounting auth.json into the cell.** Today's auth.json contents may be three benign API keys (user-verified by inspection), but the file's schema is Hermes-managed and could grow to include identity-layer state (OAuth refresh tokens, account credentials, future Hermes-defined fields) in any release. Mounting commits to exposing whatever Hermes chooses to store there, indefinitely. Declaring per-secret in `secrets:` makes the cell's credential surface an explicit, auditable, per-harness decision. Schema-isolation and audit are the load-bearing reasons, not present-day threat severity.

Rejected: **Plaintext credential values in harness config.** A `harnesses.json` with literal API key values would be plaintext-credentials-on-disk in a file that's not a vault, not encrypted, and trivially readable by any process with file-read access on the user's account. The `secrets:` block declares names only; values come from runtime resolution.

Rejected: **Per-provider special-casing (e.g., `anthropic_api_key:`, `openai_api_key:` as named fields).** Treating each LLM provider as a named field would duplicate per-provider logic in OIQ core. A generic `secrets:` list works for any named credential — bot tokens, API keys, future provider types — with no provider-specific OIQ code.

**Source:** conversation 2026-05-19 (M7 smoke close-out + auth.json-mounting question); empirical validation in the Anthropic-provider variant smoke same date.

**Notes:**

- **OAuth tokens are not a suitable substrate for `secrets:` injection.** Hermes/Claude-Code-style OAuth access tokens (`sk-ant-oat*` prefix) are short-lived and client-scoped; refresh requires the refresh substrate, which lives in `auth.json` and cannot enter the cell per D-80. For cell-side use, users should issue **direct API keys** (Anthropic Console `sk-ant-api*`, OpenAI `sk-...`, etc.) — long-lived, individually rotatable, no refresh dependency. Treat dedicated-API-key-per-cell as the recommended deployment pattern; OAuth-mediated provider access stays on the host's daily-driver harness.
- **OneCLI integration caveat (worth a follow-up).** OneCLI's design is gateway-proxy (intercepts API calls and adds credentials at the network layer), not value-retrieval. Its CLI has no `secrets get` subcommand. The Stage 12 `fetch_secret` implementation calls `onecli secrets get <name>`, which doesn't exist — every current invocation falls through to the env-var fallback path. Worth either aligning with OneCLI's actual surface or removing the OneCLI integration entirely (relying on env-var injection alone). Not blocking D-162, but tracked here so it doesn't get lost.
- **Future enhancement (post-MVP):** an explicit per-harness `mount_auth_json: true` override could be exposed for users who have audited their auth.json contents and accept the forward-compat risk. Default remains opt-out.

**Status:** active

### D-163: Stage 13 design — `oiq adjust` CLI surface, TTY approval, container resolution

**Type:** scope

**Tags:** mvp, mounts, safety

**Door Type:** two-way for the CLI surface and approval shape (subflags can be added/removed, prompt wording can evolve, brevity aliases can be added later). The `AGENT_DENIED_CHANGES` denied-list semantic becomes closer to one-way once Stage 14 builds on it — re-permitting an agent-callable mutation after it has been on the denied list would require fresh security review.

**Decision:** Stage 13 ships `oiq adjust <session-id> [flags]` as a single CLI verb for mid-session capability mutation, with subflags `--add-mount <name>[:<mode>]`, `--remove-mount <name>`, `--extend <duration>`, `--allow-broad-mount`. The stop+restart mechanism (D-27) executes after a TTY `[y/N]` approval that displays a compact diff of the requested changes; the prompt is skipped only when every change is unambiguously narrowing (e.g., `--remove-mount` alone). Container resolution uses the Docker label `whizzard.session_id=<sid>` with exact-then-prefix matching; misses cross-check the session log to distinguish typos, ended sessions, and crashed sessions with appropriate user-facing messages. Mid-session `--allow-broad-mount` is permitted for human-initiated adjusts (same authorization shape as launch-time per D-46); the Stage 14 agent-initiated request path will enforce an `AGENT_DENIED_CHANGES` constant that excludes `--allow-broad-mount` (and similar high-risk mutations) from the agent-callable surface.

**Rationale:** D-27 settled the stop+restart mechanism at the architecture layer; Stage 13 is about the UX and CLI surface around invoking it. The single `adjust` verb with composable subflags lets the user combine multiple changes into one approval prompt and keeps help-discoverability in one place. The Stage 14 forward-compat hooks (pluggable `Approver` interface, library-shaped `adjust_session()` core, `AGENT_DENIED_CHANGES` constant) are structural choices that cost nothing at Stage 13 implementation time and save real refactoring when the MCP request path lands.

Rejected: **dedicated subverbs per operation** (`oiq extend`, `oiq add-mount`, etc.) — splits help across N entry points, prevents bundled multi-change commands with a single approval prompt, more code per verb. Single `adjust` verb wins on consistency and composability; brevity aliases can come later at the `r/s/p/m/pr` layer if a specific operation gets typed often enough.

Rejected: **disallowing mid-session `--allow-broad-mount`** (initial proposal). The argument FOR disallow was "mid-session creates a third entry path that undermines D-46's two-gate model." On scrutiny: the profile gate (D-46 first gate) still applies, the user typing the flag at a real terminal is the same authorization signal as at launch, and forcing a session restart for a forgotten flag is hostile UX — sessions accumulate state (conversation, agent memories, MCP context) that shouldn't be thrown away over a flag-omission mistake. Allowing it preserves the two-gate model where it matters (profile layer) and adds none of the actually-risky cases.

Rejected: **session-log-only container resolution**. Less robust against log corruption than Docker label lookup; requires cross-referencing cidfile state which can also drift. The Docker label is set on the container at launch, can't be forged from inside the cell (D-9: cell has no Docker socket access), and the container itself is the authoritative source of truth.

Rejected: **auto-launch fresh session when target session has exited**. Surprising — the mental model of `adjust` is "mutate a *running* session." Clear error + suggestion of the right command (`oiq r [preset]`) is more honest than silently doing something the user didn't ask for.

Rejected: **single-tier approval (everything prompts)**. Wasteful for `--remove-mount` which is always-safe (narrowing capability cannot grant access). Skipping the prompt only for narrowing-only operations keeps the prompt meaningful when it appears.

Rejected: **typed-`yes` confirmation**. Theater for low-stakes changes. The user just typed an adjust command; `[y/N]` is sufficient confirmation.

**Notes:**

- **Stage 14 forward-compat hooks.** Three structural choices Stage 13 makes that Stage 14 plugs into without refactoring: (1) approval is a callable parameter `Approver(change_diff) -> bool` — Stage 13 implements `tty_approver`; Stage 14 adds `mcp_request_approver`; (2) the core adjust operation is a library-shaped `adjust_session(session_id, changes, approver) -> AdjustResult` function the CLI thinly wraps; (3) `AGENT_DENIED_CHANGES = frozenset({"allow_broad_mount", "change_profile", ...})` is a module constant Stage 14's MCP request handler references to filter agent-callable mutations.
- **Session ID continuity.** Adjust uses the same session-id throughout where possible; the audit log gets a new event type linking the old and new container IDs so downstream tools can follow the chain. Implementation may simplify to "end old session, start new session with `superseded_session_id: <old>` metadata" if same-id continuity proves complex.
- **Terminal disconnect for interactive sessions.** A known limitation for MVP: adjust stops and re-launches the container, so an interactive terminal connected to the old container loses its connection. Daemon/gateway-mode sessions (Hermes gateway) are unaffected — they auto-resume from HERMES_HOME state. For interactive sessions, users can re-attach to the new container manually (`docker attach <cid>`), or run interactive sessions via tmux. Document; don't try to handle terminal-reattachment automatically in MVP.

**Source:** conversation 2026-05-19 (Stage 13 design pass per D-148 spirit); see docs/mvp_build_plan.md §Stage 13.

**Status:** active

### D-164: Image provenance is independent of containment; OIQ supports both OIQ-built and vendor-supplied images

**Type:** architecture

**Tags:** adapter, safety

**Door Type:** two-way for per-adapter provenance choice (each adapter picks its pattern); closer to one-way for the principle itself (OIQ owns flags, not images) — rolling back would require fresh architectural review.

**Decision:** OIQ owns the `docker run` invocation (security flags, mounts, env, lifecycle); the image is just the IMAGE argument. Adapters pick one of two patterns: (1) **OIQ-built image** — current Hermes, `docker/Dockerfile.hermes` layers the harness onto `whizzard-base`; used when the harness isn't natively containerized. (2) **Vendor-supplied image** — e.g., NanoClaw's published image; OIQ applies its containment flags at launch. Both run one container per session under identical OIQ posture; image provenance is the only difference.

**Rationale:** An earlier framing treated "Docker-native harnesses" as fundamentally incompatible with OIQ. On closer analysis the conflict is narrower: only harnesses requiring `--privileged` or `/var/run/docker.sock` access genuinely break the model — both defeat OIQ's containment. Harnesses that simply ship as a container image are wrappable by using that image directly with OIQ's flags applied.

Rejected: **Docker-in-Docker** — needs privileged mode; breaks `--cap-drop=ALL` and read-only rootfs. Rejected: **`docker.sock` mount** — root-equivalent host escape. Rejected: **blanket refusal to support container-native harnesses** — overcautious framing of a narrow problem.

**Notes:**
- Pin vendor images to specific digests (D-77 spirit), not tags.
- Hard incompatibility: harnesses requiring `--privileged` or `/var/run/docker.sock` cannot be wrapped under OIQ — declined, not adapted.

**Source:** conversation 2026-05-19 (NanoClaw "harness in container" question).

**Status:** active

---

### D-165: Stage 14 agent-request processing — file-mailbox channel + operator-invoked `whiz requests`; host-side MCP deferred to v1.0

**Type:** architecture

**Tags:** mvp, integration, safety

**Door Type:** two-way for the CLI surface (a real-time watcher can be layered on later without removing `whiz requests`); closer to one-way for the request-file schema once agents and adapters depend on it.

**Decision:** A contained agent requests a capability change (`whiz_request_mount`, `whiz_request_extend`) by writing a JSON file into a per-session request directory inside the `/run/whiz` mount (D-156 event-file pattern). The host picks requests up on-demand via the operator-invoked `whiz requests` command (list / approve / deny), which routes approved requests through `adjust_session` with `agent_initiated=True` (D-163). No background process watches the channel. A host-side MCP server — where the request tools would become synchronous round-trip calls — is the planned v1.0 revisit.

**Rationale:** `run_shell` blocks for the whole session, so picking up a request mid-session needs *some* concurrent mechanism. The operator-invoked command keeps Whizzard CLI-driven — the exact ground on which D-156 rejected a long-lived host daemon.

Rejected: **background watcher thread** — reintroduces always-on host-side liveness D-156 ruled out, adds concurrency to the load-bearing `run_shell`/`_perform_launch` path, and a mid-session TTY prompt is poor UX for interactive sessions. Rejected: **host-side MCP server now** — gives genuine synchronous tool calls (D-156 itself flagged Stage 14 as the trigger to consider it), but opens a cell→host RPC channel (new D-9 surface), needs a per-session host process, and reopens shipped Stage 9 code; too large a lift for the MVP. Deferred, not dismissed.

**Notes:**
- The MVP design is forward-compatible: the request-file schema, `adjust_session`, and the `AGENT_DENIED_CHANGES` filter all carry over unchanged when host-side MCP later replaces just the transport.
- Agent requests are pre-validated host-side before any stop+restart, so a request needing a broad-mount override is denied with the session still running rather than killing it on a failed relaunch.

**Source:** conversation 2026-05-21 (Stage 14 design discussion with Bryan).

**Status:** active

---

### D-166: Stage 15 design — duration + idle enforcement via a Popen poll loop, hybrid idle detection, extend = remaining + N

**Type:** architecture

**Tags:** mvp, safety, profiles

**Door Type:** two-way for the tunables (poll interval, CPU threshold, the idle-signal set — signals can be added) and the `idle_timeout_seconds` schema; closer to one-way for the Popen-poll-in-`run_shell` mechanism once downstream code depends on `expiry_reason`.

**Decision:** `run_shell` launches the cell with `subprocess.Popen` and hands it to `monitor_and_enforce` (`whizzard/enforcement.py`) — a single-threaded poll loop, not a background thread. Each tick checks the wall-clock duration cap and samples idle activity; on a limit hit it runs the adapter's graceful wrap-up (or `docker stop`) and records `expiry_reason` (clean / duration / idle) on session_end. Idle detection is **hybrid**: the primary signal is container resource activity from `docker stats` (CPU + network + block I/O), and a write to the agent event file or request channel also resets the idle clock. `oiq adjust --extend` is wired through as `duration_override_seconds` = (original cap − elapsed) + extension. `idle_timeout_seconds` becomes a new optional profile field.

**Rationale:** `run_shell` already blocks for the whole session; a poll loop in that same call needs no concurrency machinery and keeps the TTY passthrough intact.

Rejected: **background watcher thread** — adds concurrency to the load-bearing launch path for no gain over an in-process loop (same rejection spirit as D-165). Rejected: **`subprocess.run(timeout=)`** — kills the docker client ungracefully and can't run the adapter wrap-up or check idle. Rejected: **CPU-only idle** — an agent blocked on a slow model call shows ~0% CPU and would be false-killed. Rejected: **event-log-only idle** — a working-but-quiet agent emits no events and would also be false-killed. The hybrid covers both: resource activity catches a dead session, network traffic covers the model-call case, event writes confirm a live agent. Rejected: **extend = fresh full window** — a non-extend adjust would silently reset the cap; remaining-time math keeps the cap meaningful and makes `--extend N` mean exactly "N more".

**Notes:**
- The `default` profile keeps `idle_timeout_seconds = None` — it is the always-on baseline. Other bundled profiles carry 15–30 min.
- Pre-expiry warning (a build-plan Stage 15 bullet) is deferred — it needs a delivery-mechanism decision (host TTY vs. an audit-log event the agent polls vs. an agent event).
- Hot-restart of idle-ended sessions is the planned Stage 15.5 follow-on; `expiry_reason: idle` is its enabler.

**Source:** conversation 2026-05-22 (Stage 15 design discussion with Bryan).

**Status:** active

---

### D-167: In-cell MCP deployment — `COPY mcp_server.py` into the execution image; don't install the `whizzard` package

**Type:** architecture

**Tags:** mvp, safety, integration

**Door Type:** two-way for the in-cell path and script name; closer to one-way for the deployment mechanism once images and harness MCP-client configs depend on it.

**Decision:** `Dockerfile.hermes` `pip install`s `mcp` and `COPY`s `whizzard/mcp_server.py` in as a standalone script. The harness's MCP-client config invokes `python <path>/mcp_server.py` with the WHIZ_* env vars the adapter's `mcp_env` sets.

**Rationale:** `mcp_server.py` is self-contained (stdlib + lazy `mcp`); reading it teaches the agent only what the cooperation layer reveals by design. Installing the whole package would put `safety.py`, `enforcement.py`, and `adjust.py` in the cell — a full policy-layer implementation map. Most acute case: a compromised agent that reads `enforcement.py` defeats idle detection trivially by writing the event file every ~30s. The kernel-enforced layer (cap drops, read-only rootfs, mounts, network) is unaffected either way.

Rejected: **install the `whizzard` package** — leaks the policy-layer mechanism (idle especially); also ships ~20 host-side modules the cell never executes. Rejected: **bind-mount `mcp_server.py` at launch** — same exposure as the chosen approach but mounts host code into the cell and adds per-launch wiring the image doesn't need.

**Source:** conversation 2026-05-22 (source-code-exposure framing).

**Status:** active

---

## Tag vocabulary

Tags are drawn from a curated canonical vocabulary, not invented per entry. Free-form tagging defeats grep-based browse: a future search for "API decisions" misses entries tagged `library-surface` instead of `api`, and a vocabulary that grows by accretion ends up with 50 near-synonyms after 150 entries.

The decision-capture skill enforces this: new entries must pick tags from the list below, or the maintainer must explicitly add a new tag to the vocabulary (and revisit existing entries to apply it where it fits).

### Canonical tags

**Adapter / harness layer:**
- `adapter` — adapter Protocol, contracts, slate, ADAPTER_SPEC (any adapter-layer decision not tied to one specific adapter)
- `hermes` — Hermes adapter / integration specifically
- `nanoclaw` — NanoClaw research / adapter specifically

**Surfaces:**
- `api` — programmatic API surfaces (library API, MCP API, in-process entry points)
- `integration` — integration with external systems (orchestrators, vault tools, CI, etc.)

**Domain clusters:**
- `naming` — product / component / file naming decisions
- `profiles` — profile config and defaults
- `mounts` — mount registry and mount behavior
- `safety` — hardening / safety policy decisions (used as secondary when `Type:` is something else)

**Scope / lifecycle:**
- `mvp` — MVP-scope work
- `post-mvp` — post-MVP-scope work
- `oss-launch` — OSS-launch milestone scope (includes contributor-facing artifacts)
- `sequencing` — timing / order-of-execution decisions

### Adding a new tag

Steps:

1. Confirm the new tag is genuinely cross-cutting (multiple existing or anticipated entries would carry it). One-off topics belong in the entry body, not as a tag.
2. Confirm no existing canonical tag covers the concept. Check the list above and grep for near-synonyms.
3. Add the new tag to the relevant cluster above with a one-line definition.
4. Apply the new tag to any prior entries it fits (so the index stays useful).
5. Update the [decision-capture skill](../../../.claude/skills/decision-capture/SKILL.md) tag-vocabulary reference if the change is significant enough to warrant maintainer-side notice.

### What NOT to tag

- The product's own name as a tag (covered in title and Source).
- One-off external references (the article URL belongs in `Source:`, not as a tag).
- The `Type:` field's value (Type already classifies; redundant tagging adds noise).
- Workflow ephemera ("urgent", "in-progress") — those belong in Status or in tasks, not in long-lived decision metadata.

---

## Cross-references

For narrative context behind clusters of decisions:

- **README.md** — high-level orientation; D-01..D-08 (project naming) and D-09..D-11 (foundational principles) live here in summary form.
- **docs/vision_and_strategy.md** — D-15..D-18 (positioning, audience, what-we-are-not), D-119..D-120 (Phase 3 Breaker, Phase 4 Shadow Home).
- **docs/architecture.md** — D-09..D-14 (foundational principles), D-19..D-27 (architecture & layering), D-28..D-36 (adapter contract), D-47..D-54 (safety policy), D-32 (agent identity).
- **docs/mvp_build_plan.md** — D-37..D-46 (profiles & mounts), D-64..D-71 (session lifecycle), D-72..D-77 (image management), D-99..D-108 (MVP scope).
- **docs/post_mvp_spec.md** — D-91, D-98 (vault), D-109..D-118 (v1.0 goals & requirements), D-121..D-123 (deferred features), D-159 (orchestrator integration API), D-160 (ADAPTER_SPEC.md).
- **docs/stage_validation.md** — operational confirmation of D-37..D-71; the validation checklists are the practical contract behind those design decisions.
- **docs/archive/hermes_research.md** — D-78..D-90 (Hermes integration), D-25 (MCP-universal), D-24 (don't recreate behavioral controls).
- **docs/archive/nanoclaw_research.md** + **docs/archive/nanoclaw_internals.md** — D-91..D-98 (NanoClaw lessons applied), D-14 (mount allowlist principle), D-92 (architectural elevation), D-77 (digest pinning rationale).
- **docs/control_surface.md** — D-23 (control layering), D-25..D-27 (cooperation layer), D-76, D-101..D-104 (2026-05-09 framing decisions), D-130..D-133 (open items).
- **docs/session_handoff.md** — D-01..D-03 (naming), D-46, D-48, D-55..D-56 (settled hardening choices), D-78..D-90 (Hermes settled and open).
- **whizzard/** package code — D-08 (WHIZZARD_HOME), D-28..D-31 (adapter Protocol), D-37..D-45 (profile and mount loaders), D-34 (harness types).
- **pyproject.toml** — D-02 (package name), D-06 (license), D-07 (version, Python).
- **memory/feedback_*.md** — D-124..D-126 (durable collaboration rules).

## Open questions tracker

The following decisions are currently **open**. Any work that depends on them should treat them as unresolved; closing one promotes it to **active** with a non-open Decision sentence.

- **D-131** — OSS-launch milestone scope
- **D-132** — Sidecar-proxy mechanism inclusion in OSS-launch
- **D-133** — Framework-level failure-mode policy vs. per-feature
- **D-135** — Read-only project-root mounting pattern adoption
- **D-136** — NanoClaw upstream collaboration
