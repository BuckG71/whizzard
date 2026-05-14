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

## 1. Project & naming

### D-01: Repo placeholder name is `basicagentauth`

**Decision:** Public/private GitHub repo ships under the placeholder name `basicagentauth`.

**Rationale:** Real product names are still in flux; an opaque placeholder avoids premature naming commitments.

**Source:** docs/session_handoff.md

**Status:** superseded by D-145

### D-02: Internal package name is `whizzard` (replaces `warlock`)

**Decision:** Python package and CLI command are named `whizzard`.

**Rationale:** Original name `warlock` collided with an active 2026 ransomware family; renamed to avoid the collision.

**Source:** docs/session_handoff.md; pyproject.toml

**Status:** active

### D-03: Local working directory stays `airlock-warlock` mid-development

**Decision:** Do not rename the working directory mid-session; it remains `airlock-warlock` despite the package rename.

**Rationale:** Renaming mid-session breaks Claude Code's working-directory binding.

**Source:** docs/session_handoff.md

**Status:** superseded by D-146 (rename happens between sessions, not mid-session)

### D-04: Two-name component split — Airlock vs. Whizzard

**Decision:** Airlock = governance/containment layer; Whizzard = orchestrator/runtime.

**Rationale:** Two-component naming maps to the split between policy enforcement and harness orchestration; keeps the layering explicit in user-facing language.

**Source:** docs/vision_and_strategy.md; docs/architecture.md

**Status:** superseded by D-144

### D-05: Verbal framing — "Whizzard operates. Airlock governs."

**Decision:** Adopt "Whizzard operates / Airlock governs" (alt: "Whizzard executes inside Airlock") as the canonical short framing.

**Rationale:** Keeps the directionality of capability flow visible in copy.

**Source:** docs/vision_and_strategy.md; docs/architecture.md

**Status:** superseded by D-144

### D-06: License is MIT

**Decision:** Project licensed MIT.

**Rationale:** Default permissive license aligned with OSS-launch goals.

**Source:** pyproject.toml

**Status:** active

### D-07: Initial version is 0.1.0; Python 3.11+

**Decision:** Initial package version is 0.1.0; minimum Python is 3.11.

**Rationale:** Pre-1.0 signals MVP/under-construction status; Python 3.11 gives modern typing without forcing 3.12.

**Source:** pyproject.toml

**Status:** active

### D-08: WHIZZARD_HOME defaults to `~/.whizzard`

**Decision:** Whizzard's host-side state directory is `~/.whizzard` (override via `WHIZZARD_HOME` env var).

**Rationale:** Standard dotfile convention; env-var override allows test isolation and alternate layouts.

**Source:** whizzard/config.py

**Status:** active

---

## 2. Foundational principles

### D-09: One-way capability flow

**Decision:** Agents request capabilities; Whizzard grants; agents never self-grant.

**Rationale:** Foundational trust model for the whole system; any feature that violates this breaks the security thesis.

**Source:** README.md; docs/architecture.md (Architectural Constants)

**Status:** active

### D-10: Whizzard core stays harness-neutral

**Decision:** Whizzard core must know nothing about Hermes, OpenClaw, NanoClaw, Discord, or MCP specifics. All harness-specific logic lives in adapters.

**Rationale:** Coupling core to any specific harness collapses the layering and makes future harnesses second-class.

**Source:** docs/architecture.md (Whizzard Core; pre-D-144 referred to as "Airlock Core")

**Status:** active

### D-11: The mount list IS the permission model

**Decision:** Capability grants are the literal, visible list of mounts and toggles a user sees before launch — not abstract policy declarations.

**Rationale:** Makes permissions human-readable, auditable at a glance, and reduces accidental exposure.

**Source:** docs/vision_and_strategy.md; docs/architecture.md

**Status:** active

### D-12: Config integrity is non-negotiable

**Decision:** Agent-reachable mount paths must never include the Whizzard config directory, regardless of policy files.

**Rationale:** An agent that can write files Whizzard reads can influence its own policies, breaking the trust model. Cannot be relaxed by profiles or presets.

**Source:** docs/architecture.md (Config Write-Protection Invariant)

**Status:** active

### D-13: Time-bounded sessions are enforced, not advisory

**Decision:** Session duration is a first-class capability primitive that Whizzard enforces; unlimited is explicit, never the silent default.

**Rationale:** A "soft" duration cap is a non-cap; safety hinges on the runtime actually terminating.

**Source:** docs/architecture.md; docs/post_mvp_spec.md §5

**Status:** active

### D-14: "Mount allowlist outside agent reach" is an architectural principle

**Decision:** The directory that defines an agent's permissions must be unreachable (and unwritable) from any agent-writable mount.

**Rationale:** Validated against NanoClaw's external `~/.config/nanoclaw/mount-allowlist.json` pattern; same principle as config write-protection but elevated as a general rule.

**Source:** docs/archive/nanoclaw_research.md (Things to learn from NanoClaw)

**Status:** active

### D-15: Useful + controlled + simple is the middle-ground positioning

**Decision:** The product target is the middle ground between unrestricted trust and unusably-restrictive sandboxes.

**Rationale:** Existing options force a binary choice; the durable opportunity is dynamic capability governance for daily-driver use.

**Source:** docs/vision_and_strategy.md (Long-Term Strategic Thesis)

**Status:** active

### D-16: This is NOT an agent platform / chatbot / coding assistant / Docker wrapper / generic AI sandbox / security utility

**Decision:** Reject positioning as any of the listed categories.

**Rationale:** Sharper "what we are not" framing protects the actual positioning ("local capability governance layer for autonomous AI systems").

**Source:** docs/vision_and_strategy.md (Product Positioning)

**Status:** active

### D-17: Not competing with Claude Code / Codex / Cursor

**Decision:** Whizzard targets local/open-source agents (Hermes, OpenClaw, NanoClaw) and solo-developer power users — not the major harness vendors.

**Rationale:** Major harness providers will likely absorb basic sandboxing; the durable opportunity is cross-agent, harness-neutral governance.

**Source:** docs/vision_and_strategy.md

**Status:** active

### D-18: Not initially targeting enterprise IAM, SOC2, centralized governance

**Decision:** Enterprise/compliance audiences are explicitly out-of-scope for v1.

**Rationale:** v1 audience is solo developers, AI power users, security-conscious tinkerers; enterprise governance is a different product shape.

**Source:** docs/vision_and_strategy.md (Intended Audience)

**Status:** active

---

## 3. Architecture & layering

### D-19: Four named components — Whizzard, Airlock, Execution Cell, Harness Adapter

**Decision:** Component vocabulary is fixed at: Whizzard (orchestrator), Airlock (policy/containment), Execution Cell (the contained environment, Docker in MVP), Harness Adapter (integration layer). *(Three components after D-144 consolidation: Whizzard, Execution Cell, Harness Adapter.)*

**Rationale:** Stable vocabulary lets docs and code converge; alternatives (e.g., calling the cell "the container") leak implementation detail.

**Source:** docs/architecture.md (System Components)

**Status:** partially superseded by D-144 (the Airlock sub-component name is retired; the other three names remain)

### D-20: Three architecture layers — Whizzard Core, Adapter Layer, Execution Backend

**Decision:** The system is organized as Whizzard Core (harness-neutral) → Harness Adapter Layer → Execution Backend. *(Pre-D-144: "Airlock Core" was the term for what is now "Whizzard Core".)*

**Rationale:** Clean seams allow swapping execution backends and adding adapters without touching core; matches the trust model.

**Source:** docs/architecture.md (Architecture Layers)

**Status:** active

### D-21: Host = control plane; container = execution plane

**Decision:** Whizzard daemon, policy engine, config registry, logs, and the future Discord bot run on the host. Agent runtime, shell, filesystem access, and tool execution run inside the container.

**Rationale:** Mandatory for the security model — control surfaces above the agent's reach.

**Source:** docs/architecture.md (Host vs Container Boundary)

**Status:** active

### D-22: Docker is the MVP execution backend; Podman/Firecracker/etc. are future

**Decision:** MVP ships on Docker only; alternative backends (Podman, Firecracker, Apple Virtualization, cloud) are deferred.

**Rationale:** Docker is ubiquitous on dev machines and gives the needed isolation primitives; abstracting now without a second implementation is speculative.

**Source:** docs/architecture.md (Execution Backend Layer); docs/post_mvp_spec.md (Deferred Features)

**Status:** active

### D-23: Three concentric control layers — enforcement / behavioral / cooperation

**Decision:** Whizzard's controls compose as outer (enforcement, kernel/Docker) → inner (behavioral, harness-native) → innermost (cooperation, Whiz MCP server).

**Rationale:** Each layer has a different shape, owner, and enforcement mechanism; mixing them duplicates harness work or weakens the trust model.

**Source:** docs/architecture.md (Control Layering); docs/control_surface.md

**Status:** active

### D-24: Whizzard does not recreate harness-native behavioral controls

**Decision:** Dangerous-command approval, tool intent gating, `/yolo`, smart-mode aux LLM, and similar in-session interception remain harness-owned. Whizzard does not duplicate them.

**Rationale:** Both Hermes and NanoClaw ship robust behavioral layers; recreating adds surface area for no gain. Layering is the discipline.

**Source:** docs/architecture.md; docs/archive/hermes_research.md; docs/control_surface.md

**Status:** active

### D-25: MCP support is treated as a baseline harness capability

**Decision:** Whizzard assumes all modern agent harnesses support MCP; the Whiz MCP server is a first-class design element, not a per-adapter capability flag.

