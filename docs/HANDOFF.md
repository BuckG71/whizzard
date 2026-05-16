# Session Handoff Log

## 2026-05-16T14:03Z — Stage 10 shipped; D-157 default-profile change; outstanding items carried forward

### Goal
Same as prior: ship Stage 8–18 per `docs/mvp_build_plan.md`. Stage 10 (Presets + CLI Ergonomics) shipped today; the next stages whose autonomous execution is blocked by D-148 are 11 (Claude Code slash commands), 16, 17 (Discord). Stage 13/14/15/18 remain autonomous-able.

### Done this session
- **Stage 10 design conversation** (per D-148): four items resolved with Bryan — preset slate, CLI brevity shape, smart defaults, preset config schema.
- **D-157 captured + applied** (commit 51a236c). Default profile's `allow_broad_mount` flipped from `false` to `true` (supersedes D-38 on that field). Bryan acknowledged the OSS-launch revisit implication.
- **Stage 10 #2 shipped** (commit 97a1bc5). `whizzard/preset_config.py` with `Preset` dataclass + omit-to-inherit overrides + bundled `_DEFAULT_PRESETS` (`hermes`, `shell`) + strict `validate_references`. Bundled mount defaults (`claude-projects`, `ai-sandbox`) added to `mounts.py`. 27 new tests.
- **Stage 10 #3 shipped** (commit 4f1eaf6). `whiz preset list | show | init | launch` subcommands. Bundled `hermes-cell` harness added to `_DEFAULT_HARNESSES` so the bundled `hermes` preset validates. `_perform_launch` extracted from `run_cmd` as shared launch core. 14 new tests.
- **Stage 10 #4 + #5 shipped** (commit fd7014d). `whiz status` command (active sessions list + count + last-10 history). Bare `whiz` → status (rather than help). Brevity shortcuts `r`, `s`, `p`, `m`, `pr` with smart dispatch on `whiz r`. `log_session_start` gains `preset` field so bare `whiz r` can find the most recent preset. `pyproject.toml` adds `whiz` script alias. 18 new tests.
- **Build plan + validation docs updated** to mark Stage 10 shipped and document the manual smoke steps (which are blocked on Stage 8 M6 until that lands).

Tests: **291 passing** (was 259 pre-Stage-10 — +32 net new).

### Active task
**Tomorrow's decision:** pick the next stage. Options:

