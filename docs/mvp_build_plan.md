# Whizzard — MVP Build Plan

This document is the tactical plan for the MVP. It assumes context from:

- [vision_and_strategy.md](vision_and_strategy.md) — the product's why, audience, and long-term direction
- [architecture.md](architecture.md) — system components, layers, safety policy, adapter schema, and architectural invariants

The MVP exists to prove that useful autonomous agents can coexist with practical local security boundaries.

---

## MVP Definition

The MVP is a **personal daily-driver milestone, not the OSS-launch milestone** (D-101). OSS-launch scope is defined separately once MVP is operational.

**Future versions** (per D-155): v1.0 adds a NanoClaw adapter; v2.0 adds a Whizzard-native secure-by-design harness. Other harnesses (OpenClaw, Claude Code, Codex, Cursor, etc.) are community-maintained via the adapter Protocol (D-28) as the open contract. The core-maintained slate is intentionally capped at three.

The MVP is operational when the system can:

**Foundational capabilities (Stages 1–9):**

1. Launch a generic Docker shell under a profile.
2. Mount only approved registered folders.
3. Apply read-only and read-write mount modes.
4. Toggle network access by profile.
5. Reject dangerous mounts per the safety policy.
6. Show dry-run permission previews.
7. Write session logs.
8. Launch a generic harness and a Hermes harness through adapters.
9. Expose a read-only Whiz MCP server so the contained agent can introspect its own constraints.

**Personal-use capabilities (Stages 10–18, added 2026-05-09 per D-137 / D-140 / D-142 / D-143):**

10. Switch between named, scoped agent contexts via presets, with terse CLI shortcuts (`whiz r`, `whiz p`, `whiz s`).
11. Operate Whiz from inside Claude Code via slash commands (`/whiz launch`, `/whiz status`, `/whiz adjust`, etc.).
12. Inject API credentials via OneCLI vault (with env-var fallback when OneCLI is absent).
13. Adjust an active session's capabilities mid-session via stop+restart, with local TTY approval.
14. Expose request-side MCP tools so the agent can ask for capability changes (`whiz_request_mount`, `whiz_request_extend`).
15. Enforce session duration and idle timeout, not just log them.
16. View running sessions, status, and audit logs via a Discord read-only control plane.
17. Start, stop, extend, switch profile, and approve mount additions remotely via Discord write/approve flow with single-use identity-bound tokens.
18. Build, audit, and pin by digest the container image used for execution.

Beyond Stage 18, two **MVP+ stages** (19–20) prepare the system for external review and OSS-launch. They add no new governance capability — they package and harden what the MVP already does — but they are prerequisites for any external eyes. See the **MVP+ — Pre-OSS-Launch Stages** section below; both are the first concrete work of the OSS-launch milestone whose scope D-131 leaves open.

---

## Build Order

### Stage 1 — Generic Docker Shell Launch

Goal: prove contained execution.

Deliverable:

```zsh
whizzard run --profile default
```

Requirements:
- non-root container user
- no host home mount
- no Docker socket
- baseline restrictions active

### Stage 2 — Mount Registry

Goal: human-readable named capabilities.

Example:

```zsh
whizzard run --profile build --mount project-alpha
```

Rules:
- mounts must be registered in `mounts.json`
- no arbitrary host paths
- mount permissions capped by registry

### Stage 3 — Profiles

Initial profiles:
- `safe`
- `default`
- `build`
- `power`
- `quarantine`

Default profile is `SAFE-NET`:
- network enabled
- useful by default
- no unrestricted host access

### Stage 4 — Dry Run

Goal: visible permissions before execution.

Example:

```zsh
whizzard run --dry-run --profile build --mount project-alpha
```

Dry-run output must include:
- profile name and effective capabilities
- each mount with path and mode (ro/rw)
- network mode
- session duration limit (if set)
- any safety warnings or overrides active

Duration must be shown explicitly so the user knows when the session will auto-terminate.

### Stage 5 — Session Logging