**Rationale:** Avoids re-deriving the assumption per adapter; reflects observed reality across Hermes, NanoClaw, and Claude-based harnesses.

**Source:** docs/architecture.md; docs/control_surface.md (framing decisions, conversation 2026-05-09)

**Status:** active

### D-26: Cooperation layer never replaces enforcement layer

**Decision:** Capability-change requests via the Whiz MCP server are mediated host-side; structural changes still require stop+restart of the container, not in-place mutation.

**Rationale:** Letting a running agent mutate its own enforcement boundary collapses the trust model.

**Source:** docs/architecture.md (Cooperation layer); docs/control_surface.md

**Status:** active

### D-27: Mid-session capability adjustment = stop+restart

**Decision:** When the user (or agent via MCP) requests a capability change mid-session, Whizzard wraps up the harness, terminates the container, and relaunches with new flags.

**Rationale:** Acceptable friction in exchange for a clean state model; avoids in-place mutation of an active enforcement envelope.

**Source:** docs/control_surface.md (framing decisions, conversation 2026-05-09)

**Status:** active

---

## 4. Adapter contract

### D-28: Adapter is a Python `Protocol`, not an abstract base class

**Decision:** `HarnessAdapter` is a `runtime_checkable` Protocol with positional methods — `start_command`, `container_env`, `working_dir`, `wrap_up`, `health_check_command` — plus a `name` attribute.

**Rationale:** Structural typing is lighter than ABCs and matches the small surface; `runtime_checkable` enables isinstance checks without inheritance.

**Source:** whizzard/adapters/base.py

**Status:** active

### D-29: `wrap_up` is required from MVP, not deferred to v1

**Decision:** Every adapter implements `wrap_up(grace_seconds)`; the generic shell adapter returns `NO_OP`.

**Rationale:** Adding the method later would force an interface change once the Hermes adapter needs it; cheap to define now.

**Source:** docs/architecture.md (Harness Adapter Layer); docs/mvp_build_plan.md (Stage 7)

**Status:** active

### D-30: WrapUpStatus enum has four values — SUCCESS / TIMEOUT / NO_OP / ERROR

**Decision:** Wrap-up outcomes are discrete and enumerated.

**Rationale:** Forces every adapter to map its shutdown semantics into a small known set; avoids ad-hoc string comparisons in the orchestrator.

**Source:** whizzard/adapters/base.py

**Status:** active

### D-31: Adapters must not sleep beyond `grace_seconds`

**Decision:** `wrap_up` implementations must return promptly with TIMEOUT if the harness has not acknowledged within the grace window.

**Rationale:** Wrap-up cannot be allowed to block container termination indefinitely; the grace bound is the contract.

**Source:** whizzard/adapters/base.py

**Status:** active

### D-32: Agent identity is the adapter's responsibility, not core's

**Decision:** Whizzard core does not assume agent identity is available. Adapters tag tool execution with agent identity at the harness boundary; core trusts that claim.

**Rationale:** Per-agent policy needs identity; harnesses Whizzard does not own can't be required to expose it natively. Cryptographic verification is a future problem.

**Source:** docs/architecture.md (Agent Identity)

**Status:** active

### D-33: `harnesses.json` is a versioned schema with required + optional fields

**Decision:** Required: `type`, `start_command`. Optional: `stop_command`, `wrap_up_command`, `wrap_up_grace_seconds`, `working_dir`, `health_check`, `startup_timeout_seconds`, `env`, `description`. Top-level `schema_version`.

**Rationale:** Versioning lets the schema grow without breaking configs; parser must accept and ignore optional fields from day one to avoid breaking changes later.

**Source:** docs/architecture.md (Harness Adapter Schema)

**Status:** active

### D-34: Two harness types — `shell` and `agent`

**Decision:** `harnesses.json` accepts `type: "shell"` (Stage 7) and `type: "agent"` (Stage 8+). Other types are rejected.

**Rationale:** Two types cover all current and planned adapters; new types can be added with a schema bump.

**Source:** whizzard/adapters/__init__.py; docs/stage_validation.md (Stage 7 Step 8)

**Status:** active

### D-35: Initial adapter slate = generic (MVP), Hermes / OpenClaw / NanoClaw (post-MVP)

**Decision:** MVP ships only the generic shell adapter; Hermes is Stage 8; OpenClaw and NanoClaw are post-MVP.

**Rationale:** Prove the abstraction with a trivial adapter before any harness-specific work.

**Source:** docs/architecture.md; docs/post_mvp_spec.md §3

**Status:** active

### D-36: MCP gateway adapter is post-v1 backlog

**Decision:** A future MCP gateway adapter is named in the architecture but not scheduled.

**Rationale:** Direction, not deliverable; pinning a date now is speculative.

**Source:** docs/architecture.md; docs/post_mvp_spec.md §4

**Status:** active

---

## 5. Profiles & mounts

### D-37: Five built-in profiles — safe / default / build / power / quarantine

**Decision:** Bundled profile set is fixed at five named profiles with the documented capability shapes.

**Rationale:** Covers the major usage modes (offline, baseline, dev, power-user, untrusted) without overwhelming users with options.

**Source:** docs/mvp_build_plan.md (Stage 3); whizzard/config.py `_DEFAULT_PROFILES`; docs/session_handoff.md

**Status:** active

### D-38: Default profile is "SAFE-NET" — network on, no mounts, unlimited duration

**Decision:** The `default` profile is the always-on baseline: network enabled, no mounts pre-bound, no duration cap, broad-mount override disabled.

**Rationale:** Useful by default without unrestricted host access; unlimited duration on the productive baseline avoids unnecessary friction for the common case.

**Source:** docs/mvp_build_plan.md (Stage 3); whizzard/config.py

**Status:** active

### D-39: Profile schema is JSON with a versioned envelope

**Decision:** Profiles are stored in `~/.whizzard/config/profiles.json` with a `schema_version` field and a `profiles` map; required keys per profile are `network_enabled` and `duration_seconds` (null = unlimited).

**Rationale:** Versioned JSON is human-editable, parseable, and extensible; required fields force explicit choices.

**Source:** whizzard/config.py

**Status:** active

### D-40: Bundled defaults are in code, copied to user config on `init`

**Decision:** Default profiles ship in the `whizzard.config._DEFAULT_PROFILES` dict; `whizzard profiles init` writes them to disk on demand.

**Rationale:** Always-available defaults work even with no user file; explicit `init` makes customization opt-in and prevents accidental clobber.

**Source:** whizzard/config.py; docs/stage_validation.md (Stage 3)

**Status:** active

### D-41: `profiles init` refuses to clobber without `--force`

**Decision:** If `~/.whizzard/config/profiles.json` exists, `init` exits 1 with a message; `--force` overwrites silently.

**Rationale:** Protect user customizations by default while preserving an explicit reset path.

**Source:** docs/stage_validation.md (Stage 3 Step 3)

**Status:** active

### D-42: Mount registry schema mirrors the profile schema

**Decision:** Mounts are stored in `~/.whizzard/config/mounts.json` with a `schema_version` field and a `mounts` map; required keys per mount are `host_path` and `default_mode` ("ro" or "rw").

**Rationale:** Consistent shape with profiles; versioned for forward compatibility.

**Source:** whizzard/mounts.py

**Status:** active

### D-43: Mounts surface inside the container at `/mounts/<name>`

**Decision:** Every named mount appears at `/mounts/<name>` inside the cell, regardless of host path.

**Rationale:** Predictable in-container path layout; agent does not need to know host-side path; works with the dry-run preview cleanly.

**Source:** whizzard/mounts.py (`CONTAINER_MOUNT_ROOT`); docs/stage_validation.md (Stage 2 Step 4)

**Status:** active

### D-44: `default_mode` caps the maximum permission per mount

**Decision:** A mount registered "ro" cannot be requested "rw" via the CLI; the registry caps permissions, the CLI can only request equal or lower.

**Rationale:** Registry is the source of truth for the permission ceiling; CLI cannot escalate.

**Source:** whizzard/mounts.py (`resolve_mount_spec`); docs/stage_validation.md (Stage 2 Step 6)

**Status:** active

### D-45: Unknown mount names are rejected before launch

**Decision:** A `--mount <name>` referring to an unregistered name produces a clean error and aborts before container start.

**Rationale:** Fail-loud at config time, not runtime; matches the "the registry IS the permission model" framing.

**Source:** whizzard/mounts.py; docs/stage_validation.md (Stage 2 Step 8)

**Status:** active

### D-46: Two-gate broad-mount override

**Decision:** Mounting a path on the override-required tier requires BOTH the profile's `allow_broad_mount: true` AND the CLI flag `--allow-broad-mount`. Either alone is insufficient.

**Rationale:** Profile sets the ceiling; CLI confirms the specific session intent. Two independent gates reduce accidental override.

**Source:** docs/architecture.md (Safety Policy); docs/session_handoff.md; docs/stage_validation.md (Stage 6 Steps 4-6)

**Status:** active

---

## 6. Safety policy

### D-47: Three safety tiers — hard block / override-required / allowed

**Decision:** Mount paths are classified into three tiers with distinct enforcement behavior.

**Rationale:** Cleaner than a binary block/allow; matches the real risk gradient (some paths are categorically wrong, some are user-judgment, most are fine).

**Source:** docs/architecture.md (Safety Policy)

**Status:** active

### D-48: Hard-block list is non-overridable

**Decision:** The hard-block list — `/`, `$HOME`, `~/.ssh`, `~/Library`, Keychains, browser profiles, Docker socket, Whizzard config dir — cannot be overridden by any flag, profile, or preset.

