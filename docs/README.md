# docs/ — navigation index

Whizzard is a local capability-governance layer for AI agents. Code-level orientation lives in the top-level [README.md](../README.md); this folder holds the design and decision record.

## Read in this order (first-time orientation)

1. **[vision_and_strategy.md](vision_and_strategy.md)** — what Whizzard is, who it serves, where it's going.
2. **[architecture.md](architecture.md)** — system architecture, control layering (enforcement / behavioral / cooperation), safety policy, the adapter contract, and foundational invariants.
3. **[../ROADMAP.md](../ROADMAP.md)** — v1.0 primary goals and rough sequencing.

## Decisions record

- **[decisions.md](decisions.md)** — the canonical record for "why is it this way?". Append-only. Flat list of `D-NN` entries with a flat+tags schema (`Type:` for primary classification, `Tags:` from a curated vocabulary). Three navigation aids at the bottom: a `## Tag vocabulary` section, a `## Cross-references` section grouping decisions by their source doc, and an `## Open questions tracker` listing decisions currently in `open` status.

## Architecture reference

- **[reference/architecture-at-a-glance.html](reference/architecture-at-a-glance.html)** — self-contained visual overview, diagram-first. Companion to [architecture.md](architecture.md), which remains the canonical written source of truth.

## Conventions

- **Decisions are append-only and numbered.** When you make one, append it to `decisions.md` with the next sequential `D-NN`. Don't edit prior decisions in place — supersede with a new one and update the prior entry's `Status:` to `superseded by D-NN`.
- **Tags are drawn from the canonical vocabulary** at the bottom of `decisions.md`. New tags require an explicit vocabulary addition — never invent inline.
- **Doc-only commits fast-forward into `main` immediately**. No PR ceremony required for documentation.
- **Markdown filenames are lowercase** going forward; legacy uppercase files will be renamed in a planned bulk sweep alongside the eventual product-name change.
