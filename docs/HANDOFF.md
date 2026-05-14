# Session Handoff Log

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