**Rationale:** Some paths are categorically wrong to mount; making them overridable means somebody will override them.

**Source:** docs/architecture.md (Safety Policy); docs/session_handoff.md

**Status:** active

### D-49: Override mechanism is intentional friction; no warning-only middle ground

**Decision:** The override-required tier is "block by default, require explicit user action, log every override." Warnings (which tend to be ignored) are not used.

**Rationale:** Warnings without enforcement degrade quickly; explicit-action gates create a record and force intent.

**Source:** docs/architecture.md (Safety Policy)

**Status:** active

### D-50: Parent-of-registered-mount is override-required

**Decision:** Mounting a path that is the parent directory of any other registered mount is treated as broad-folder override-required, even if the parent itself is not on a static block list.

**Rationale:** Mounting a parent unintentionally widens the agent's view to include all sibling mounts; treat it as a broad-mount decision.

**Source:** docs/architecture.md (Safety Policy); docs/stage_validation.md (Stage 6 Step 7)

**Status:** active

### D-51: Cloud-sync roots (iCloud Drive, Dropbox, OneDrive) are override-required

**Decision:** Cloud-sync roots are on the override-required tier, not the allowed tier.

**Rationale:** A write inside a sync root propagates off-machine; that warrants explicit user intent.

**Source:** docs/architecture.md (Safety Policy)

**Status:** active

### D-52: Symlink targets are resolved before validation

**Decision:** Safety check resolves symlinks before classifying a path against the block lists.

**Rationale:** Otherwise an attacker can register a symlink whose target is a hard-blocked path; resolve-then-check defeats this.

**Source:** docs/architecture.md (Safety Policy); docs/archive/nanoclaw_research.md (comparison table)

**Status:** active

### D-53: Override usage is recorded in the session log

**Decision:** Any override applied to a session is written to `session_start` under `overrides_used` with the reason string.

**Rationale:** Required for the "log every override" half of D-49; makes overrides post-hoc auditable.

**Source:** docs/architecture.md; docs/stage_validation.md (Stage 6 Step 6)

**Status:** active

### D-54: Dry-run is subject to the same safety gates as live runs

**Decision:** Safety errors fire under `--dry-run` exactly as they do under live execution.

**Rationale:** Dry-run is a preview, not a bypass; surfacing errors there is the whole point.

**Source:** docs/stage_validation.md (Stage 6 Step 8)

**Status:** active

---

## 7. Container hardening

### D-55: Container runs as fixed UID 1000 by default

**Decision:** Default in-container user is `whizzard` at UID 1000.

**Rationale:** Non-root containment without per-host configuration; matches the established Linux convention.

**Source:** docs/stage_validation.md (Stage 1); docs/session_handoff.md

**Status:** active

### D-56: Hermes adapter uses scoped UID parity for the profile mount

**Decision:** When the Hermes adapter is in use, the container UID matches the host UID for the Hermes profile mount specifically; other mounts and the rest of the container retain the default UID 1000.

**Rationale:** Hermes self-improvement requires write access to host-side memories/skills/state.db; on raw Linux without Docker Desktop's transparent UID translation, fixed UID 1000 makes those writes fail. Scoped parity preserves writes for the profile mount only.

**Source:** docs/session_handoff.md (Stage 8 design state, item 4)

**Status:** active

**Notes:** Logged in `session_start`. Mirrors NanoClaw's hybrid pattern (UID 1000 unless host UID differs).

### D-57: `--cap-drop=ALL` is mandatory

**Decision:** All Linux capabilities are dropped in every cell.

**Rationale:** Defense in depth; even if an exploit lands inside the container, it has no extra capabilities to leverage.

**Source:** docs/session_handoff.md; docs/control_surface.md (§3); docs/archive/nanoclaw_research.md (comparison)

**Status:** active

### D-58: `--security-opt no-new-privileges` is mandatory

**Decision:** All cells run with `no-new-privileges` set.

**Rationale:** Defeats setuid-binary privilege elevation paths.

**Source:** docs/session_handoff.md; docs/control_surface.md (§3)

**Status:** active

### D-59: Read-only root filesystem with tmpfs scratch

**Decision:** Root filesystem is `--read-only`. `/tmp` and `/home/whizzard` are tmpfs.

**Rationale:** Prevents persistent in-container modification; tmpfs gives the agent the writable space it needs without persisting it.

**Source:** docs/session_handoff.md; docs/stage_validation.md (Stage 1 Step 4); docs/control_surface.md (§3)

**Status:** active

### D-60: Network policy is profile-driven, on/off only in MVP

**Decision:** MVP supports `--network none` (off) or default bridge (on), set per profile. Egress allowlists by host/port are post-MVP.

**Rationale:** Profile-driven on/off is sufficient for the MVP threat model; granular egress requires a sidecar proxy that's a real architectural commitment.

**Source:** docs/architecture.md; docs/control_surface.md (§2)

**Status:** active

### D-61: Whizzard does not use host networking by default

**Decision:** Cells do not run with `--network host`.

**Rationale:** Hermes's own Docker setup uses `network_mode: host` for convenience; that defeats containment. Whizzard explicitly does not.

**Source:** docs/archive/hermes_research.md (Existing Docker setup)

**Status:** active

### D-62: Image base must be hardened (non-root, minimal)

**Decision:** The execution image is built from a minimal base with non-root default user.

**Rationale:** Hardened base is part of the security surface, not a deployment afterthought.

**Source:** docs/control_surface.md (§7); docs/stage_validation.md (Stage 1)

**Status:** active

### D-63: Custom seccomp / AppArmor / SELinux profiles are out of scope for MVP

**Decision:** MVP relies on Docker default seccomp. AppArmor/SELinux are deprioritized indefinitely.

**Rationale:** Linux-only and enterprise-shaped; v1 audience does not include the personas who need this.

**Source:** docs/control_surface.md (§3 and "What's explicitly out of scope")

**Status:** active

---

## 8. Session lifecycle

### D-64: Session log is JSONL with paired start + end records

**Decision:** Sessions are logged as one `session_start` and one `session_end` JSONL record per session, sharing a `session_id`. File path: `~/.whizzard/logs/sessions.jsonl`.

**Rationale:** JSONL is append-friendly, line-parseable, and tail-friendly. Paired records make sessions trivially reconstructable.

**Source:** docs/mvp_build_plan.md (Stage 5); docs/stage_validation.md (Stage 5)

**Status:** active

### D-65: Session ID is a UUID assigned pre-launch

**Decision:** Session ID is a UUID generated before the container starts; surfaced in the banner and stamped on the container as a label (`whizzard.session_id=<uuid>`).

**Rationale:** Allows the container to be located via Docker filters and tied to its log entries even if the host process crashes mid-session.

**Source:** docs/stage_validation.md (Stage 5 Step 1)

**Status:** active

### D-66: Session log captures image_id, container_id, profile, mounts, network, argv, expiry reason, exit status

**Decision:** Required fields in the session log are enumerated in Stage 5; image_id is the resolved sha256 digest, container_id is captured via `--cidfile`.

**Rationale:** "Audit-grade" needs to include enough to reconstruct what ran and what could be done with it; image_id closes the "stale image" risk loop.

**Source:** docs/mvp_build_plan.md (Stage 5)

**Status:** active

### D-67: Pre-flight failures do NOT write a session log entry

**Decision:** If pre-launch validation (unknown profile, missing image, safety violation) fails, no session log entry is written.

**Rationale:** No session ran; logging would clutter the audit trail with non-events. The CLI error message is the audit record.

**Source:** docs/stage_validation.md (Stage 5 Step 7)

**Status:** active

### D-68: Termination flow is wrap_up → SIGTERM → 5s grace → SIGKILL

**Decision:** Session termination sequence: invoke `adapter.wrap_up(grace_seconds)`; then SIGTERM; then a fixed 5s final grace; then SIGKILL.

**Rationale:** Gives the harness its native shutdown path, then a deterministic kill path bounded by configured grace + 5s.

**Source:** docs/mvp_build_plan.md (Stage 5 termination flow)

**Status:** active

### D-69: Each step in the termination flow is logged with timestamps

**Decision:** wrap-up command sent, response received or timeout, duration consumed, and whether SIGTERM was sufficient or SIGKILL was required are all logged.

**Rationale:** Wind-down is the riskiest moment; full timestamps make it auditable.

**Source:** docs/mvp_build_plan.md (Stage 5)

**Status:** active

### D-70: Dry-run does NOT write to the session log

**Decision:** `--dry-run` previews the docker invocation but writes nothing to `sessions.jsonl`.

**Rationale:** Dry-run is informational; session log is for actual sessions.

**Source:** docs/stage_validation.md (Stage 5 Step 1)

**Status:** active

### D-71: Dry-run does NOT check image existence

**Decision:** `--dry-run` prints the full preview even if the referenced image is not built locally.

**Rationale:** Dry-run is for previewing intent; gating on image presence undermines its usefulness during scripting and dry-run-before-build flows.

**Source:** docs/stage_validation.md (Stage 4 Step 5)

**Status:** active

---

## 9. Image management

### D-72: Dockerfile lives at `docker/Dockerfile`

**Decision:** Single Dockerfile at the repo's `docker/` directory.

**Rationale:** Conventional location; one image, one file.

**Source:** README.md (Repository layout); docs/mvp_build_plan.md

**Status:** active

### D-73: Image tag is `whizzard-base:latest` for MVP

**Decision:** The execution image is tagged `whizzard-base:latest`.

**Rationale:** Predictable, scriptable; conventional `:latest` tag for the dev image.

**Source:** docs/stage_validation.md (Stage 1 Step 2)

