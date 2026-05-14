# Session Handoff Log

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
