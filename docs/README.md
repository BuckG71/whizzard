# docs/ — navigation index

Whizzard is a local capability-governance layer for AI agents. Code-level orientation lives in the top-level [README.md](../README.md); this folder holds the design and decision record.

## Read in this order

1. **[vision_and_strategy.md](vision_and_strategy.md)** — what Whizzard is, who it serves, and where it's going. Includes Phase 3 (Breaker) and Phase 4 (Shadow Home) directional sketches.
2. **[architecture.md](architecture.md)** — system architecture, control layering (enforcement / behavioral / cooperation), safety policy, the adapter contract, and foundational invariants.
3. **[mvp_build_plan.md](mvp_build_plan.md)** — the 18-stage MVP plan with goals, deliverables, and dependencies. Stage status is tracked here.
4. **[control_surface.md](control_surface.md)** — full structural-control surface map with status markers (✓ MVP / ◐ post-MVP / ○ new / ✗ harness-native).
5. **[post_mvp_spec.md](post_mvp_spec.md)** — v1.0 plan; reduced scope after MVP expansion since vault, presets, Discord, and idle timeout graduated to MVP.

## Reference docs (read on demand)

- **[decisions.md](decisions.md)** — append-only decisions index, D-01 onward. Section 15 collects open / unresolved items; section 16 cross-references decisions back to source docs. The canonical record for "why is it this way?"
- **[stage_validation.md](stage_validation.md)** — manual validation checklists for shipped stages.
- **[session_handoff.md](session_handoff.md)** — current-snapshot context for a fresh Claude Code session. Overwritten each session (per D-149); use `git show <hash>:docs/session_handoff.md` to recover prior versions.

## Archive

**[archive/](archive/)** holds finished research artifacts kept for reference but no longer part of the active reading order:

- `hermes_research.md` — deep dive into the Hermes harness (informs Stage 8).
- `nanoclaw_research.md` — security and containment analysis of NanoClaw.
- `nanoclaw_internals.md` — companion to the above, covering NanoClaw's operator-side skill model and internals.

These three were the input material for D-78..D-98; the conclusions live in `decisions.md`. Don't re-derive — read the decisions first and only dip into archive if you need the underlying evidence.

## Conventions

- **Decisions are numbered.** When you make one, append it to `decisions.md` in the right section. Don't edit prior decisions in place — supersede with a new one.
- **`session_handoff.md` is overwriteable.** It captures current state, not history. Roll back via git.
- **Doc-only commits fast-forward into `main` immediately** (D-147). No PR ceremony required for documentation.