**Status:** active

### D-74: `whizzard image build` and `whizzard image status` are MVP commands

**Decision:** MVP exposes image management as `image build` (rebuild local image) and `image status` (show current image id, build date, base digest).

**Rationale:** Image provenance must be visible day one; rolling these into a subcommand keeps them discoverable.

**Source:** docs/mvp_build_plan.md (Stage 9 / re-numbered Stage 11)

**Status:** active

### D-75: Image staleness check is post-MVP

**Decision:** `whizzard image check` against a configurable staleness threshold, plus optional auto-rebuild policy per profile, ships in v1.

**Rationale:** Useful but not necessary to prove the MVP thesis.

**Source:** docs/post_mvp_spec.md §6

**Status:** active

### D-76: Image management was Stage 9, becomes Stage 11

**Decision:** The image management stage is renumbered to Stage 11; Stage 9 becomes "Whiz MCP server (read-only subset)" and Stage 10 becomes "Presets."

**Rationale:** B+D value-prop framing pulled MCP read-only and presets into MVP scope; image management is no longer the gating MVP item.

**Source:** docs/control_surface.md (Recent framing decisions, conversation 2026-05-09); conversation 2026-05-09

**Status:** active

### D-77: Base image will be digest-pinned (planned, post-MVP)

**Decision:** The base image reference in the Dockerfile will be pinned by digest (not floating tag) once Stage 11 lands.

**Rationale:** Tag-based pulls can silently change; digest pinning closes that gap. NanoClaw's tag-only choice is explicitly something Whizzard should not borrow.

**Source:** docs/mvp_build_plan.md (Stage 9); docs/control_surface.md (§7); docs/archive/nanoclaw_research.md

**Status:** active

---

## 10. Hermes integration (Stage 8)

### D-78: Hermes integration only through the adapter layer

**Decision:** Hermes is integrated via the adapter contract; Whizzard is not a Hermes wrapper.

**Rationale:** Coupling Whizzard to Hermes (vs. integrating through the adapter abstraction) collapses the layering and blocks future harnesses.

**Source:** docs/mvp_build_plan.md (Stage 8); docs/architecture.md

**Status:** active

### D-79: Whizzard mounts a single Hermes profile directory as HERMES_HOME

**Decision:** The Hermes adapter mounts one Hermes profile directory (`~/.hermes/profiles/<name>/`) into the cell as the contained Hermes's `HERMES_HOME`. It does not mount per-subdirectory.

**Rationale:** `HERMES_HOME` is Hermes's single relocation knob; mounting one profile subsumes per-file decisions and isolates the contained Hermes from the host's default profile.

**Source:** docs/archive/hermes_research.md; docs/session_handoff.md (Stage 8 settled, item 1)

**Status:** active

### D-80: Credentials are injected via env vars; auth.json never enters the cell

**Decision:** API credentials reach the contained Hermes as `<PLATFORM>_TOKEN` env vars via a `--expose-key NAME` flag; `auth.json` is not mounted.

**Rationale:** Hermes's `_apply_env_overrides()` officially supports env-var credential override; this is not a workaround. Keeps host credentials at the boundary.

**Source:** docs/archive/hermes_research.md; docs/session_handoff.md (Stage 8 settled, item 2)

**Status:** active

**Notes:** Vault-mediated credentials (D-100) are the eventual replacement; `--expose-key` migrates transparently.

### D-81: Hermes's approval system is the inner gate; Whizzard does not duplicate it

**Decision:** Hermes's dangerous-command detection, manual/smart approval modes, and `/yolo` remain in force inside the cell. Whizzard's safety policy is the outer gate (mounts, network, container). The two stack.

**Rationale:** Different layers, different decisions; Hermes already does this well.

**Source:** docs/archive/hermes_research.md; docs/session_handoff.md (Stage 8 settled, item 3)

**Status:** active

### D-82: Whizzard does not ship as a Hermes plugin

**Decision:** Whizzard is not implemented as a plugin loaded inside Hermes (`~/.hermes/plugins/`).

**Rationale:** A plugin runs *inside* Hermes; Whizzard runs Hermes inside a sandbox. The directionality is wrong.

**Source:** docs/archive/hermes_research.md (Plugins are NOT a path)

**Status:** active

### D-83: Wrap-up is `/quit` via `docker exec`

**Decision:** Hermes adapter sends `/quit` into the running container via `docker exec` to trigger graceful wind-down; SIGTERM is fallback.

**Rationale:** `/quit` is Hermes's native interactive wrap-up; `docker exec` is the available channel into a running container.

**Source:** docs/architecture.md (harnesses.json `wrap_up_command`); docs/session_handoff.md (Stage 8 settled, item 6)

**Status:** active

### D-84: Two operating modes — interactive and gateway

**Decision:** The Hermes adapter supports both interactive (`hermes chat`) and gateway (`hermes gateway run`) modes.

**Rationale:** Both are real Hermes use cases; user has indicated gateway will be more common but interactive must remain available.

**Source:** docs/session_handoff.md (Stage 8 settled, item 7)

**Status:** active

### D-85: Whizzard profiles and Hermes profiles are orthogonal

**Decision:** Whizzard's "profile" (capability bundle: network, duration, broad-mount) and Hermes's "profile" (full HERMES_HOME directory) are different concepts at different layers and may both be specified per launch.

**Rationale:** Each describes a different thing; collapsing them would lose expressiveness.

**Source:** docs/archive/hermes_research.md (Concrete answers, Q3)

**Status:** active

### D-86: Hermes profile creation UX

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

**Decision:** Gateway is the default. `whiz hermes <profile>` with no mode flag launches `hermes gateway run` inside the cell. Interactive (`hermes chat`) is opt-in via an explicit `--interactive` (or equivalent) flag. **Empty-platforms guard rail:** if the selected profile's `config.yaml` declares no active platforms, gateway-default refuses to start and emits a clear error message that points the user to either configure platforms or pass `--interactive` — gateway-default does not silently fall back to interactive, and does not start an empty daemon.

**Rationale:** Whizzard's center of gravity is users who run Hermes as a 24/7 platform-connected agent (Discord, Slack, etc.), not as a CLI chat tool. Virtually every Hermes installation Bryan has seen or anticipates uses a messaging app as the primary interface; making gateway the default aligns the path of least resistance with the dominant usage pattern, and is consistent with the post-MVP Discord control plane direction. This commits D-89 (platform credential declaration UX) and D-90 (in-session approval routing) to MVP-blocking polish — they are not deferrable, since gateway-default puts both surfaces on the day-one path. The empty-platforms refusal is preferred over silent fallback because gateway-vs-interactive is a meaningful behavior difference and a misconfigured profile should fail loudly, not silently land the user in the wrong mode.

