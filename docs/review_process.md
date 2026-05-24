# Whizzard — Code Review Process

How code review works on this project after the 2026-05-23 catch-up review.
Short by design: this doc is the *protocol*; the rationale lives in
`docs/decisions.md` and the working memory files under
`~/.claude/projects/.../memory/`.

## What runs at every stage close

When a build-plan stage ships, `/wrap-up stage` (the `work-wrap-up`
skill) is the entry point. It already runs the validation gates and
proposes the CHANGELOG entry. Now it also runs a focused code review on
the stage's diff before the commit-push lands.

The review is driven by the built-in `code-review` skill:

- **Risk-tagged stages** — anything touching containment, credential
  handling, mount/permission paths, mutation (adjust + wake), the audit
  log, or the in-cell MCP server — run at `effort=high`.
- **Everything else** — run at `effort=medium`.

The wrap-up skill consults the build plan's risk classification when
selecting the level; if unclear, default to `high` (the cost of an
extra pass is small; the cost of missing a real bug is not).

## Triage discipline

For every finding the reviewer surfaces, decide one of:

- **fix-now** — apply the fix in the same commit batch. Default bias
  for review findings; only divert if there's a real reason not to.
- **defer** — log to `docs/known_issues.md` with the per-finding
  rationale (what the fix entails AND its natural home — Stage 18,
  Stage 20, post-OSS-launch, etc.).
- **decision-needed** — if the finding raises a design question, draft
  a `D-NNN` entry via the `decision-capture` skill, set status `open`,
  cross-reference from `known_issues.md`. The fix waits on the
  decision.
- **dismiss** — only when the finding genuinely isn't a bug. Rationale
  must name the invariant or decision that makes the concern moot
  (e.g. "D-22 makes the docker CLI the trust boundary"). "Fine in
  practice" doesn't count.

Two hard rules: bias toward **fix-now**; every **defer** and every
**dismiss** carries a one-paragraph rationale. The catch-up review
established this pattern — see `feedback_default_to_fix_now` in
project memory.

## Where findings end up

| Disposition       | Lands in                                  |
|-------------------|-------------------------------------------|
| fix-now           | the stage's commit batch + tests          |
| defer             | `docs/known_issues.md`                    |
| decision-needed   | `docs/decisions.md` (open) + known_issues |
| dismiss           | the commit body + this doc's rationale    |

No transient `.draft.md` files in the repo — the catch-up review used a
gitignored working file under `docs/internal/` that was deleted at the
end. Future per-stage reviews don't need that intermediate file; the
diff is small enough to triage inline.

## Periodic whole-tree refresh

Every ~5 stages, or before any external-reviewer pass or OSS-launch
milestone, re-run the chunked whole-tree review pattern the catch-up
review used:

1. Identify chunks whose files changed meaningfully since the last
   baseline (use `git diff --stat <last-baseline-tag>..HEAD`).
2. For each changed chunk, spawn a fresh review agent with the
   chunk-A through chunk-H brief from the catch-up review (see
   `~/.claude/plans/redirect-we-re-getting-pretty-glowing-piglet.md`
   for the original prompt templates).
3. Triage per the rules above.

Tag the baseline as `review-baseline-YYYY-MM-DD` so the next refresh
has a clean diff base.

## Pre-launch external review

Stage 20 in `docs/mvp_build_plan.md` covers the OSS-launch external-
reviewer pass. That is the human-eyes layer; this protocol is the
LLM-assisted layer that runs throughout the build. They are
complementary, not redundant.

## What this protocol does NOT do

- It does not replace `make check` (lint + typecheck + unit tests) or
  `make coverage` (the ≥80% gate). Those still run on every commit.
- It does not replace `make integration` — integration tests are
  mandatory before pushing changes that touch docker, session
  lifecycle, audit log, or the resolutions store. The catch-up review
  surfaced that `make check` deselects the integration tier, so
  running it separately is on the operator (or CI).
- It does not replace `/ultrareview` for whole-codebase reviews — that
  is the closest thing to second-pair-of-eyes today and is recommended
  at meaningful milestones.

## When this protocol changes

Process refinements get committed to this file in the same PR that
introduces them. The catch-up review's `feedback_*` memory files
(under `~/.claude/projects/...`) carry the conversational rationale;
this file carries the durable rules.

Cross-references:

- `docs/decisions.md` §D-122 — solo-on-main workflow.
- `docs/decisions.md` §D-150 — HANDOFF append-only discipline.
- `docs/known_issues.md` "Process risks" — pace + review-gate balance.
- `docs/mvp_build_plan.md` §Stage 20 — pre-launch external review.
- `~/.claude/skills/work-wrap-up/SKILL.md` — the per-stage entry point.