Log:
- profile
- mounts
- network mode
- container id
- image id
- session start time
- session duration limit (if set)
- actual session duration
- expiry reason (user exit / timeout / safety termination)
- wrap-up event: command sent, response received or timeout, duration consumed
- whether SIGTERM was sufficient or SIGKILL was required
- exit status

Session duration is a first-class field. Time-bounded sessions are a primary safety primitive and must be enforced, not advisory.

Termination flow:

```text
1. T-minus wrap_up_grace_seconds: adapter.wrap_up() invoked
2. Adapter sends harness-native wrap-up signal, waits for confirmation (bounded by grace)
3. SIGTERM sent to container
4. Short final grace (5s) for clean shutdown
5. SIGKILL if still running
```

Each step is logged with timestamps so a session's wind-down is fully auditable.

### Stage 6 — Safety Validation

Implement the safety policy defined in [architecture.md](architecture.md).

Specifically:
- enforce the hard-block list (no override)
- enforce the override-required list (`--allow-broad-mount`, logged)
- enforce config write-protection (the Whizzard config directory must never be reachable from any agent-writable mount, regardless of `mounts.json`)
- reject any mount path that resolves into the Whizzard config directory

### Stage 7 — Generic Adapter

First adapter: generic shell adapter.

This proves the harness abstraction architecture before any harness-specific integration. The adapter contract and `harnesses.json` schema are defined in [architecture.md](architecture.md).

The MVP adapter interface includes:
- `launch(workspace, config)` — start the harness inside the container
- `stop()` — clean shutdown
- `wrap_up(grace_seconds)` — invoke the harness's native graceful-shutdown mechanism (no-op for generic shell)
- `health_check()` — confirm harness is ready

The wrap_up method must exist from MVP so the Hermes adapter (Stage 8) can implement it without an interface change.

### Stage 8 — Hermes Integration

Hermes integration must occur ONLY through the adapter layer.

Not:
```text
Whizzard = Hermes wrapper
```

Instead:
```text
Hermes adapter → Whizzard core
```

Profile-based isolation: Whizzard mounts a single Hermes profile directory as `HERMES_HOME` rather than mounting individual subdirectories of `~/.hermes`. Credentials inject via env vars; `auth.json` never enters the cell. Stage 8 design is resolved (D-86 through D-90 all `active` as of 2026-05-14); see `STAGE_8_BUILD_PLAN.md` for the build-state detail.

### Stage 9 — Whiz MCP Server (Read-Only Subset)

Goal: give the contained agent a structured, agent-facing interface to introspect its own Whiz-imposed constraints.

Tools shipped at this stage (cooperation layer, all read-only):
- `whiz_status` — current profile, mounts, network policy, expiry, harness, session id
- `whiz_audit_self` — this session's own audit log entries
- `whiz_emit_event` — agent-authored entry appended to the audit log
- `whiz_list_presets` — enumerable presets (Stage 10 dependency)

The MCP server is a first-class part of the design (D-25). Mutate-side tools come at Stage 13.

### Stage 10 — Presets and CLI Ergonomics [SHIPPED 2026-05-16]