**Source:** docs/session_handoff.md (Stage 8 open #3); docs/archive/hermes_research.md (Open question 3); conversation 2026-05-09

**Status:** active

### D-89: Platform credential declaration UX in gateway mode

**Decision:** Config-implicit with visibility and per-launch restriction:

1. **Source of truth: Hermes's `config.yaml` (inside `HERMES_HOME`).** The Hermes adapter reads it pre-launch to identify the configured platform set and inject the corresponding credential env vars into the cell. Whizzard core never reads `config.yaml` directly (see D-153 for the isolation rule).
2. **Pre-launch capability-visibility banner.** Before container start, Whizzard prints the active capabilities (e.g., `Active platforms: discord, slack`). Content comes from a new adapter Protocol method (e.g., `active_capabilities() -> list[str]`); core prints harness-neutrally.
3. **Per-launch restriction via `--platforms <comma-list>`.** The flag lives under the `whiz hermes` subcommand surface (Hermes-specific, not a core flag — see D-153). It can only shrink the set defined in `config.yaml`; attempting to expand beyond `config.yaml` errors before launch.
4. **Missing-credential warnings.** If `config.yaml` lists a platform but the corresponding host env var (e.g., `DISCORD_BOT_TOKEN`) is unset, Whizzard warns pre-launch. Hermes would fail to initialize the platform anyway; surfacing earlier improves UX and gives the user a clean abort path.
5. **Credential source for MVP: host environment variables.** Whizzard reads the relevant tokens from its own shell environment and passes them through to the cell. Vault-mediated credentials (D-91, D-134) are the post-MVP path.

**Rationale:** Reading `config.yaml` as the source of truth avoids duplicating Hermes's native declaration mechanism — D-10 (harness-neutral core) is preserved because the read happens in the adapter, not core. The visibility banner translates Whizzard's "explicit, human-readable permission boundary" framing (D-11) to the platform-credential capability, which would otherwise be silently inherited from a config file the user may not remember editing. The `--platforms` per-launch restriction gives users a "downgrade for this session" handle without forcing a config edit. Bounding `--platforms` to restriction-only (never expansion) preserves the config-yaml-as-ceiling model and keeps the permission boundary monotonic per launch. Host env vars are the minimum-viable credential source for MVP; OneCLI vault generalization is deferred per D-91. The `--platforms` flag being Hermes-subcommand-scoped (not a core flag) avoids premature abstraction — when a second agent adapter lands, its analog can take whatever shape fits, without retrofitting a generic surface.

**Source:** docs/HANDOFF.md (2026-05-14T14:14Z entry); docs/archive/hermes_research.md (Open question 4, L200); conversation 2026-05-14.

**Status:** active

### D-90: In-session approval routing in gateway mode

**Decision:** Whizzard does not override or route Hermes's in-session approval system; it stays out of the harness-native behavioral control surface (per D-24). The Hermes adapter's posture toward Hermes approvals is:

1. **No mode override.** Whizzard does not inject `--yolo`, does not rewrite the approval-mode field, and does not provide a Whizzard-side equivalent. Whatever the user configured in Hermes (`manual` / `smart` / `off` / `cron`) is what runs.
2. **Pre-launch warning for incompatible mode + gateway combination.** If gateway mode is active (per D-88) and the Hermes adapter reads `manual` as the approval mode, Whizzard emits a clear warning pre-launch: gateway mode has no TTY for interactive y/n prompts; the agent may stall on dangerous-command detection. The warning suggests `smart` mode (Hermes's auxiliary-LLM pre-evaluator), `off` mode (the cell's outer boundary is trusted to constrain), or waiting for Hermes's platform-routed approvals if/when they ship upstream.
3. **Approval mode appears in the capability banner.** The pre-launch banner introduced in D-89 (`Active platforms: discord, slack`) is extended to include the approval mode line, so the user sees the full capability posture before container start.
4. **No Whizzard `--yolo` flag.** Yolo is a Hermes concept; users who want it set it in their Hermes config or pass Hermes's own flag through.

**Rationale:** D-24 ("Whizzard does not recreate harness-native behavioral controls") is the load-bearing principle. Hermes already owns dangerous-command detection, approval-mode policy, and — eventually — platform-routed approval UX. Recreating any of that in Whizzard would duplicate the surface and create drift hazards as Hermes evolves. The narrow value-add Whizzard *can* provide is visibility (D-11: capability grants are human-readable) and a warning at the TTY-incompatibility failure mode, which is a predictable misconfiguration that would otherwise stall the agent silently. Surfacing the approval mode in the banner means the user sees the full capability posture in one place pre-launch, consistent with D-89's visibility principle. Bounding Whizzard's role to "warn, don't override" preserves the cooperation-layer-doesn't-replace-enforcement-layer principle (D-26).

**Source:** docs/HANDOFF.md (2026-05-14T14:14Z entry); docs/archive/hermes_research.md (Open question 5, L92-102, L172-176, L222); conversation 2026-05-14.

**Status:** active

---

## 11. NanoClaw lessons applied

### D-91: Adopt the OneCLI Agent Vault pattern (validated)

**Decision:** Whizzard's vault direction is the OneCLI Agent Vault pattern — credentials never enter the container; outbound HTTPS is routed through a host-side gateway that injects credentials per request.

**Rationale:** NanoClaw's production implementation validates the pattern; integrate with OneCLI rather than building from scratch.

**Source:** docs/post_mvp_spec.md (Vault-Mediated Credentials); docs/archive/nanoclaw_research.md

**Status:** active

### D-92: Mount allowlist outside the project root is an explicit principle

**Decision:** Elevate "the allowlist that defines an agent's permissions must live outside any agent-writable mount" to a named architectural principle, not just an emergent property of the current config layout.

**Rationale:** NanoClaw's external `~/.config/nanoclaw/mount-allowlist.json` is a deliberate defensive choice; making it a named principle prevents future drift.

**Source:** docs/archive/nanoclaw_research.md (Things to learn from NanoClaw)

**Status:** active

### D-93: Whizzard's container hardening is stronger than NanoClaw's, intentionally

**Decision:** Keep `--cap-drop=ALL`, `--read-only`, `no-new-privileges`, tmpfs mounts, and profile-driven network policy as Whizzard differentiators; NanoClaw lacks these and the gap is real.

**Rationale:** Whizzard's value-add over harness-native containment is exactly this hardening layer.

**Source:** docs/archive/nanoclaw_research.md

**Status:** active

### D-94: Whizzard does not adopt NanoClaw's branch-based skill distribution

**Decision:** If Whizzard ever supports skills/extensions, they will be installable artifacts, not git-branch grafts.

**Rationale:** NanoClaw's branch-grafting model fits their fork-and-customize UX; Whizzard's "policy layer that wraps any harness" UX needs a different distribution shape.

**Source:** docs/archive/nanoclaw_internals.md §9.2

**Status:** active

### D-95: Whizzard does not adopt NanoClaw's multi-channel adapter framework

**Decision:** Multi-channel messaging (Discord/Telegram/Slack routing into agents) is harness territory, not Whizzard territory.

**Rationale:** Whizzard contains harnesses; harnesses bring their own multi-channel infrastructure.

**Source:** docs/archive/nanoclaw_internals.md §9.2

**Status:** active

### D-96: Whizzard does not adopt `bypassPermissions` posture for adapters

**Decision:** Adapters must not paper over a harness's own permission model with bypass flags.

**Rationale:** NanoClaw can use `bypassPermissions: true` because the container is its boundary. Whizzard wraps existing harnesses; harness-level permission posture is the harness's call.

**Source:** docs/archive/nanoclaw_internals.md §9.2

**Status:** active

### D-97: NanoClaw adapter is post-v1, not MVP

**Decision:** A NanoClaw harness adapter is on the long-term roadmap but not in MVP or v1 scope.

**Rationale:** NanoClaw's host-side architecture (router/delivery as host process) is more involved than Hermes; defer until Hermes adapter is solid.

**Source:** docs/archive/nanoclaw_research.md (How NanoClaw fits as a harness)

**Status:** active

### D-98: OneCLI vault as v1-must-have (promoted from post-MVP backlog)

**Decision:** Vault-mediated credentials are promoted from "post-MVP backlog" to "v1-must-have" based on NanoClaw's production validation.

**Rationale:** Production-proven pattern; the gap between env-var injection (MVP) and vault-mediated (v1) is the difference between "credentials in process env" and "agent literally cannot exfiltrate."

**Source:** docs/session_handoff.md; docs/archive/nanoclaw_research.md (Bottom line); docs/control_surface.md (§5)

**Status:** active

---

## 12. MVP scope and ordering

### D-99: MVP definition is "9 capabilities" (numbered list in mvp_build_plan)

**Decision:** The MVP is operational when it can do nine specified things — generic shell launch, named mounts, ro/rw modes, profile-driven network, safety policy, dry-run, session logs, generic adapter, image management.

**Rationale:** Concrete acceptance test; the MVP succeeds when it becomes a daily-driver permission harness.

**Source:** docs/mvp_build_plan.md (MVP Definition)

**Status:** active

**Notes:** The stage list expanded after the 2026-05-09 framing change (D-103, D-104, D-76); the original 9-capability statement remains the touchstone.

### D-100: MVP build order is Stage 1 → Stage 11

**Decision:** Stages run in order: shell, mounts, profiles, dry-run, logging, safety, generic adapter, Hermes, MCP read-only, presets, image management.

**Rationale:** Each stage builds on the previous; rearranging would force out-of-order dependencies.

**Source:** docs/mvp_build_plan.md (Build Order); docs/control_surface.md (renumbering)

**Status:** superseded by D-138

### D-101: MVP is a personal daily-driver milestone, not the OSS-launch milestone

**Decision:** The current MVP is a local-testing milestone for personal use. OSS-launch is a later, broader milestone.

**Rationale:** Conflating the two would either bloat MVP or rush an OSS release without enough operational evidence.

**Source:** docs/control_surface.md (Recent framing decisions, conversation 2026-05-09)

**Status:** active

### D-102: Day-1 OSS value prop is the B+D combination

**Decision:** OSS positioning is "B" (define what your agent can touch, see, and do by shaping the environment, not approving every action) plus "D" (switch between named, scoped agent contexts faster than you can type the docker command).

**Rationale:** The combined frame is sharper than either alone; D specifically pulls preset support up into MVP scope.

**Source:** docs/control_surface.md (Recent framing decisions, conversation 2026-05-09)

**Status:** active

### D-103: Presets pulled into MVP as Stage 10

**Decision:** Presets (named bundles of profile + harness + mounts + duration + env) are now MVP scope as Stage 10, not post-MVP §7.

**Rationale:** D in the B+D value prop is delivered through preset-driven switching; without presets, "switch contexts faster than typing docker" is hollow.

**Source:** docs/control_surface.md (framing decisions, conversation 2026-05-09)

**Status:** active

### D-104: Whiz MCP server (read-only subset) pulled into MVP as Stage 9

**Decision:** A read-only Whiz MCP surface — `whiz_status`, `whiz_audit_self`, `whiz_emit_event`, `whiz_list_presets` — is MVP scope as Stage 9.

**Rationale:** Cooperation layer is a first-class part of the design; the read-only subset has no enforcement implications and lands cheaply.

**Source:** docs/control_surface.md (framing decisions, conversation 2026-05-09); docs/control_surface.md §13

**Status:** active

### D-105: Explicit non-MVP features (named list)

**Decision:** GUI, Discord control plane, MCP gateway adapter, per-agent orchestration, breaker engine, shadow-home system, file-tree mount picker, AI risk scoring, and VM orchestration are explicitly out of MVP.

**Rationale:** Keeps MVP narrow; each item has its own post-MVP home.

**Source:** docs/mvp_build_plan.md (Explicit Non-MVP Features)

**Status:** active

### D-106: MVP design discipline — useful, understandable, secure-enough, low-friction, extensible

**Decision:** The MVP success criteria are these five qualities, in that priority order.

**Rationale:** Forces narrow scope; "secure enough" is deliberate (vs. "maximally secure") to keep the MVP shippable.

**Source:** docs/mvp_build_plan.md (Design Discipline)

**Status:** active

### D-107: Dry-run preview must include duration

**Decision:** The dry-run output must explicitly show the effective session duration limit.

**Rationale:** Time-bounded sessions are a primary safety primitive; the user has to see when termination will hit before they launch.

**Source:** docs/mvp_build_plan.md (Stage 4)

**Status:** active

### D-108: Banner shows profile, network, duration, broad-mount override, image, mounts, harness, session ID

**Decision:** The pre-launch and dry-run banner enumerates these fields.

**Rationale:** "What you see is what is granted" — visible permissions are the affordance.

**Source:** docs/vision_and_strategy.md (UX / Mental Model); docs/stage_validation.md (multiple stages)

**Status:** active

### D-137: All five personal-use candidate items pulled into MVP

**Decision:** All five additional control items surfaced as MVP candidates — mid-session stop+restart with capability adjustment, request-side MCP tools, OneCLI vault integration, Discord/mobile control plane, idle timeout — are pulled into MVP scope.

**Rationale:** MVP must clear the personal daily-driver threshold (D-101); these are the items below that threshold. Rather than rank-order them, taking all of them in MVP makes the milestone fully usable for personal daily use.

**Source:** conversation 2026-05-09

**Status:** active; resolves D-130

### D-138: MVP build order is extended to 17 stages

**Decision:** MVP build order is Stage 1 → Stage 17. New stages relative to D-100: Stage 11 = OneCLI vault integration, Stage 12 = stop+restart mechanism + local TTY approval flow, Stage 13 = Whiz MCP server request-side tools, Stage 14 = duration + idle timeout enforcement, Stage 15 = Discord control plane (read-only), Stage 16 = Discord control plane (write + approve flow), Stage 17 = image management (was Stage 11; defers to last).

**Rationale:** Dependency-respecting ordering for the expanded MVP. Vault lands at Stage 11 because it's the strongest single argument for Whizzard's security thesis. Stop+restart precedes request-side MCP because the tools depend on the mechanism. Discord splits into read-only and write/approve stages so the simpler read piece can validate the bot framework before the higher-risk approval flow lands. Image management defers to the end as polish-relative-to-functionality.

**Source:** conversation 2026-05-09

**Status:** superseded by D-143

### D-139: Discord control plane write + approve flow is in MVP

**Decision:** The Discord control plane write/approve flow — start, stop, extend, switch profile, approve mount addition, with single-use time-bounded tokens validated against the initiator's Discord ID — is in MVP scope as Stage 16.

**Rationale:** The original "read-only first" framing was a staging suggestion within Channel B (the Whiz control plane), not a permanent constraint. Bryan wants full Discord-mediated session management at MVP, not deferred to v1. Promotes part of post_mvp_spec.md §2 into MVP; the rest of §2 remains v1.

**Source:** conversation 2026-05-09

**Status:** active

### D-140: MVP capability set is extended beyond the foundational nine

**Decision:** MVP capability set is the original 9 capabilities (D-99) plus: mid-session capability adjustment via stop+restart, agent-facing MCP cooperation surface (read-only and request-side), OneCLI vault credential isolation, Discord/mobile control plane (read + write/approve), idle timeout enforcement.

**Rationale:** D-101 established that MVP is the personal daily-driver threshold; D-137 commits the additional items. This decision is the named extension to the original capability list.

**Source:** conversation 2026-05-09

**Status:** active; extends D-99

### D-141: Whizzard adopts a hybrid generalization path — agent-focused at MVP, explicit "general" mode at OSS-launch

**Decision:** Whizzard's MVP remains agent-focused (Hermes/NanoClaw harness adapters anchor the audience). At OSS-launch, an explicit "general process" mode is added: `harnesses.json` schema accepts any executable, presets shaped for non-agent OSS tools (e.g., "try-untrusted-cli"), marketing positions both agent and general use cases. The architectural foundation already supports this — most stages are harness-neutral; only the Whiz MCP cooperation layer (Stages 9, 14) is agent-specific.

**Rationale:** Three options were considered: A) stay agent-focused with sibling project later, B) general from the start, C) hybrid — agent at MVP, general at OSS-launch. C wins because it preserves MVP focus (sharp use cases drive design) while leaving the broader OSS-tool audience addressable when polish lands. B risks losing focus pre-MVP; A leaves a real gap on the table — there's no good cross-platform low-friction security-shaped container layer for individual developers (firejail/bwrap are Linux-only and config-tedious; Docker alone has no policy/preset/audit layering; devcontainers and Distrobox aren't security-shaped).

