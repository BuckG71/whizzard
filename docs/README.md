# docs/ — navigation index

Whizzard is a local capability-governance layer for AI agents. Code-level orientation lives in the top-level [README.md](../README.md); this folder holds the design and decision record.

## Read in this order (first-time orientation)

1. **[vision_and_strategy.md](vision_and_strategy.md)** — what Whizzard is, who it serves, where it's going. Includes Phase 3 (Breaker) and Phase 4 (Shadow Home) directional sketches plus the Real-World Validation section tracking incident patterns the threat model addresses.
2. **[architecture.md](architecture.md)** — system architecture, control layering (enforcement / behavioral / cooperation), safety policy, the adapter contract, and foundational invariants.
3. **[mvp_build_plan.md](mvp_build_plan.md)** — the 18-stage MVP plan with goals, deliverables, and dependencies. Stage status is tracked here (`[SHIPPED <date>]` markers as stages land).
4. **[control_surface.md](control_surface.md)** — full structural-control surface map with status markers (✓ MVP / ◐ post-MVP / ○ new / ✗ harness-native).
5. **[post_mvp_spec.md](post_mvp_spec.md)** — v1.0 plan; reduced scope after MVP expansion since vault, presets, Discord, and idle timeout graduated to MVP.

## Decisions & process record

- **[decisions.md](decisions.md)** — the canonical record for "why is it this way?". Append-only per D-129. Flat list of `D-NN` entries (D-01 onward) with a flat+tags schema (`Type:` for primary classification, `Tags:` from a curated vocabulary). Has three navigation aids at the bottom: a `## Tag vocabulary` section listing canonical tags + how to add new ones, a `## Cross-references` section grouping decisions by their source doc, and an `## Open questions tracker` listing decisions currently in `open` status.
- **[HANDOFF.md](HANDOFF.md)** — append-only log of session-level transitions per D-150. Each entry captures what shipped, what's in flight, and what's next at a specific session boundary. Read the latest entry to pick up the thread.
- **[session_handoff.md](session_handoff.md)** — older single-snapshot handoff doc (2026-05-09). Superseded by HANDOFF.md per D-150 but retained for historical context; not actively updated.

## Stage-level build references

- **[stage_validation.md](stage_validation.md)** — manual validation checklists for shipped stages. The practical contract behind the architectural decisions.
- **[STAGE_8_BUILD_PLAN.md](STAGE_8_BUILD_PLAN.md)** — per-stage focused build plan, used when a stage needs more detail than the top-level `mvp_build_plan.md` carries. Pattern; similar files appear for stages that warrant the depth.

## Deployment references

- **[home_lab_deployment.md](home_lab_deployment.md)** — reference doc for the post-MVP four-machine Tailscale-meshed deployment (Mac Studio workstation + Linux MBP agent host + Gaming PC inference + eventual cloud VM). Captures architecture, sequencing, constraints, and the OSS-launch positioning angle. Awaiting MVP completion + local OIQ migration before execution.

## Harness integration examples

- **[examples/](examples/)** — copy-paste recipes for using OIQ inside specific harnesses. Currently ships production-grade `examples/claude_code/` (Claude Code skill files wrapping the OIQ CLI) and `examples/hermes/` (full Hermes adapter setup walkthrough). Other harnesses welcome via PR. See `examples/README.md` for contribution guidance and the design rationale (D-161).

## Archive

**[archive/](archive/)** holds finished research artifacts kept for reference but no longer part of the active reading order:

- `hermes_research.md` — deep dive into the Hermes harness (informed Stage 8).
- `nanoclaw_research.md` — security and containment analysis of NanoClaw.
- `nanoclaw_internals.md` — companion to the above; covers NanoClaw's operator-side skill model and internals.

These were the input material for D-78..D-98; the conclusions live in `decisions.md`. Don't re-derive — read the decisions first and only dip into archive if you need the underlying evidence.

## Conventions

- **Decisions are append-only and numbered.** When you make one, append it to `decisions.md` with the next sequential `D-NN`. Don't edit prior decisions in place — supersede with a new one and update the prior entry's `Status:` to `superseded by D-NN`. See the decision-capture skill for the full protocol.
- **HANDOFF.md is append-only** (D-150). Each session-level transition gets a new entry at the bottom; never edit prior entries.
- **Tags are drawn from the canonical vocabulary** at the bottom of `decisions.md`. New tags require an explicit vocabulary addition — never invent inline. See the decision-capture skill's "Tag selection" guidance.
- **Doc-only commits fast-forward into `main` immediately**. No PR ceremony required for documentation.
- **Markdown filenames are lowercase** going forward (D-151); legacy uppercase files (`HANDOFF.md`, `STAGE_8_BUILD_PLAN.md`) will be renamed in the planned bulk sweep alongside the Whizzard→Osmotiq product rename (D-158).