Goal: deliver the day-1 OSS value-prop "switch between named, scoped agent contexts" (the **D** half of D-102's B+D combination), with low-friction CLI ergonomics so common operations require minimal typing.

Design conversation per D-148 ran 2026-05-15/16 resolving four items: bundled preset slate, CLI shortcut shape, smart defaults, and preset config schema. See `decisions.md` D-157 for the default-profile change that fell out (allow_broad_mount flipped to true for Bryan's daily-driver setup).

Shipped (commits 51a236c, 97a1bc5, 4f1eaf6, fd7014d):

**Presets** — `whizzard/preset_config.py`. Schema-versioned JSON at `~/.whizzard/config/presets.json`. Omit-to-inherit semantics for profile-field overrides (duration_seconds, idle_timeout_seconds, allow_broad_mount). Bundled defaults: `hermes` (Bryan's daily driver) and `shell` (contained scratch). Strict load-time reference validation against profiles / harnesses / mounts / harness platform ceilings.

**Preset CLI subapp** (`whiz preset list | show | init | launch`):
```zsh
whiz preset launch hermes
whiz preset list
whiz preset show hermes
whiz preset init [--force]
```

**CLI brevity** (D-142 A):
- `whiz` binary alias alongside `whizzard` (pyproject.toml [project.scripts]).
- Shortcuts: `whiz r`, `whiz s`, `whiz p`, `whiz m`, `whiz pr` — preset launch / status / preset list-or-show / mounts list / profiles list.

**Smart defaults**:
- Bare `whiz` → status (rather than help; `whiz --help` is the explicit help path).
- Bare `whiz r` → launch most-recent preset (parsed from sessions.jsonl `preset` field; entry added to log_session_start for this purpose).
- `whiz r <preset>` → preset launch (with `--image` and `--dry-run` honored).
- `whiz r --profile X ...` → equivalent to `whiz run --profile X ...`.
- Mixing positional preset + run-style flags errors with a clear message.
- `whiz p <name>` → preset show; `whiz p` bare → preset list.

**Status command** (`whiz status`): active sessions list with running indicator + active-session count. Recent history table (last 10 starts). Empty-log fallback.

32 net new tests; 291 tests pass total.

Bundled defaults reflect MVP user's setup (D-101 personal-use threshold). OSS-launch will revisit per the same pattern as D-157.

### Stage 11 — Harness Integration Examples (CLI is the primary surface) [SHIPPED 2026-05-19]

Goal: zero-friction Whiz operation from inside any agent harness — by recognizing that the CLI shipped in Stage 10 is already the harness-neutral interface, and delivering copy-paste integration recipes rather than baking harness-specific surfaces into OIQ core.

**Design pivot (D-148 conversation, 2026-05-18).** The original framing was "bundle of `.claude/skills/` recipes" locked to one vendor's harness. An intermediate proposal added a canonical-commands + per-harness-emitter layer plus a host-side MCP server; both were rejected as solving problems the user doesn't have:

- The CLI ergonomics shipped in Stage 10 (`whiz r`, `whiz s`, smart defaults, bare-`whiz` status) already deliver zero-friction operation from any terminal. Any harness can shell out; the user can type directly. Total friction: ~7 keystrokes.
- Per-harness skill/command files belong in user/community config, not OIQ core. Shipping `.claude/skills/` in the package would couple a harness-neutral product to one vendor's directory layout.
- A host-side MCP server would have solved a problem only the *agent* (not the user) has, while introducing a new privilege-escalation surface (any host-side process can connect; cells with smuggled socket access could call `oiq.launch`). Not worth the security cost.

Stage 11 is therefore reframed as a documentation-and-examples stage, not a code-build stage.

**Deliverables:**

1. **`docs/examples/claude_code/`** — production-grade Claude Code integration. A set of `.claude/skills/` files (`oiq-launch`, `oiq-status`, `oiq-preset-list`, `oiq-sessions-tail`, and read-only displays for `oiq-extend`, `oiq-approve`, `oiq-adjust`). Each skill shells out to the OIQ CLI. "Production-grade" because Bryan uses these daily — the MVP user IS a Claude Code user, so the example IS the daily-driver setup.

2. **`docs/examples/hermes/`** — production-grade Hermes integration. The Migrate recipe: a working `harnesses.json` snippet for `hermes-cell`, a working `presets.json` entry (the `hermes` preset already bundled in Stage 10), a profile-cloning walkthrough (host `~/.hermes` → `~/.hermes-whizzard-cell` via `oiq hermes profile create`), OneCLI credential setup (D-134), and the step-by-step "go-live" sequence (stop host Hermes → clone profile → first OIQ-wrapped launch). "Production-grade" because Hermes IS our MVP target adapter — the example IS the validation path.

3. **`docs/examples/README.md`** — index of examples, with stubs and contribution invitations for `docs/examples/codex/`, `docs/examples/cline/`, `docs/examples/openclaw/`, etc. Lowers community-contribution friction.

4. **Root README section "Using OIQ inside your agent harness"** — describes the integration pattern (CLI shell-out from harness commands/skills), points at `docs/examples/`, invites PRs for additional harnesses.

**Mutating skill behavior** (extend, approve, adjust) ships when the underlying CLI verbs land (Stage 13 for extend/adjust; Stage 14 for approve). The Stage 11 closeout deliberately omitted "read-only display" placeholders for the not-yet-existent verbs — placeholders that error with "not yet implemented" aren't useful. They'll be added as new skill files when the verbs ship.

**No new pip dependencies. No core code changes.** Stage 11 was documentation work plus example-file authoring. The CLI was the deliverable; Stage 11 is the showcase.

**Shipped 2026-05-19.** Nine files in `docs/examples/`: top-level README, `claude_code/README.md`, four skill files (`oiq-launch`, `oiq-status`, `oiq-presets`, `oiq-sessions-tail`), `hermes/README.md` (full migration walkthrough), `hermes/harnesses.json.example` (`hermes-cell` + `hermes-cell-smoke` entries), `hermes/config.yaml.snippet` (Ollama provider via `host.docker.internal`). Root README gains a "Using OIQ inside your agent harness" section pointing at the examples directory.

### Stage 12 — OneCLI Credential Plumbing (Cross-Adapter Generalization + Fallback)

Goal: make OneCLI credential injection a reusable adapter utility, with a clean fallback when OneCLI isn't available.

Stage 8 shipped OneCLI integration scoped to the Hermes adapter — the credential-fetch shell-out and per-platform `<PLATFORM>_BOT_TOKEN` injection live in `whizzard/adapters/hermes.py` (per D-89 amended and D-134). Stage 12 generalizes the pieces that aren't Hermes-specific into a shared adapter utility so future adapters (v1.0 NanoClaw, v2.0 Whizzard-native harness, community adapters) can use the same primitives without re-implementing them.

Deliverables:

- **Extract `_fetch_secret_via_onecli` and related helpers** from the Hermes adapter into a shared adapter utility module (e.g., `whizzard/adapters/_onecli.py`). Surface stays adapter-private per D-153 — core modules don't reference it — but the utility is shared across adapters.
- **Env-var fallback path.** When OneCLI isn't installed (or returns no matching secret), fall back to reading the corresponding env var directly from the host with a warning logged to the session record. Per D-134's "OneCLI not installed" failure-mode note.
- **Pre-launch surfacing.** `active_capabilities()` on each adapter using the utility flags whether credentials came via OneCLI, host env, or neither (the last is an error).
- **Refactor Hermes adapter** to consume the extracted utility (delete the duplicate code from `adapters/hermes.py`).

**NOT in this stage:** the proxy-based "credentials never enter container" pattern from D-91. That pattern applies to "agent uses external API" use cases (NanoClaw shape — D-91's scope per D-134's clarification), which lands in v1.0 alongside the NanoClaw adapter, not MVP.

The original Stage 12 framing (proxy pattern via `HTTPS_PROXY`) was based on D-91's literal "credentials never enter container" guarantee. D-134 clarified that for gateway-style harnesses — Hermes, the MVP target — OneCLI's role is delivery-mechanism only, not proxy-based interception. The proxy pattern is preserved for v1.0 NanoClaw adoption per D-155's slate.

Promoted to MVP per D-98 (vault is v1-must-have). Lands at this position because credential isolation hygiene — even bounded — is the strongest single argument for Whiz's security thesis (D-102 / B).

### Stage 13 — Stop+Restart Mechanism + Local TTY Approval Flow [SHIPPED 2026-05-19]

Goal: change a running session's capabilities without losing the session.

Mechanism (D-27): adapter.wrap_up() → terminate → relaunch with new flags. The session is logically continuous from the user's perspective even though the container is replaced. Approval is a local TTY prompt for MVP; Discord approval comes at Stage 17.

Design + UX details captured in D-163 (Stage 13 design conversation). Shipped surface:

```sh
whiz adjust <session-id> --add-mount foo[:mode]
whiz adjust <session-id> --remove-mount bar
whiz adjust <session-id> --extend 30m
whiz adjust <session-id> --allow-broad-mount --add-mount documents
whiz adjust <session-id> --yes    # skip approval prompt (for scripting)
```

Implementation: `whizzard/adjust.py` (library: Changes/MountAddition/Approver/AdjustResult, parse_duration, resolve_session, detect_noops, render_diff, adjust_session orchestration, AGENT_DENIED_CHANGES + check_agent_allowed for Stage 14 forward-compat) + `whizzard/cli/adjust.py` (CLI command + tty_approver). 41 new tests; total 352 unit tests passing; integration tier still green.

Stage 14 hooks in place:
- Pluggable `Approver` interface (Stage 14 adds an MCP-mediated approver)
- Library-shaped `adjust_session(...)` callable from both CLI and MCP paths
- `AGENT_DENIED_CHANGES = frozenset({"allow_broad_mount", "change_profile"})` filter applied when `agent_initiated=True`

Forward-looking: `--extend` records the new duration in the adjustment log entry but isn't actively enforced until Stage 15 lands the duration-enforcement mechanism. Interactive sessions (vs. gateway-mode daemons) experience a terminal-disconnect during adjust — documented as a known limitation; users on interactive sessions can re-attach with `docker attach <cid>` or run interactive sessions via tmux.

### Stage 14 — Whiz MCP Server (Request-Side Tools) [SHIPPED 2026-05-21]

Goal: agent-initiated capability requests.

Design captured in D-165. The contained agent calls MCP request tools that drop a JSON request file into a per-session channel inside the `/run/whiz` mount (D-156 event-file pattern); the host picks them up on-demand via the operator-invoked `whiz requests` command — no background watcher (keeps Whizzard CLI-driven, per D-156's daemon rejection). A host-side MCP server giving synchronous round-trip request calls is the planned v1.0 revisit.

Shipped surface:

```sh
whiz requests                  # list pending agent requests (all sessions)
whiz requests list --all       # include resolved (applied/denied) requests
whiz requests approve <id>     # approve + apply via Stage 13 stop+restart
whiz requests deny <id>        # decline without applying
```

In-cell MCP tools added (`whizzard/mcp_server.py`):
- `whiz_request_mount` — agent requests a registered mount be added
- `whiz_request_extend` — agent requests a duration extension
- `whiz_check_request` — agent polls a prior request's outcome

Implementation: `whizzard/mcp_server.py` (3 new tools + `WHIZ_REQUEST_DIR` env var), `whizzard/requests.py` (host-side reader / pre-flight validator / `process_request`), `whizzard/cli/requests.py` (`whiz requests` sub-app), Hermes adapter `mcp_env` wiring, `whiz status` pending-request count. Approved requests route through `adjust_session` with `agent_initiated=True`, so the `AGENT_DENIED_CHANGES` filter (D-163) blocks broad-mount / profile changes from the agent path. Requests are pre-validated host-side before any stop+restart — a request needing a broad-mount override is denied with the session still running. 55 new tests; 407 unit tests passing; 85% coverage; integration tier still green.

Depends on Stage 13 substrate. Network-egress-allowlist requests (`whiz_request_network`) require sidecar proxy and remain post-MVP.

### Stage 15 — Duration + Idle Timeout Enforcement

Goal: time-bounded sessions become enforced (not just logged).

Requirements:
- hard duration cap kills the container at expiry
- idle timeout kills the container after N minutes with no agent activity
- both write to session log with expiry reason
- pre-expiry warning at configurable lead time

Builds on the duration tracking already present from Stage 5.

### Stage 16 — Discord Control Plane (Read-Only)

Goal: see what's running from anywhere.

Bot framework + Discord auth + read-only commands:
- `/whizzard status` — list running sessions, current profile/mounts/expiry per session
- `/whizzard sessions list` — recent session history
- `/whizzard logs tail <session-id>` — tail the audit log for one session

Reads are queries against `~/.whizzard/logs/sessions.jsonl` plus live process state. No mutation.

The Whiz control plane channel must be separate from the agent interaction channel (architecture invariant — agents do not manage their own permissions, [post_mvp_spec.md §2](post_mvp_spec.md)).

### Stage 17 — Discord Control Plane (Write + Approve)

Goal: full Discord-mediated session management.

Mutating commands:
- `/whizzard start` — launch a session (preset or explicit args)
- `/whizzard stop <session-id>`
- `/whizzard extend <session-id> <duration>`
- `/whizzard switch-profile <session-id> <profile>` — implemented via Stage 13 stop+restart
- `/whizzard approve <token>` — approve pending mount addition or other capability request

Approval token security (per D-113): tokens are single-use, expire after 5 minutes, validated against the Discord user ID that initiated the session request.

### Stage 18 — Image Management

Goal: prevent stale or unknown images from undermining containment.

Requirements:
- base image digest pinned in `Dockerfile` (not floating tag)
- `whizzard image build` to build/rebuild the local image
- `whizzard image status` to show current image id, build date, base digest
- `whizzard image check` to compare current image age against staleness threshold
- session log records the image id for each session (already implemented in Stage 5)

Stale images are a silent risk: a compromised or outdated base image defeats the containment model regardless of policy correctness. Image provenance must be visible and auditable.

This stage was originally Stage 9, then Stage 11, then Stage 17; it now lands at Stage 18 (D-143). It's polish-relative-to-functionality compared to the personal-use capability stages and benefits from being the last MVP stage so the security audit before OSS-launch starts from a fully digest-pinned baseline.

---

## MVP+ — Pre-OSS-Launch Stages

Stages 19–20 are **not part of the MVP** — the MVP is operational at Stage 18. They are the first concrete work of the OSS-launch milestone whose scope D-131 leaves open. Neither stage adds a governance capability; together they make the MVP installable by someone other than the maintainer and verify the containment model before any external exposure.

Sequencing: Stage 19 must land before the project is shared with reviewers (they need an install path). Stage 20 is the final gate before public launch — it comes after Stage 19 because the published artifact and install path are themselves attack surface, and it folds in reviewer findings.

### Stage 19 — Packaging & Install

Goal: a person who is not the maintainer can install and run Whizzard from a published artifact, without cloning the repo or knowing the dev workflow.

Until this stage the only install path is the README's "Install (development)" — clone + `pip install -e ".[dev]"` — which is correct for the D-101 personal-use threshold (the MVP user IS the maintainer) but unusable for reviewers or the public.

Deliverables:

- **Published Python distribution.** Build sdist + wheel from the existing `[build-system]`; publish to an index. The reviewer round uses TestPyPI or a tagged pre-release; public launch uses PyPI. The `whizzard` / `whiz` console entry points already exist in `pyproject.toml`.
- **Execution-image distribution.** Decide and implement one of: publish a digest-pinned execution image to a registry (e.g. GHCR) so users pull rather than build, or make `whizzard image build` a bulletproof, well-messaged first-run step. Ties directly to Stage 18 digest pinning. The Hermes image (`docker/Dockerfile.hermes`) gets the same treatment or a clearly documented build step.
- **Clean-machine install verification.** A documented, tested end-to-end path on a fresh environment: install → `whizzard image build`/pull → `whizzard run` → containment confirmed. The README gains a user-facing "Install" section distinct from "Install (development)".
- **First-run / no-config experience.** With no `~/.whizzard/config/` present, the CLI guides the user through config init and image setup instead of erroring cryptically. Bare `whiz` already maps to status (Stage 10); add the no-config fallback.
- **Release hygiene.** Tagged release, `CHANGELOG.md` entry, version bump (`pyproject.toml` is the version source of truth, D-07). The release build runs in CI and is reproducible.
- **Reviewer-distribution mechanism.** Pick and document how pre-launch reviewers receive the build (TestPyPI install, private wheel, or tagged pre-release) and the feedback channel they use.

Rationale: this stage closes the "no install story at all" gap — currently wider than the structural Docker-floor friction, because nothing ships at all. It is a hard prerequisite for external review and the first deliverable of the D-131 OSS-launch milestone.

### Stage 20 — Security Review & Hardening Audit

Goal: adversarially verify the containment model before any public exposure. Whizzard's entire value proposition is that the permission boundary holds; this stage is where that claim is *tested* rather than asserted. Stage 18's closing note anticipates "a security audit before OSS-launch" — this is that audit, scoped.

This is the final pre-launch gate. Expect findings to reopen earlier coding work; doing it before launch rather than after is the point.

Deliverables:

1. **Consolidated threat model** (`docs/threat_model.md`). architecture.md states the invariants but scatters the adversarial view. Consolidate it: adversaries (a malicious agent or skill inside the cell, a malicious harness, a hostile registered-mount payload), assets (host filesystem outside mounts, credentials, the Whizzard config directory, the host control plane), trust boundaries, and the explicit non-goals (a shadow environment does not prove safety, etc.).

2. **Adversarial ("red-team") test suite**, committed as permanent regression tests — one cluster per invariant, each test failing if the invariant breaks:
   - *Containment escape* — Docker socket unreachable; privilege escalation blocked; `no-new-privileges`, capability drops, non-root user, and `--read-only`/tmpfs actually applied to the launched container.
   - *Config write-protection* — the foundational invariant (architecture.md): the config directory is unreachable from any agent-writable path via symlink, `..` traversal, parent-directory mount, or snapshot/event-file poisoning. Heaviest coverage here.
   - *Mount boundary* — a registered mount cannot be widened via symlink or traversal; read-only mounts are genuinely read-only.
   - *Network policy* — network-off means no host reachability (`host.docker.internal`, the Docker bridge, DNS).
   - *Cooperation-layer abuse* — `AGENT_DENIED_CHANGES` (broad-mount, profile change) cannot be bypassed from the agent path; request files in `/run/whiz` cannot be forged to mimic operator approvals; no injection via mount/preset names in request JSON.
   - *Stop+restart / adjust* — the agent cannot influence relaunch flags; the carried snapshot cannot be poisoned to gain capability; the approval flow cannot be spoofed.
   - *Discord control plane* — approval tokens are single-use, expiring, and identity-bound (D-113); the control channel is separate from the agent channel; no command injection via message content.

3. **Fail-closed audit.** This stage must close D-133 (framework-level failure-mode policy, currently open). The strong default for a security product is fail-closed: any safety-relevant path — safety validation, mount resolution, network configuration, image checks — that throws or is indeterminate aborts the launch rather than proceeding with a weaker boundary. Includes verifying the dry-run preview cannot diverge from the actual launch: the preview and the real `docker run` invocation must resolve from one code path. A preview that lies is a security bug.

4. **Injection / command-construction audit.** `docker_cmd.py` and every site where user- or agent-supplied input (mount names, profile/preset names, session IDs, durations) flows into a subprocess: argument-injection into `docker run`, no shell-string construction, strict input validation at the boundary.

5. **Credential-handling audit.** `auth.json` never enters the cell (D-80); credential values never reach session logs, `harnesses.json`, or any agent-readable file; the OneCLI env-var fallback does not over-expose.

6. **Supply-chain scan, wired into CI.** `pip-audit` (or equivalent) over the dependency tree on every push; base-image and Hermes-image digest pinning verified (Stage 18); the Stage 19 published artifact is in scope.

7. **Independent review pass.** Run the repo's `security-review` tooling over the full diff, and route the consolidated threat model plus the installable build to the external reviewers. Triage all findings: launch-blockers fixed within this stage; non-blockers captured as decisions or backlog items.

Exit criteria: every invariant in architecture.md "Architectural Constants" has at least one adversarial test that fails if the invariant is broken; all launch-blocker findings resolved; CI runs the adversarial suite and the dependency scan on every push.

Rationale: for a containment product, "the boundary holds" must be a tested, regression-protected property, not a design assertion. This stage is the trust gate between a working personal tool and a publicly launched security product — and it (plus reviewer turnaround), not feature velocity, is the critical path to launch.

---

## Repository Structure

```text
whizzard/
  README.md
  pyproject.toml

  whizzard/
    cli.py
    config.py
    docker_cmd.py
    safety.py
    logging.py
    adapters/
      generic.py
      hermes.py

  config/
    profiles.json
    mounts.json
    harnesses.json

  docker/
    Dockerfile

  scripts/
    whizzard-safe
    whizzard-default
    whizzard-build
    whizzard-power

  docs/
    vision_and_strategy.md
    architecture.md
    mvp_build_plan.md
    post_mvp_spec.md

  tests/
```

---

## MVP Acceptance Test

The MVP passes if these commands behave as specified:

**Foundational (Stages 1–9):**

```zsh
whizzard run --profile safe
whizzard run --profile default
whizzard run --profile build --mount project-alpha
whizzard run --dry-run --profile build
whizzard run --profile build --harness hermes
whizzard adapters list
whizzard profiles list
whizzard mounts list
whizzard harnesses list
whizzard sessions tail
```

**Personal-use (Stages 10–18):**

```zsh
whizzard preset launch coding-session
whiz r                                                 # smart default: launch most-recent preset
whiz s                                                 # subcommand shortcut: sessions tail
whizzard run --profile build --vault                  # OneCLI vault on
whizzard adjust <session-id> --add-mount foo
whizzard adjust <session-id> --extend 30m
whizzard sessions list
whizzard image status
whizzard image check
```

**Claude Code slash commands (Stage 11):**

```text
/whiz launch coding-session
/whiz status
/whiz preset list
/whiz sessions tail
/whiz extend <session-id> 30m
/whiz adjust <session-id> --add-mount foo
/whiz approve <token>
```

**Discord control plane (Stages 16–17):**

```text
/whizzard status
/whizzard start preset:coding-session
/whizzard stop <session-id>
/whizzard extend <session-id> 30m
/whizzard approve <token>
```

And:
- dangerous mounts are blocked per the safety policy
- logs are written for every session, including capability adjustments
- containerized execution works for both shell and Hermes harnesses
- network mode changes by profile
- host home directory is inaccessible
- adapter abstraction is preserved
- image provenance is recorded for every session
- credentials never enter the container when the vault is in use
- duration and idle timeouts are enforced (not just logged)
- agent-initiated `whiz_request_*` MCP calls go through the local TTY approval flow (or the Discord approval flow when the control plane is up)
- Discord control plane channel is separate from agent interaction channel

---

## Explicit Non-MVP Features

Do NOT build during MVP:
- GUI
- MCP gateway adapter (governed MCP runtime for arbitrary harnesses — distinct from the Whiz MCP server in Stages 9 and 13)
- Per-agent orchestration (per-agent capability scoping comes via Whiz profiles + presets in MVP; full multi-agent identity is post-MVP)
- Breaker engine
- Shadow-home system
- File tree mount picker
- AI risk scoring
- VM orchestration (Podman / Firecracker / Apple Virtualization Framework)
- Network egress allowlists, MCP tool shaping, traffic logs (all require sidecar-proxy mechanism — post-MVP / post-OSS-launch)
- AppArmor / SELinux profiles, time-of-day windows, bandwidth caps, multi-party approval, identity-provider integrations (deprioritized indefinitely per D-123 — enterprise-shaped)

The Discord control plane was previously listed here; it moved into MVP at Stages 15–16 per D-137 and D-139.

These belong to post-MVP phases. See [post_mvp_spec.md](post_mvp_spec.md) and [vision_and_strategy.md](vision_and_strategy.md).

---

## Design Discipline

Keep the MVP narrow.

Primary success criteria:
- useful
- understandable
- secure enough
- low-friction
- extensible

The MVP succeeds if it becomes a practical daily-driver permission harness for local agents.