**Source:** conversation 2026-05-09

**Status:** active

### D-142: Slash command surface — A, B, C in MVP; D post-MVP

**Decision:** Four slash-command surfaces were considered:

- **A. Host CLI brevity** (`whiz` alias alongside `whizzard`, subcommand shortcuts like `whiz r` / `whiz s` / `whiz p`, smart defaults such as "launch most recent preset" with no args) — in MVP, folded into Stage 10 alongside presets
- **B. Discord and other gateway slash commands** (`/whizzard status`, `/whizzard start`, `/whizzard extend`, etc.) — in MVP at Stages 16–17
- **C. Host-side Claude Code slash commands** (`.claude/skills/` bundle for `/whiz launch`, `/whiz status`, `/whiz adjust`, etc., wrapping the underlying CLI) — in MVP as new Stage 11
- **D. In-agent-chat slash command interception by harness adapter** (user types `/whiz extend 30m` inside their Discord conversation with the agent; adapter intercepts before the agent sees it; forwards to Whiz host-side) — post-MVP

**Rationale:** A, B, C are small, near-orthogonal, and directly reduce daily-driver friction. D is more architecturally consequential — it requires a new adapter contract method (input-side intercept hook), transport-level user authentication, and opt-in design — and benefits from being designed after the Hermes adapter (Stage 8) and Discord control plane (Stages 16–17) are stable. Stage 8 will be designed with D's contract requirement in mind so it's not retrofitted.

**Source:** conversation 2026-05-09

**Status:** active

### D-143: MVP build order extended to 18 stages

**Decision:** MVP build order is now Stage 1 → Stage 18. Stage 10 expands to include CLI brevity (D-142 A); new Stage 11 is Host-side Claude Code Slash Commands (D-142 C); subsequent stages renumber by +1: Stage 12 = OneCLI vault (was 11), Stage 13 = stop+restart + local TTY approval (was 12), Stage 14 = Whiz MCP request-side (was 13), Stage 15 = duration + idle timeout (was 14), Stage 16 = Discord control plane read-only (was 15), Stage 17 = Discord control plane write+approve (was 16), Stage 18 = image management (was 17).

**Rationale:** Slash command surface decisions per D-142. CLI brevity (A) is pure UX with the same theme as presets — folding into Stage 10 keeps stage count from inflating without sacrificing clarity. Claude Code slash commands (C) merit their own stage because the deliverable is a distinct `.claude/skills/` bundle with its own test surface. Image management still defers to last (D-138 rationale unchanged).

**Source:** conversation 2026-05-09

**Status:** active; supersedes D-138

### D-144: Consolidate naming to single "Whizzard" — drop the Airlock/Whizzard split

**Decision:** Drop the two-component naming split. The whole project is named "Whizzard" — orchestrator, policy engine, and containment layer all under one name. The "Airlock" sub-component name is retired. Architecture layers within Whizzard remain (Whizzard Core / Harness Adapter / Execution Backend), but they're internal layering rather than separately-named user-facing components. "Whizzard" itself remains a working placeholder; long-term name TBD.

**Rationale:** The Airlock/Whizzard split was elegant verbally ("Whizzard operates / Airlock governs") but added cognitive load with no benefit — both names mapped to the same codebase, the same `.whizzard` config dir, the same CLI binary. Users had to learn two names to describe one thing. Consolidation simplifies the mental model. The architectural separation between core / adapter / backend is preserved as internal layering inside the architecture doc.

**Source:** conversation 2026-05-09

**Status:** active; supersedes D-04, D-05, partially D-19

### D-145: GitHub repository will rename from `basicagentauth` to `whizzard`

**Decision:** The GitHub repository will be renamed from the placeholder `basicagentauth` to `whizzard`. Rename happens between Claude sessions (executed by the user via `gh repo rename whizzard` from the local working dir, plus `git remote set-url origin git@github.com:BuckG71/whizzard.git`).

**Rationale:** Consolidate naming with D-144. The placeholder repo name added confusion when discussing the project. "Whizzard" is the working name across docs, code, and config; the repo name should match.

**Source:** conversation 2026-05-09

**Status:** active; supersedes D-01

### D-146: Local working directory rename `airlock-warlock` → `whizzard` happens between sessions

**Decision:** The local working directory at `/Users/bg1971/ai-sandbox/airlock-warlock` will be renamed to `/Users/bg1971/ai-sandbox/whizzard`. The rename is executed between Claude Code sessions (not mid-session), to avoid breaking the current session's working-directory binding. Steps: end current Claude session; remove the `crazy-ellis-b21769` worktree (`git worktree remove`); rename the parent directory; start a new Claude Code session pointed at the new path.

**Rationale:** D-03 prohibited mid-session rename for binding-stability reasons; that constraint doesn't apply between sessions. Consolidates the local layout with D-144 and D-145. After rename, Claude Code's auto-memory will live at a new encoded path (`-Users-bg1971-ai-sandbox-whizzard/`); the user must copy memory files from the old path or recreate them.

**Source:** conversation 2026-05-09

**Status:** active; supersedes D-03

---

## 13. Post-MVP & beyond

### D-109: v1.0 has eight named goals

**Decision:** v1.0 goals are: per-agent capability scoping, Discord/mobile control plane, multi-harness rollout, MCP gateway direction, session duration as enforced primitive, image management at runtime, quick-access presets, repo onboarding.

**Rationale:** Stable list anchors post-MVP planning.

**Source:** docs/post_mvp_spec.md (v1.0 Primary Goals)

