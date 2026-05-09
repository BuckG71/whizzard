# Session Handoff — 2026-05-09

> **Current snapshot. Supersedes prior versions in git history.** This document is overwriteable each session per D-149-pending convention (decided 2026-05-09; will be captured as a numbered decision in the next session). Roll back via `git show <hash>:docs/session_handoff.md` if you ever need a prior version.

Comprehensive context for picking up the thread in a new Claude Code session. Read this first; it points to the canonical docs for everything else.

---

## Quick orientation

If you're a new Claude Code session reading this:

1. The user is **Bryan Garrett** (`bgarrett.work@gmail.com`, `BuckG71` on GitHub).
2. The project is **Whizzard** — a local capability-governance layer for AI agents, with a post-MVP path to general OSS-tool sandboxing. "Whizzard" is a working placeholder name; the project may rename before OSS launch.
3. **Repo:** `github.com/BuckG71/whizzard` (renamed 2026-05-09 from `basicagentauth` per D-145).
4. **Local working directory:** `/Users/bg1971/ai-sandbox/whizzard` (renamed 2026-05-09 from `airlock-warlock` per D-146).
5. **Claude Code auto-memory:** `~/.claude/projects/-Users-bg1971-ai-sandbox-whizzard/memory/`. Should auto-load. If memory rules don't seem to be applying, verify the user migrated the memory directory from the pre-rename path (`-Users-bg1971-ai-sandbox-airlock-warlock`).
6. The 2026-05-09 session consolidated naming from "Airlock + Whizzard" to single "Whizzard" (D-144). Older docs and decisions may still reference Airlock as historical context — substance is unchanged.

## Build progress

| Stage | Status | Tests |
|---|---|---|
| 1: Generic Docker Shell Launch | ✅ Done, validated | 13 |
| 2: Mount Registry | ✅ Done, validated | +19 |
| 3: JSON-driven Profiles | ✅ Done, validated | +14 |
| 4: Dry Run | ✅ Done, validated | +9 |
| 5: Session Logging | ✅ Done, validated | +13 |
| 6: Safety Validation | ✅ Done, validated | +18 |
| 7: Generic Adapter | ✅ Done, validated | +41 |
| 8: Hermes Integration | In design — no code yet | — |
| 9–18 | Not started | — |

**131 tests passing** as of last code commit. MVP is now an **18-stage plan** (was 9 originally; expanded 2026-05-09 to clear the personal-use threshold per D-137 / D-138 / D-143).

## First task for this new session — `docs/` cleanup (Option B)

Bryan and the prior session agreed to a small cleanup before resuming Stage 8 work:

1. Create `docs/archive/` directory.
2. Move three finished research docs into it:
   - `docs/hermes_research.md` → `docs/archive/hermes_research.md`
   - `docs/nanoclaw_research.md` → `docs/archive/nanoclaw_research.md`
   - `docs/nanoclaw_internals.md` → `docs/archive/nanoclaw_internals.md`
3. Update any cross-references in other docs that point to those three files (search for `hermes_research.md`, `nanoclaw_research.md`, `nanoclaw_internals.md` and add `archive/` to the path).
4. Write a new `docs/README.md` as a navigation index — explains what each doc is for and the order to read them. Target ~50 lines, readable cold by a new contributor.
5. Capture this convention as a decision: **D-149** — `session_handoff.md` is overwriteable each session; not append-only. Add it to `docs/decisions.md` in §14 Process & collaboration.
6. Commit with message `docs: archive finished research, add docs/README navigation index, capture D-149`.
7. Per `feedback_merge_doc_changes.md`, fast-forward merge into `main` immediately.

After Option B, the natural next thread is Stage 8 design — see "Open work" below.

## Where to find current state

Don't re-derive what's already documented. Read these in this order:

| Doc | What's in it |
|---|---|
| [README.md](../README.md) | Top-level orientation, install, first run |
| [docs/vision_and_strategy.md](vision_and_strategy.md) | What Whizzard is, who it serves, where it's going. Includes Phase 3 Breaker, Phase 4 Shadow Home directional sketches |
| [docs/architecture.md](architecture.md) | System architecture, control layering (enforcement / behavioral / cooperation), safety policy, adapter contract, foundational invariants |
| [docs/mvp_build_plan.md](mvp_build_plan.md) | The 18-stage MVP plan with goals, deliverables, and dependencies |
| [docs/control_surface.md](control_surface.md) | Full structural-control surface map with status markers (✓ MVP / ◐ post-MVP / ○ new / ✗ harness-native) |
| [docs/decisions.md](decisions.md) | Append-only decisions index, D-01 through D-148 (148 captured as of 2026-05-09; 12 currently open) |
| [docs/post_mvp_spec.md](post_mvp_spec.md) | v1.0 plan; reduced scope after MVP expansion since vault, presets, Discord, idle timeout graduated to MVP |
| [docs/stage_validation.md](stage_validation.md) | Manual validation checklists for shipped stages |
| `docs/archive/` (after Option B cleanup) | Finished research artifacts — Hermes deep-dive, NanoClaw security analysis, NanoClaw internals |

## Durable feedback (auto-loads from memory)

These rules govern how Claude collaborates with Bryan. If they don't seem to be loading, check that the auto-memory directory migration was done correctly.

- **MVP focus** — until MVP is operational, push back on doc tweaks; steer toward implementation. Bryan-directed doc work (like a decisions audit) is exempt.
- **One topic at a time** — surfacing a multi-item list is fine, but discuss and resolve them one at a time.
- **Don't push to close** — stop ending responses with "ready to close X?" prompts; topics close naturally.
- **Merge doc-only commits immediately** — for doc-only changes, fast-forward merge into main without asking; revert via git if needed. Code changes still pause for confirmation.
- **User has split threat model — dep-careful but yolo on harnesses** — preflight any new Whiz dep against license/maintenance/native-code/footprint criteria. The Whiz "try a new harness" path must be easier than the yolo path or users bypass it.
- **Pause at UX-shaped stages to design before coding** — at Stages 10, 11, 16, 17 (presets, shortcuts, slash commands, Discord), open a design conversation before implementing.

## Open work

### Immediate (after Option B cleanup)

The next substantive thread is **Stage 8 (Hermes adapter) design**. Five questions remain open from the 2026-05-08 research pass:

- **D-86** — Hermes profile auto-creation UX (auto-create on first launch vs. require manual `hermes profile create` first)
- **D-87** — Concurrency exclusivity (refuse contained launch if host-side Hermes uses same profile, vs. document only)
- **D-88** — Default Hermes mode (interactive vs. gateway vs. no default)
- **D-89** — Platform credential declaration in gateway mode (config-implicit / CLI allowlist / harness preset / hybrid)
- **D-90** — In-session approval routing in gateway mode (platform-routed vs. `--yolo` bypass)

Bryan's directive: one at a time, no rushing. #3 (default mode) is the most consequential and cascades into others; #1 (profile auto-creation) is the most foundational. Open by asking which he wants first.

Also worth flagging at Stage 8 design: per D-142, design the adapter contract with a future input-side intercept hook in mind so post-MVP D (in-agent-chat slash command interception) doesn't require contract refactoring.

### Other open items (not blocking, tracked in decisions.md §15)

- **D-131** — OSS-launch milestone scope (distinct from MVP; needs definition once MVP is operational)
- **D-132** — Sidecar-proxy mechanism inclusion in OSS-launch
- **D-133** — Framework-level failure-mode policy vs. per-feature
- **D-134** — OneCLI direct integration vs. wait for full vault stage
- **D-135** — Read-only project-root mounting pattern adoption
- **D-136** — NanoClaw upstream collaboration

## Recent commits (2026-05-09)

```
1a1b7bf  rename: consolidate to "Whizzard" — drop Airlock split
6568d34  docs: slash command surface decisions + MVP extends to 18 stages
7e5c01f  docs: capture D-141 — hybrid generalization path (Option C)
75a3188  docs: session research, control framing, MVP scope expansion to 17 stages
7d0b01d  Add session handoff doc for context-window continuity (prior session)
```

All are merged into `main`. Branch `claude/crazy-ellis-b21769` is the worktree branch from the prior session and may be cleaned up via `git worktree remove` + `git branch -d` once you've verified main has everything.

## Recommended opening for the new session

> "Read docs/session_handoff.md. Then start with the Option B cleanup task (archive + docs/README.md + D-149 capture). After that lands, ask me which Stage 8 design question I want to take first."

That gets the cleanup done before any substantive new work, keeps the docs folder usable, and respects the one-topic-at-a-time rule when picking up Stage 8.

Good luck.
