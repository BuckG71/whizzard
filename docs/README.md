# docs/ — navigation index

Whizzard is a local capability-governance layer for AI agents. Code-level orientation lives in the top-level [README.md](../README.md); this folder holds the design and decision record.

## Read in this order (first-time orientation)

1. **[vision_and_strategy.md](vision_and_strategy.md)** — what Whizzard is, who it serves, where it's going.
2. **[architecture.md](architecture.md)** — system architecture, control layering (enforcement / behavioral / cooperation), safety policy, the adapter contract, and foundational invariants.
3. **[../ROADMAP.md](../ROADMAP.md)** — v1.0 primary goals and rough sequencing.

## Decisions record

- **[decisions.md](decisions.md)** — the canonical record for "why is it this way?". Append-only per D-129. Flat list of `D-NN` entries with a flat+tags schema (`Type:` for primary classification, `Tags:` from a curated vocabulary). Three navigation aids at the bottom: a `## Tag vocabulary` section, a `## Cross-references` section grouping decisions by their source doc, and an `## Open questions tracker` listing decisions currently in `open` status.

## Stage-level build references

- **[stage_validation.md](stage_validation.md)** — manual validation checklists for shipped stages. The practical contract behind the architectural decisions.

## Deployment references

- **[home_lab_deployment.md](home_lab_deployment.md)** — reference doc for the post-MVP multi-machine Tailscale-meshed deployment. Captures architecture, sequencing, and constraints.

## Harness integration examples

- **[examples/](examples/)** — copy-paste recipes for using Whizzard inside specific harnesses. Currently ships `examples/claude_code/` (Claude Code skill files wrapping the CLI) and `examples/hermes/` (full Hermes adapter setup walkthrough). Other harnesses welcome via PR. See `examples/README.md` for contribution guidance and the design rationale (D-161).

## Architecture reference

- **[reference/whizzard-architecture.html](reference/whizzard-architecture.html)** — self-contained architecture overview rendered for quick browsing.

## Archive

**[archive/](archive/)** holds finished research artifacts kept for reference but no longer part of the active reading order:

- `hermes_research.md` — deep dive into the Hermes harness (informed Stage 8).
- `nanoclaw_research.md` — security and containment analysis of NanoClaw.
- `nanoclaw_internals.md` — companion to the above; covers NanoClaw's operator-side skill model and internals.

These were the input material for several decisions; the conclusions live in `decisions.md`. Don't re-derive — read the decisions first and only dip into archive if you need the underlying evidence.

## Conventions

- **Decisions are append-only and numbered.** When you make one, append it to `decisions.md` with the next sequential `D-NN`. Don't edit prior decisions in place — supersede with a new one and update the prior entry's `Status:` to `superseded by D-NN`.
- **Tags are drawn from the canonical vocabulary** at the bottom of `decisions.md`. New tags require an explicit vocabulary addition — never invent inline.
- **Doc-only commits fast-forward into `main` immediately**. No PR ceremony required for documentation.
- **Markdown filenames are lowercase** going forward (D-151); legacy uppercase files will be renamed in the planned bulk sweep alongside the Whizzard→Osmotiq product rename (D-158).