**Status:** active

**Notes:** Item 7 (presets) and parts of item 5/6 are now MVP scope post-2026-05-09 framing changes (D-103, D-104). The v1.0 list still names them as v1 goals; the tension is documented but not resolved in the source docs.

### D-110: Per-agent policy with local approval before Discord exists

**Decision:** `approval_required: true` on agent policies must have a local terminal-prompt approval path that exists before any Discord bot ships. `--pre-approve` flag for scripted contexts.

**Rationale:** Without local approval, the policy setting is unusable during the v1 build phase; Discord approval is additive, not foundational.

**Source:** docs/post_mvp_spec.md §1 (Approval Flow — Local Path)

**Status:** active

### D-111: Discord control bot is policy-restricted

**Decision:** The Discord bot may start/stop/revoke sessions, request approvals, display status/logs, switch profiles, launch presets — but may NOT execute arbitrary shell, mount arbitrary paths, grant unrestricted permissions, or expose secrets.

**Rationale:** Bot is a control plane, not an execution path; treating it as anything else widens the attack surface.

**Source:** docs/post_mvp_spec.md §2 (Control Plane Responsibilities)

**Status:** active

### D-112: Discord prefers slash commands over `!` legacy commands

**Decision:** Slash commands are the preferred Discord syntax; legacy `!` is optional support.

**Rationale:** Structured inputs, lower parser surface, mobile-friendly, autocomplete; slash commands are the platform's native gesture.

**Source:** docs/post_mvp_spec.md §2 (Discord Command Model)

**Status:** active

### D-113: Discord approval tokens are single-use, time-bounded, identity-bound

**Decision:** "approve NNNN" tokens must be single-use, expire within ~5 minutes, and only accepted from the Discord user who initiated the request.

**Rationale:** Prevents token replay and prevents other server members from approving on someone else's behalf.

**Source:** docs/post_mvp_spec.md §2 (Approval Security Requirements)

**Status:** active

### D-114: Duration hierarchy is session-flag → preset → agent-policy → profile-default

**Decision:** Effective duration is resolved in this priority order, with "no duration" meaning unlimited (logged as such).

**Rationale:** Allows fine-grained override at the moment of launch while preserving sane policy defaults.

**Source:** docs/post_mvp_spec.md §5 (Duration Hierarchy)

**Status:** active

### D-115: Adapter `pre_terminate` hook ships in v1

**Decision:** v1 adds an adapter-level `pre_terminate` callback distinct from `wrap_up`, allowing structured state checkpointing (e.g., serializing conversation history).

**Rationale:** Wrap-up is harness-native shutdown; pre-terminate is for cross-session continuity. Different concerns.

**Source:** docs/post_mvp_spec.md §5 (v1 Additions to Duration Handling)

**Status:** active

### D-116: Full session checkpointing (serialize/resume) is v2

**Decision:** v1 ships only the hooks for checkpointing; full serialize-and-resume across sessions is v2.

**Rationale:** Hook surface is the small piece; the actual serialize/resume is a much larger commitment.

**Source:** docs/post_mvp_spec.md §5

**Status:** active

### D-117: Quick-access presets are a security feature, not just usability

**Decision:** Frame presets as security infrastructure, because secure workflows fail when they are too painful.

**Rationale:** If governance is harder than the bypass, users bypass; low-friction safe paths are part of the safety architecture.

**Source:** docs/post_mvp_spec.md (Operational Philosophy)

**Status:** active

### D-118: Repo onboarding (docs + setup script) is part of v1, not optional polish

**Decision:** v1 ships a getting-started guide, setup script/Makefile target, worked example, profile docs, and a "what is and isn't protected" note.

**Rationale:** Misconfiguration weakens containment; bad setup docs are a security failure, not a docs failure. The setup path should be opinionated.

**Source:** docs/post_mvp_spec.md §8

**Status:** active

### D-119: Phase 3 Breaker uses deterministic heuristics initially, not AI scoring

**Decision:** Initial Breaker implementation uses deterministic heuristics for behavioral interruption; autonomous AI behavioral scoring is explicitly out of initial scope.

**Rationale:** Determinism is debuggable and trustworthy; AI scoring introduces a second AI system inside the safety boundary.

**Source:** docs/vision_and_strategy.md (Phase 3 Breaker, Initial implementation recommendation)

**Status:** active

### D-120: Phase 4 Shadow Home does NOT prove safety

**Decision:** Frame the Shadow Home / decoy environment as a behavior-observation tool, not a safety proof. A malicious system could behave benignly during testing.

**Rationale:** Setting expectations correctly; over-claiming on shadow execution would mislead users about residual risk.

**Source:** docs/vision_and_strategy.md (Phase 4, Important Limitation)

**Status:** active

### D-121: Mount-picker / file-tree browser is post-v1 backlog and human-only

**Decision:** A graphical mount picker is post-v1; agents themselves never browse the host filesystem tree.

**Rationale:** Agent-driven filesystem browsing leaks the structure agents are meant to be blind to.

**Source:** docs/post_mvp_spec.md (Mount Picker / File Tree Browser)

**Status:** active

### D-122: Session replay / audit visualization is post-v1

**Decision:** Visual session replay (commands, mounts, network, approvals, breaker events) is post-v1 backlog.

**Rationale:** JSONL is sufficient for daily use; visualization is polish.

**Source:** docs/post_mvp_spec.md (Session Replay)

**Status:** active

### D-123: AppArmor/SELinux, time-of-day windows, bandwidth caps, multi-party approval, identity-provider integrations are deprioritized indefinitely

**Decision:** These items appear in the control surface but are explicitly deprioritized.

**Rationale:** Enterprise-shaped; OSS Whizzard targets individual / security-conscious developer personas.