1. **Stage 8 M6 (HERMES_HOME mount + env-var wiring).** Still the highest-priority unblock for end-to-end validation — blocks Stage 8 M7 manual smoke AND Stage 10's `whiz r hermes` end-to-end smoke AND Stage 9's MCP server actually being useful. Autonomous-able, well-defined (~150-300 lines + tests). See `STAGE_8_BUILD_PLAN.md` "Next 3 actions" for the three concrete sub-pieces.
2. **Stage 13 (Stop+restart mechanism + local TTY approval).** Autonomous-doable for the mechanism; TTY approval flow has UX-shape that may benefit from a design pause (not in D-148's explicit list but borderline).
3. **Stage 15 (Duration + idle timeout enforcement).** Cleanly autonomous-able with host-side detection.
4. **Stage 18 (Image management).** Cleanly autonomous-able. Per D-143 it's deliberately last for "polish before audit" reasons; landing earlier is fine but doesn't advance OSS-launch closer.
5. **Stage 11 (Claude Code slash commands)** or **Stage 16/17 (Discord)** — all require D-148 design pauses first.

**My lean:** **Stage 8 M6** is the single highest-leverage next move. It unblocks three different downstream things (M7 smoke, Stage 9 validation, Stage 10 hermes preset end-to-end). Until it lands, the daily-driver `whiz r hermes` won't actually persist Hermes state across launches.

### Tried & rejected this session
- **Modifying default profile in place vs. capturing as new decision.** Captured as D-157 (supersedes D-38 on the `allow_broad_mount` field) per D-129's append-only convention. D-38's status changed to "partially superseded."
- **Adding `whiz preset create` guided-create verb at MVP.** Deferred per the "easy to add/modify" goal being met by direct file edit + `whiz preset init` (D-40/D-41 pattern). Add post-MVP if friction surfaces.
- **Tuple-shaped mount entries in presets `(name, mode)`.** Dropped in favor of flat list of names. Per-launch mode override goes through the existing `--mount name:mode` CLI flag (Stage 2 mechanism). Cleaner schema.
- **Strict profile-name + run-flag mix in `whiz r`.** Rejected; explicit error message instead so users learn the two paths cleanly.

### Outstanding items carried from prior handoffs

From 2026-05-15T03:39Z (Stage 8 M6 gap):
- **Stage 8 M6 — HERMES_HOME mount + env-var wiring.** Newly identified gap; the Hermes adapter has `hermes_home` in its config (used host-side for D-87 gateway.lock pre-check) but never mounts the path into the cell or sets `HERMES_HOME` in the cell's env. Three sub-pieces in `STAGE_8_BUILD_PLAN.md` "Next 3 actions" — Protocol extension with `container_mounts()`, `docker_cmd` consumption, D-56 scoped UID parity wiring.
- **Stage 8 M7 — manual interactive smoke.** Blocked on M6.
- **Stage 8 M8 — packaging closeout.** `pyproject.toml [project.optional-dependencies] hermes = [...]` needs Hermes distribution shape (Bryan's install is a directory tree, not pip-installable; open question what the right pin is).

From 2026-05-15T03:05Z (Stage 9 autonomous build):
- **Stage 9 manual smoke.** Requires `mcp` SDK in execution image + user-added Whiz MCP server entry in Hermes profile's `config.yaml`. Now also blocked on Stage 8 M6.
- **Stage 9 auto-wiring** of the Hermes `config.yaml` MCP server entry (currently manual). Small follow-up.

New from this session:
- **D-157 user-config drift.** Bryan's personal `~/.whizzard/config/profiles.json` still has the old `default` shape with `allow_broad_mount: false`. He'll need to update (manual edit or `whiz profiles init --force`) to pick up the new bundled default for his actual daily use. Code is in shape; user state needs sync.

### Resume protocol
1. Skim today's commits (51a236c, 97a1bc5, 4f1eaf6, fd7014d) to confirm Stage 10 lands as expected.
2. Decide next stage per the five options above (Stage 8 M6 is my lean).
3. If Stage 8 M6: read `STAGE_8_BUILD_PLAN.md` for the three sub-pieces; autonomous-able.
4. If Stage 13: brief design conversation on TTY approval flow shape before coding.
5. `docs/HANDOFF.md` is append-only per D-150. Prior entries reference only.

Prior entries below are reference only.

---

## 2026-05-15T03:39Z — Stage 8 HERMES_HOME gap identified; M6 inserted; manual smoke blocked on it

### Goal
Same as prior: ship Stage 8–18 per `docs/MVP_BUILD_PLAN.md`. Stage 8 + Stage 9 + Stage 12 are shipped (code); Stage 8's manual smoke is blocked on a newly-identified wiring gap that needs to land before end-to-end validation is meaningful.

### What surfaced this session
- Bryan asked whether state and memory persist across cell terminations when the cell uses a cloned Hermes profile.
- The design answer is yes (D-79: HERMES_HOME bind mount → host-side persistence). The *implementation* answer is no: the current Stage 8 Hermes adapter has `hermes_home` in its config (used host-side for the D-87 gateway.lock pre-check) but **never mounts that path into the cell or sets `HERMES_HOME` in the cell's env**. Without that wiring, the cell's Hermes process has no profile to attach to — memories, state.db, skills, sessions would all be ephemeral with the container.
- Concretely: this is the gap that prevents the M6 manual-smoke from being runnable, and would have been caught the moment anyone tried to launch end-to-end with a real container. Unit tests don't catch it because they mock the docker invocation.

### Done this session
- **`docs/STAGE_8_BUILD_PLAN.md` updated** — inserted new **M6: HERMES_HOME mount + env-var wiring (D-79)** as outstanding work. Renumbered old M6 → M7 (manual interactive smoke, now blocked on the new M6) and old M7 → M8 (packaging closeout). Updated "Next 3 actions" to be the three concrete sub-pieces of M6. Updated "Where to resume" to reflect the new state.

### Active task
**Land Stage 8 M6 (HERMES_HOME mount + env-var wiring).** Three sub-pieces, autonomous-able:
1. Extend `HarnessAdapter` Protocol with `container_mounts() -> list[ContainerMount]`; implement on `GenericShellAdapter` (returns `[]`) and `HermesAdapter` (returns the HERMES_HOME mount). Extend `HermesAdapter.container_env` to set `HERMES_HOME=<in-cell-path>`. Unit tests.
2. Wire `docker_cmd.build_run_argv` to call `adapter.container_mounts()` and emit `-v` flags. Unit tests.
3. Wire D-56's scoped UID parity for the HERMES_HOME mount (write-through for self-improvement). Currently a captured design decision without code.

After M6 ships, M7 manual smoke becomes runnable for the first time.

### Outstanding items carried from prior handoffs
From 2026-05-15T03:05Z (Stage 9 autonomous build):
- **Stage 9 manual smoke** — requires `mcp` SDK in execution image + user-added Whiz MCP server entry in Hermes profile's `config.yaml`. Documented in `docs/stage_validation.md` Stage 9 section. Now also blocked on Stage 8 M6 (since the cell needs HERMES_HOME wired before any end-to-end run works).
- **Stage 9 auto-wiring** of the Hermes `config.yaml` MCP server entry (currently manual) — small follow-up; could be a `whiz hermes profile create` flag or a separate command.

From 2026-05-15T02:35Z (Stage 12 + alignment):
- **Stage 8 M8 (was M7): packaging closeout** — `pyproject.toml` `[project.optional-dependencies] hermes = [...]` needs the Hermes Python distribution shape. Bryan's install at `~/.hermes/hermes-agent/` is a directory tree (not pip-installable). Open question what the right pin shape is.
- **Optional**: `whiz hermes <profile>` launch-surface sugar vs. existing `whiz run --harness <name>`. Either works for the smoke test.

From 2026-05-15T03:05Z (next-stage options):
- **Stage 10 (Presets + CLI ergonomics)** — D-148 design pause required before coding.
- **Stage 11 (Claude Code slash commands)** — D-148 design pause required.
- **Stage 15 (Duration + idle timeout)** — autonomous-able if host-side detection is chosen.
- **Stage 18 (Image management)** — autonomous-able; deliberately last per D-143 but can land any time.

### Tried & rejected this session
- **Treat the HERMES_HOME wiring as separately captured / out-of-scope for Stage 8.** It's clearly Stage 8 territory per D-79; inserting as a new M6 rather than punting was the right call.
- **Renumber milestones to keep M6 as "manual smoke"** — would have obscured the fact that the smoke is gated on the wiring work, and would have buried the new work in unnumbered "outstanding" prose. Explicit renumbering makes the dependency visible.

### Resume protocol
1. Read the updated `docs/STAGE_8_BUILD_PLAN.md` "Next 3 actions" — they are the three concrete sub-pieces of M6.
2. M6 is small (~150-300 lines + tests) and autonomous-able. Comparable scale to a single Stage 9 milestone.
3. After M6 ships, decide whether to attempt M7 manual smoke (requires user setup: build image with `mcp` SDK, add MCP server entry to a Hermes profile's `config.yaml`, register Discord token in OneCLI per D-134 — Bryan already has the last one).
4. The other outstanding stages (10, 11, 15, 18) are independent of Stage 8 M6 and can come in any order.
5. `docs/HANDOFF.md` is append-only per D-150. Prior entries are reference only.

Prior entries below are reference only.

---

## 2026-05-15T03:05Z — Stage 9 shipped autonomously after the prior handoff

### Goal
Same as prior: ship Stage 8–18 per `docs/MVP_BUILD_PLAN.md`. Stage 9 (Whiz MCP server, read-only subset) was originally scheduled as a paired build for tomorrow; Bryan opted to keep going and have me ship it autonomously after Stage 12 landed.

### Done since prior entry (Stage 9 autonomous build)
Five milestones, five commits:
- **M1 — MCP server module (c6ba14b):** `whizzard/mcp_server.py` with four tool functions. Tools read env vars for paths; `main()` lazily imports the `mcp` SDK so tests don't need it. 13 tests.
- **M2 — Snapshot writer (4841a2a):** `whizzard/snapshot.py` writes per-session state JSON at launch to `<WHIZZARD_HOME>/sessions/<session_id>/snapshot.json`. 12 tests.
- **M3 — Adapter wiring (2adc3a0):** Added `mcp_env(session_id)` to the HarnessAdapter Protocol. Generic returns `{}`; Hermes returns four WHIZ_* env vars pointing at conventional in-cell `/run/whiz/` paths. Hermes `active_capabilities` mentions MCP. 3 tests.
- **M4 — Event-merge (f765572):** `session_log.merge_agent_events` reads per-session event file and appends to audit log with `origin: agent` enforced. Wired into `docker_cmd.run_shell` before `log_session_end`. 6 tests.
- **M5 — Launch integration (16a30ed):** `cli.py` calls `write_snapshot` before launch. `docker_cmd.build_run_argv` adds the `-v /run/whiz` mounts when `mcp_env` is non-empty + session_id present. `pyproject.toml` adds `mcp>=1.0` as core dep. 3 tests.

Tests: **231 passing** (was 207 at start of Stage 9 — +24 net new). Stage 9 is end-to-end functional on the Whizzard side; the cell-side needs `mcp` in the image and a user-added Hermes `config.yaml` MCP server entry for live verification (documented in `docs/stage_validation.md` Stage 9 section, just added).

### Active task
**Tomorrow:** paired conversation on what's next. Build-plan-order says Stage 10 (Presets + CLI ergonomics) — which is on the D-148 "design-pause-before-coding" list, so it needs a design conversation first. Options:

1. **Stage 10** — design conversation about which presets to ship, CLI shortcut shape (`whiz r` / `whiz s` / `whiz p` per D-142 A), smart defaults.
2. **Skip ahead to autonomous-able non-blocked stages** (Stage 12 done; Stage 15 idle timeout, Stage 18 image management still available).
3. **M6/M7 manual smoke for Stage 8/9** if you want to validate end-to-end before going further.

### Tried & rejected this session
- See prior entry for the substantive strategic threads (harness vs wrapper, NanoClaw fork, NanoClaw as MVP adapter, host-side MCP). All closed today; nothing new rejected during the autonomous Stage 9 build.

### Resume protocol
1. Skim the five Stage 9 commits to confirm the shape matches expectations.
2. Decide on next stage per the three options above (or whatever else).
3. Stage 9 manual smoke (real Hermes container with `mcp` installed + config.yaml MCP entry) can happen any time the image build is updated.

Prior entries below are reference only.

---

## 2026-05-15T02:35Z — Stage 12 shipped; build plan aligned; ready to start Stage 9 together

### Goal
Same as prior: ship Stage 8–18 per `docs/MVP_BUILD_PLAN.md`. Today closed several strategic threads and shipped Stage 12 autonomously. Tomorrow opens with Stage 9 (Whiz MCP server, read-only subset) as a paired build.

### Done since prior entry
- **Build-plan alignment** (commit e6b04db): MVP Definition references D-155 (v1/v2 slate); Stage 8 "open questions" framing replaced; Stage 12 re-scoped from D-91 proxy pattern → cross-adapter OneCLI delivery utility per D-134.
- **D-155 captured** (b677d5e): core-maintained adapter slate is small and curated — generic + Hermes (MVP), NanoClaw (v1.0), native harness (v2.0); others community-maintained via the Protocol. Supersedes D-35 and D-97.
- **D-156 captured** (76ffb39): Whiz MCP server runs in-cell with launch-time snapshot, not host-side socket. Stage 9 architecture settled.
- **Stage 12 shipped** (979aaba): extracted OneCLI plumbing to `whizzard/adapters/_credentials.py`, added env-var fallback per D-134, surfaced credential source in `active_capabilities`. 194 tests pass.

Strategic threads closed today (not new commits — discussion artifacts already in decisions.md): harness-vs-wrapper question (stay wrapper for MVP, native harness at v2.0); maintenance-burden question (cap core slate at 3); NanoClaw-as-MVP-adapter question (no — harder, not easier, despite smaller codebase).

### Active task
Start Stage 9 together. Per D-156, the architecture is settled: in-cell Python MCP server, launch-time state snapshot, mounted live audit logs, event-file write-back for `whiz_emit_event` (merged into host log at session_end). Four tools: `whiz_status`, `whiz_audit_self`, `whiz_emit_event`, `whiz_list_presets` (stub).

### Tried & rejected this session
- **Pivoting MVP adapter to NanoClaw**: smaller codebase doesn't translate to easier adapter; host-side router/delivery mismatch with Whizzard containment; Hermes is the user's daily-driver (D-101 alignment). Stuck with Hermes for MVP per D-155.
- **Forking NanoClaw for a secure-by-design harness**: inherits patterns Whizzard explicitly rejected (D-94, D-95, D-96), language mismatch, threat-model mismatch. Native v2.0 harness inspired by NanoClaw, not forked from it.
- **Host-side MCP server with Unix socket / port IPC**: new attack surface, per-session authorization complexity, long-lived host daemon Whizzard doesn't currently have. In-cell snapshot per D-156.

### Resume protocol
1. Read `docs/STAGE_8_BUILD_PLAN.md` for Stage 8 outstanding (M6 manual smoke, M7 packaging — neither blocks Stage 9).
2. Stage 9 architecture is settled per D-156. Implementation plan to write: probably ~3-4 milestones (scaffold the in-cell MCP server module + snapshot writer + the four tools + Hermes adapter wiring). Comparable scale to Stage 8 but with less design ambiguity.
3. Stage 9 design pause is *not* required per D-148 (it's not in the named list 10/11/16/17). But the in-cell architecture call was treated as a design point and is now captured.
4. Bryan said "we will work on stage 9 together tomorrow" — paired build, not autonomous.

Prior entries below are reference only.

---

## 2026-05-14T20:46Z — DECISIONS.md migrated to flat+tags schema; Stage 8 unchanged

### Goal
Same as prior: ship Stage 8 Hermes adapter end-to-end per `docs/STAGE_8_BUILD_PLAN.md`. Today's work was an orthogonal docs-schema migration; the Stage 8 code state is unchanged.

### Done since prior entry
- **decision-capture skill** rewritten to flat+tags schema with `Type:` / optional `Tags:` / `Door Type:` (renamed from Reversibility, with one-way / two-way framing). Synced between `~/.claude/skills/` and Bryan's Library plugin dir.
- **session-handoff skill** received two small consistency edits (stale `§10` reference in example; `"Open" section` wording in exclusions). Synced.
- **`docs/decisions.md` migrated** (commits d1c40c7 / f30516f / 55ed465):
  - 14 numbered section headers removed (file is now flat, sequential by ID)
  - All 154 entries got `Type:` + `Door Type:` fields; adapter-section entries got `Tags:` (`hermes` or `nanoclaw`)
  - 148 templated Door Type values were refined to per-entry-specific prose, with door direction (one-way / two-way) checked entry-by-entry — several mis-classifications corrected (notably D-22, D-28, D-29, D-32)
  - §15 stale bullet for D-130 (superseded by D-137) cleared
  - Migration script lives at `/tmp/migrate_decisions.py`; one-shot, not committed

### Active task
Resume Stage 8 work where the prior entry left it: M6 manual end-to-end smoke (needs Docker image build + harness config) and M7 packaging (`pyproject.toml` extras for `whizzard[hermes]`). No Stage 8 code changed in this session.

### Tried & rejected
- **Manual per-entry editing of 148 Door Types**: was the initial approach; cost too many turns. Switched to script-with-mapping (one Bash call per ~25-entry batch).
- **Keeping `§15 Open / unresolved` numbered section header**: removed with the others; restored as non-numbered `## Open / unresolved` meta-heading so the bullet list retains context.

### Resume protocol
1. `docs/decisions.md` is now in the new schema. Future captures follow the decision-capture skill (flat append, Type/Tags/Door Type).
2. Pick Stage 8 back up: see `docs/STAGE_8_BUILD_PLAN.md` "Where to resume" — M6 E2E smoke and M7 packaging are the remaining items.
3. The prior `2026-05-14T18:28Z` entry below still describes the current Stage 8 code state accurately.

Prior entries below are reference only.

---

## 2026-05-14T18:28Z — Stage 8 build: code milestones 1–6 shipped; awaits Hermes E2E smoke + packaging

### Goal
Same as prior: ship Stage 8 Hermes adapter end-to-end per `docs/STAGE_8_BUILD_PLAN.md`.

### Done since prior entry
- **Action 3 / M3 (439d062)** — `HermesAdapter.container_env()` reads `self.config["platforms"]`, shells out to OneCLI per platform (`<PLATFORM>_BOT_TOKEN` convention), returns env dict; passthrough of `config["env"]` preserved. New exceptions `OneCLINotInstalledError`, `OneCLISecretMissingError`. `harness_config.py` validates `platforms` field.
- **D-89 amendment (b70b4c0)** — option 3: declarations live in `harnesses.json`, not parsed from `config.yaml`. Pivot driven by real-install inspection of `~/.hermes/config.yaml` revealing no parseable active-platforms field. Avoids replicating Hermes-internal logic per D-153.
- **D-134 resolved (4690708)** — OneCLI integrated in MVP credential injection. Scoped clarification of D-91 for gateway-style harnesses ("delivery mechanism only," not "never enter container").
- **M4 (298ae06)** — `preflight() -> PreflightResult` added to the Protocol. `GenericShellAdapter.preflight()` is always ok. `HermesAdapter.preflight()` reads `gateway.lock` JSON, probes pid liveness via signal 0, blocks on live pid, clears stale pid + announces.
- **M5 (05779b6)** — `whiz hermes profile create <name>` CLI verb. Convention: `default` = `~/.hermes`; other names = `~/.hermes-<name>`. `--clone-from` / `--no-clone`. Clones explicitly exclude `auth.json` (D-80) + per-instance runtime state. Reserved/invalid names + existing targets refused.
- **M6 code (3ac596c)** — `wrap_up()` via `docker stop --time=<grace>` + container exit-code inspection. SIGKILL exit 137 → TIMEOUT; clean exit → SUCCESS; docker errors → ERROR. Resolves the original `/quit`-vs-SIGTERM open question (`/quit` is chat-mode stdin, not a host-runnable command; Hermes's existing SIGTERM handler is the canonical channel).
- **`docs/stage_validation.md`** — Stage 8 section written; previously a placeholder.

Test suite: **185 passing** (was 142 at start of autonomous block). All new test coverage uses `monkeypatch` + `tmp_path`; no real Hermes / Docker / OneCLI binaries required for unit tests.

### Active task
Stage 8 code is functionally complete for all autonomously-doable work. The remaining items need user input or environment:

1. **M6 manual end-to-end smoke test.** Requires the Whizzard Docker image to be built and a real Hermes harness configured in `harnesses.json`. Per the new Stage 8 validation section in `docs/stage_validation.md`, the smoke covers: interactive mode launch (cheapest, no platform creds), gateway mode launch (verifies OneCLI fetch), and the concurrency guard (D-87 live-pid block + stale-pid cleanup).
2. **M7 packaging — `pyproject.toml` extras.** Needs the Hermes Python package name + tested-against version range. Bryan's install at `~/.hermes/hermes-agent/` is a directory tree (`hermes_cli/main.py` is invoked by absolute path in `gateway_state.json`), so the distribution shape isn't pip-package-on-PyPI. Unclear what the right pin looks like — needs Bryan's input.
3. **CLI launch surface — `whiz hermes <profile>` vs. `whiz run --harness <name>`.** Either works for the smoke test. Design call deferred; current code path is `whiz run --harness <name>` which already dispatches to `HermesAdapter` through `build_adapter("agent", ...)`. Adding `whiz hermes <profile>` sugar is straightforward if/when wanted.

### Tried & rejected (this session)
- **Parsing `config.yaml` for active platforms** (original D-89 design intent). Inspection of real `config.yaml` showed it has no parseable active-platforms field — activation involves top-level platform sections, `toolsets:` entries, and internal `check_<platform>_requirements()` logic. Replicating that would violate D-153. Pivoted to harnesses.json declaration (D-89 amended).
- **`docker exec <container> /quit` for wrap_up.** `/quit` is a Hermes chat-mode slash command consumed by Hermes's own stdin, not a host-side command runnable via `docker exec`. Switched to `docker stop --time=<grace>` which delivers SIGTERM and falls back to SIGKILL — clean fit with Hermes's existing SIGTERM handler (drains turns, writes state, exits).
- **Host env vars as MVP credential source.** Resolved D-134 toward OneCLI inclusion in MVP. Gets users off long-lived `.env` plaintext from day one; bounded incremental security but real (no transformational, since for gateway-style harnesses creds still enter the container — D-91's literal "never enter" guarantee scoped to API-using agents).

### Resume protocol
1. **Read `docs/STAGE_8_BUILD_PLAN.md`** for current shape and the M7 outstanding items (now mirrored in `docs/stage_validation.md` Stage 8 section as "Outstanding for full Stage-8 closeout").
2. **Run `pytest tests/`** to confirm the 185 passing baseline.
3. **Decide on M7 packaging shape with Bryan** — specifically how Hermes is distributed (PyPI? git URL? local install assumed?). This determines what `[project.optional-dependencies] hermes` should declare.
4. **Schedule the M6 manual E2E smoke** when the image is built and a Hermes harness is configured in `harnesses.json`. The validation steps are documented under "Manual end-to-end smoke (M6 integration...)" in `docs/stage_validation.md`.
5. **Optional follow-on:** wire up the `whiz hermes <profile>` launch-surface sugar if you want a more Hermes-native CLI verb (vs. the existing `whiz run --harness <name>` which already works).

Prior entries below are reference only. `docs/HANDOFF.md` is append-only per D-150.

---

## 2026-05-14T16:32Z — Stage 8 build paused mid-Action-3 awaiting ~/.hermes access

### Goal
Same as prior entry: ship Stage 8 Hermes adapter end-to-end per `docs/STAGE_8_BUILD_PLAN.md`.

### Active task
Build-plan Action 3 — implement `HermesAdapter.container_env()` to read `<HERMES_HOME>/config.yaml` for active platforms and inject corresponding host env vars (D-89). **Paused before any Action 3 code written**: implementation quality depends on knowing the actual `config.yaml` schema, the real profile directory layout, and the `gateway.lock` / `gateway.pid` formats — all of which live in `~/.hermes` and have not yet been read. Bryan will grant access when back at desk.

### Done since prior entry
- **Action 1 (commit b5302c2)** — `whizzard/adapters/hermes.py` skeleton with all `HarnessAdapter` Protocol methods stubbed; `start_command` defaults to `hermes gateway run` per D-88; `wrap_up` raises `NotImplementedError` rather than misrepresenting as NO_OP. `build_adapter("agent", ...)` now returns `HermesAdapter` instead of raising. All 140 tests passed.
- **Action 2 (commit 96450b6)** — `active_capabilities() -> list[str]` added to the `HarnessAdapter` Protocol (D-89, D-90). `GenericShellAdapter` returns `[]`; `HermesAdapter` returns `[]` as skeleton (Action 3 populates). 142 tests passed.

### Resume protocol
1. Once access is granted, read these paths in `~/.hermes` (one-time inspection — no need to keep open):
   - `~/.hermes/<primary-profile>/config.yaml` — schema for platform declarations
   - `ls -la ~/.hermes/<primary-profile>/` — full file layout (for Action 5's `--clone-from` planning)
   - `~/.hermes/<primary-profile>/gateway.lock` and `gateway.pid` if a host gateway is running (for Action 4 / milestone 4 format confirmation)
   - **Do not read `auth.json`** — D-80 applies to inspection too.
2. Resume Action 3: implement `container_env()` against the real `config.yaml` schema. Map platforms to `<PLATFORM>_BOT_TOKEN` env vars (the D-89 convention) read from `os.environ`. Add unit tests with fixture HERMES_HOME directories covering: happy path, empty platforms, missing credential on host, unreadable config.
3. **Open call to make:** PyYAML is needed for parsing config.yaml. Add it to `[project.optional-dependencies] hermes` in `pyproject.toml` (matching D-131 notes' monorepo+extras direction). Guard the `import yaml` lazily inside `container_env()` so the adapter remains importable without the `hermes` extra installed; method call without yaml raises a clear "install whizzard[hermes]" error.
4. After Action 3 commits, milestone 4 (gateway.lock pre-check) is next per the build plan.

Prior entries below are reference only. `docs/HANDOFF.md` is append-only per D-150.

---

## 2026-05-14T15:53Z — Stage 8 design complete; Hermes adapter build ready to start

### Goal
Ship Stage 8 Hermes adapter end-to-end per `docs/STAGE_8_BUILD_PLAN.md` — `whiz hermes <profile>` launches a contained Hermes (gateway by default, interactive opt-in), with profile creation, concurrency guards, and capability visibility all working per D-86–D-90.

### Active task
Next Action 1 of the build plan: create `whizzard/adapters/hermes.py` with `HermesAdapter` stubbing every `HarnessAdapter` Protocol method (D-28). Wire `whizzard/adapters/__init__.py` to return `HermesAdapter` for `type: "agent"` instead of raising `UnknownHarnessTypeError`. Add one passing instantiation test in `tests/test_hermes_adapter.py`. No design decisions outstanding — pure implementation.

### Tried & rejected
- **Auto-create Hermes profile on first launch** (D-86 Option A): silent state mutation; typo failure mode (`whiz hermes whizard-cell` mistyped spawns a bogus profile).
- **Require user to invoke `hermes profile create` directly** (D-86 Option B): violates "Whiz easier than yolo"; couples Whizzard tightly to Hermes CLI shape.
- **Whizzard core reading `config.yaml` directly**: violates D-10; resolved as D-153 (harness-specific identifiers stay in adapter modules only).
- **Whizzard overriding Hermes's approval system / injecting `--yolo`**: violates D-24; resolved as D-90 (Whizzard warns at TTY-less-gateway misconfiguration but does not override).
- **Multi-repo split at OSS launch** (D-131 sub-question): cross-repo Protocol-change overhead exceeds benefit at current scale; current lean is monorepo + Python packaging extras.
- **Auto-generated adapter fixes / auto-shipped versions** (D-154): safety boundary issue — bot-generated patches on weak test suites would erode the project's trust premise. Humans stay in loop for code changes and releases.

### Resume protocol
1. Read `docs/STAGE_8_BUILD_PLAN.md` for the full plan — Next 3 Actions are the immediate work.
2. Start with Action 1 (adapter skeleton + Protocol stubs + instantiation test). Commit, then move to Action 2 (Protocol extension for `active_capabilities()`), then Action 3 (`container_env()` reading `config.yaml`).
3. All Stage 8 design decisions are in `docs/decisions.md` §10 (D-86 through D-90, all status `active`). Reference by ID — do not re-derive.
4. Cross-cutting rules to enforce during the build:
   - **D-153** — no Hermes-specific identifier (paths, filenames, env var names, CLI flags) appears outside `whizzard/adapters/hermes.py` or the `whiz hermes` subcommand surface in `whizzard/cli.py`.
   - **D-154** — adapter tests organized as smoke / unit / integration tiers; `pyproject.toml` declares a Hermes version range in `[project.optional-dependencies]` from the start.
5. `docs/HANDOFF.md` is append-only (D-150). Prior entry below is reference only — read it for design-phase context, do not edit it.

---

## 2026-05-14T14:14Z — Stage 8 Hermes design (D-88 done, D-86 mid-resolution)

### Goal
Resolve all five Stage 8 Hermes design questions (D-86–D-90) so Stage 8 coding can begin.

### Active task
D-86 sub-question: defaults for `whiz hermes profile create`, framed via existing-Hermes-user migration shapes (Parallel / Migrate / Clean cell). Lean: Option C (Whizzard-native verb, not auto-create and not Hermes-CLI-direct) with `--clone-from default` as the default flag plus `--clone-from <other>` and `--no-clone` escape valves; clone must explicitly omit `auth.json` to preserve D-80. Bryan was about to answer "is Parallel common in the wild, or will most users go straight to Migrate?" — that determines how much weight to give host/cell drift in the docs.

### Tried & rejected
- **D-86 Option A** (auto-create profile on first launch): silent state mutation; typo failure mode (`whiz hermes whizard-cell` mistyped spawns a bogus profile and starts running).
- **D-86 Option B** (require user to run `hermes profile create` themselves): violates "Whiz easier than yolo"; couples Whizzard tightly to Hermes CLI shape across versions.
- **D-88 silent fallback** to interactive mode when no platforms configured: misconfigured profile should fail loudly, not silently land user in wrong mode.
- **Mount user's default Hermes profile directly**: tension with D-80 — `auth.json` lives inside the profile dir and would enter the cell.

### Resume protocol
1. Get Bryan's Parallel-vs-Migrate read.
2. Capture D-86 as resolved in `DECISIONS.md` §10 with the `whiz hermes profile create` verb plus `--clone-from`/`--no-clone` flags; note the `auth.json` omission requirement.
3. Update the open-questions tracker; commit + ff-merge.
4. Ask which of D-87 / D-89 / D-90 to take next.
5. `docs/session_handoff.md` is stale (pre-D-150/D-151 rename); read `docs/HANDOFF.md` instead. `docs/skill-drafts/` holds uncommitted spec drafts Bryan is iterating on — don't move or commit without checking.

Don't push to close D-86 prematurely — the sub-question is real and Bryan steered toward it deliberately.