**Source:** docs/control_surface.md (What's explicitly out of scope)

**Status:** active

---

## 14. Process & collaboration

### D-124: MVP focus rule — push back on doc tweaks until MVP is operational

**Decision:** Until MVP is operational, the assistant pushes back on documentation-only edits and steers toward implementation. Backlog additions are an explicit exception.

**Rationale:** Doc churn substitutes for shipping; the rule keeps focus on the implementation that proves the thesis.

**Source:** /Users/bg1971/.claude/projects/-Users-bg1971-ai-sandbox-airlock-warlock/memory/feedback_mvp_focus.md (referenced from auto-memory)

**Status:** active

### D-125: One topic at a time

**Decision:** Surfacing a multi-item list is fine, but discuss and resolve them one at a time before moving on.

**Rationale:** Avoids parallel half-resolved threads; matches the user's working style.

**Source:** memory/feedback_one_at_a_time.md (referenced from auto-memory)

**Status:** active

### D-126: Don't push to close items

**Decision:** Stop ending responses with "ready to close X?" prompts; topics close naturally when both parties feel done.

**Rationale:** Closing prompts add friction without speeding resolution.

**Source:** memory/feedback_dont_push_to_close.md (referenced from auto-memory)

**Status:** active

### D-127: Session-handoff doc convention

**Decision:** When approaching the context-window limit, write a comprehensive handoff document (`docs/session_handoff.md`) including verbatim recent turns so a fresh session can resume without re-deriving context.

**Rationale:** Cross-session continuity for a long-running design conversation.

**Source:** docs/session_handoff.md (the document itself, plus conversation 2026-05-08 framing)

**Status:** active

### D-128: Plan-vs-task distinction (plan = stable; task = in-flight)

**Decision:** Source docs (plans) remain authoritative for narrative and rationale; in-flight conversation captures the moment-to-moment decisions, which are then promoted to docs only when stable.

**Rationale:** Avoids constant doc churn; lets conversation move quickly without losing decisions.

**Source:** docs/control_surface.md (Recent framing decisions); docs/decisions.md (this file's preamble)

**Status:** active

### D-129: Decisions are append-only with status updates, not deletion

**Decision:** This decisions document is append-only; superseded entries stay in place with their status changed, not removed.

**Rationale:** Stable cross-references; lets future work cite "D-NN as superseded by D-MM" without breaking links.

**Source:** docs/decisions.md (this file's preamble); conversation 2026-05-09

**Status:** active

### D-147: Merge doc-only commits into main immediately

**Decision:** Doc-only commits (anything touching only `docs/**`, `README.md`, comment-only changes) are fast-forward merged into `main` immediately after commit, without separate confirmation. Code changes still pause for explicit confirmation. Mixed commits follow the code-change path.

**Rationale:** Doc changes are reversible via `git revert`. Holding them adds friction without proportional safety benefit. The user develops directly on main; PR ceremony is not the workflow.

**Source:** memory/feedback_merge_doc_changes.md; conversation 2026-05-09

**Status:** active

### D-148: Pause at UX-shaped stages to design before coding

**Decision:** Stages whose primary deliverable is a user-facing surface — profiles, presets, CLI shortcuts, slash commands, Discord control plane — open with a design conversation before implementation. List candidate affordances, rank by frequency × friction-saved, cut anything below the bar, confirm the slate before code lands. Currently applies to MVP Stages 10 (Presets + CLI ergonomics), 11 (Claude Code slash commands), 16, 17 (Discord), and any future stage introducing user-facing surfaces.

**Rationale:** UX surfaces compound. Bad shortcuts become muscle memory; missing presets become daily papercuts. Once shipped, these are hard to change without breaking habits. Friction at these surfaces undermines the project's core value prop. Throughput on these stages matters less than getting affordances right.

**Source:** memory/feedback_ux_pause_at_design_stages.md; conversation 2026-05-09

**Status:** active

### D-149: `session_handoff.md` is overwriteable, not append-only

**Decision:** `docs/session_handoff.md` captures the current snapshot needed to start a fresh Claude Code session and is rewritten end-to-end each session. It is not a log; do not append. Prior versions are recoverable via `git show <hash>:docs/session_handoff.md` if a rollback is ever needed. Other docs (notably `decisions.md`) remain append-only — this convention applies only to the handoff file.

**Rationale:** A growing handoff file is a worse handoff: stale guidance accumulates, the new-session instructions get buried, and the document loses its "read this first" character. Git already preserves history; the working file should optimize for the next session reading it cold, not for completeness across all sessions. Decisions and validation checklists live in their own append-only docs, so historical context is not lost by overwriting the handoff.

**Source:** docs/session_handoff.md (D-149-pending note); conversation 2026-05-09

**Status:** superseded by D-150

### D-150: `HANDOFF.md` is append-only — supersedes D-149

**Decision:** The handoff doc, renamed `docs/HANDOFF.md`, is append-only. New entries go at the top; prior entries are preserved verbatim. Each entry follows the structure defined by the `/handoff` skill (Goal / Active task / Tried & rejected / Resume protocol) with a target length under 250 words.

**Rationale:** D-149's overwriteable framing was correct for the prior `session_handoff.md` format, which captured comprehensive narrative context (~3000 words) where accumulated entries would have bloated the file unusably. The new HANDOFF format under the `/handoff` skill captures different and much shorter content (~150–250 words/entry), so the bloat concern that justified overwrite no longer applies. Append-only enables cross-session decision archaeology and matches the behavior of every other long-lived doc in the project (`DECISIONS.md`, `STAGE_VALIDATION.md`).

**Source:** conversation 2026-05-09; `/handoff` skill spec

**Status:** active

### D-151: Markdown filenames in this project are uppercase

**Decision:** All markdown filenames in the Whizzard repository are uppercase by convention. Examples: `README.md`, `HANDOFF.md`, `DECISIONS.md`, `ARCHITECTURE.md`, `MVP_BUILD_PLAN.md`. Underscores separate words within the name. Bulk rename of existing lowercase files and the corresponding cross-reference updates are tracked as a separate cleanup commit.

**Rationale:** Consistency with the common GitHub convention for top-level repo docs (`README`, `CONTRIBUTING`, `LICENSE`, `CHANGELOG`), extended uniformly to all project markdown to remove case-recall friction when typing references. The pattern is also visually distinctive against code files in directory listings.

**Source:** conversation 2026-05-09

**Status:** active

**Notes:** Bulk rename pending as a separate commit; cross-references in code/docs must be updated atomically with the rename to avoid broken links.

### D-152: Defense-in-depth against bundled-test-file Skill attacks

**Decision:** (1) `pyproject.toml` declares `norecursedirs = [".agents", ".claude", ".cursor"]` in addition to `testpaths = ["tests"]`, so pytest cannot auto-discover test files inside skill / agent / IDE state directories even if `testpaths` is later broadened. (2) Any Anthropic Skills (or equivalent agent-extension bundles) installed into this repository must be pinned to a specific commit hash, not a branch. (3) Before merging any commit that introduces files under `.agents/`, `.claude/skills/`, or `.cursor/skills/`, reviewers must check for the file shapes that ride the developer-toolchain execution surface — `*.test.*`, `*.spec.*`, `conftest.py`, `__tests__/`, `*.config.*` — and treat any presence as a finding requiring justification.

**Rationale:** Per Gecko Security's disclosure (VentureBeat, 2026-05-09), public Anthropic Skill scanners inspect the agent-execution surface (`SKILL.md`, agent-invoked scripts) but not the developer-toolchain surface (test files auto-discovered by Jest/Vitest/pytest with full local permissions). Whizzard's structural containment addresses the agent-execution side but does not bound the developer toolchain — `npm test` / `pytest` runs on the host, not inside a cell. The MVP scope does not extend to sandboxing developer tooling, so we defend project hygiene through configuration and review. Audit at decision time: `.claude/` contained only `.DS_Store` and `settings.local.json`; `.agents/` and `.cursor/` did not exist; no findings.

**Source:** VentureBeat 2026-05-09 (Gecko Security disclosure on Anthropic Skill scanner blind spot); conversation 2026-05-09

**Status:** active

**Notes:** `.agents/` is *not* added to `.gitignore` because Skills are intended to be committed and shared per upstream convention; the defense lives in test-runner config and pre-merge review.

### D-153: Harness-specific identifiers appear only in adapter modules

**Decision:** Harness-specific paths, filenames, environment variable names, schema field names, and CLI flag names appear only in adapter modules (`whizzard/adapters/<harness>.py`) and the corresponding adapter subcommand surface in `whizzard/cli.py`. Whizzard's core modules — `config.py`, `docker_cmd.py`, `mounts.py`, `safety.py`, `session_log.py`, `harness_config.py` — must not reference Hermes/OpenClaw/etc.-specific identifiers (examples: `config.yaml`, `state.db`, `gateway.lock`, `HERMES_HOME`, `DISCORD_BOT_TOKEN`, `--platforms`). Permitted core knowledge: the harness *type* names registered in `harnesses.json` (currently `"shell"` and `"agent"` per D-34) and the adapter Protocol method names (D-28). Those are the abstraction surface; everything below them is adapter-private.

**Rationale:** D-10 ("Whizzard core stays harness-neutral") is a stance; this decision makes it a reviewable, lint-checkable rule. Without an explicit isolation rule, harness-specific identifiers drift into core as convenient shortcuts ("just read `config.yaml` here, we only have Hermes anyway"), and reverting that drift later becomes a real refactor. Naming the files subject to the rule — and the categories of identifier the rule covers — keeps the adapter pattern load-bearing for the lifetime of the project, including future post-MVP adapters (OpenClaw, NanoClaw, etc.). The adapter Protocol (D-28) is the contract between core and adapters; this is the rule that protects the contract from erosion.

**Source:** conversation 2026-05-14 (during D-89 resolution; Bryan's question on whether config.yaml dependency violates D-10).

**Status:** active

**Notes:** Enforcement is per-PR review for MVP. A lint check (grep-based) is plausible post-MVP if drift becomes a recurring issue.

---

## 15. Open / unresolved

(Status: open across the document — collected here for visibility. Full entries above.)

- **D-130** — Personal-use MVP threshold candidates
- **D-131** — OSS-launch milestone scope
- **D-132** — Sidecar-proxy mechanism in OSS-launch
- **D-133** — Failure-mode semantics across new controls
- **D-134** — OneCLI direct integration in MVP credential injection
- **D-135** — Read-only project-root mounting as a Whizzard pattern
- **D-136** — NanoClaw upstream collaboration

### D-130: Personal-use MVP threshold — additional ○ items to pull in

**Decision:** Which additional surface items rise to MVP for the personal-use threshold (candidates: stop+restart capability adjustment, request-side MCP tools, OneCLI vault, Discord read-only status, idle timeout) is unresolved.

**Source:** docs/control_surface.md (Open items #1)

**Status:** superseded by D-137

### D-131: OSS-launch milestone scope

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

**Decision:** Whether to introduce a sidecar-proxy mechanism in OSS-launch (which unlocks egress allowlists, MCP tool shaping, traffic logging, vault generalization) is unresolved.

**Source:** docs/control_surface.md (Open items #3)

**Status:** open

### D-133: Failure-mode semantics across new controls

**Decision:** Whether to define a single framework-level violation policy (kill / pause / quarantine / continue+log) or per-feature policies is unresolved.

**Source:** docs/control_surface.md (Open items #4)

**Status:** open

### D-134: OneCLI direct integration for MVP credential injection

**Decision:** Whether to integrate with OneCLI directly for MVP-era credential injection (before the full vault backlog item lands) is unresolved.

**Source:** docs/archive/nanoclaw_research.md (Open question 1)

**Status:** open

### D-135: Read-only project-root mounting as a Whizzard pattern

**Decision:** Whether Whizzard should support / recommend NanoClaw's read-only project-root + selective writable subdirs pattern for "containerize my own dev project" use cases is unresolved.

**Source:** docs/archive/nanoclaw_research.md (Things to learn from NanoClaw)

**Status:** open

### D-136: NanoClaw upstream collaboration

**Decision:** Whether to pursue collaboration with NanoClaw upstream (offering Whizzard hardening as a complement to their scope-reduction model) is unresolved.

**Source:** docs/archive/nanoclaw_research.md (Open question 4)

**Status:** open

---

## Cross-references

For narrative context behind clusters of decisions:

- **README.md** — high-level orientation; D-01..D-08 (project naming) and D-09..D-11 (foundational principles) live here in summary form.
- **docs/vision_and_strategy.md** — D-15..D-18 (positioning, audience, what-we-are-not), D-119..D-120 (Phase 3 Breaker, Phase 4 Shadow Home).
- **docs/architecture.md** — D-09..D-14 (foundational principles), D-19..D-27 (architecture & layering), D-28..D-36 (adapter contract), D-47..D-54 (safety policy), D-32 (agent identity).
- **docs/mvp_build_plan.md** — D-37..D-46 (profiles & mounts), D-64..D-71 (session lifecycle), D-72..D-77 (image management), D-99..D-108 (MVP scope).
- **docs/post_mvp_spec.md** — D-91, D-98 (vault), D-109..D-118 (v1.0 goals & requirements), D-121..D-123 (deferred features).
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
- **D-134** — OneCLI direct integration in MVP credential injection
- **D-135** — Read-only project-root mounting pattern adoption
- **D-136** — NanoClaw upstream collaboration
