# CLAUDE.md

Guidance for Claude Code sessions in this repository.

## Output format: prefer HTML where it makes sense

When producing something for a human to *read* — reports, analyses, summaries,
plans, design reviews, comparisons, status updates, data explorations — prefer
generating a single self-contained HTML file over a long Markdown document or a
wall of chat text. Reasoning (from "The Unreasonable Effectiveness of HTML",
Anthropic / Thariq Shihipar):

- People skim or skip long Markdown files; they actually read HTML.
- HTML carries far more information per page: CSS layout, SVG diagrams, tables,
  tabs, collapsible sections, color, callouts, links.
- It costs more tokens than Markdown, but the higher chance of being read makes
  the trade worth it.

Practical rules:

- Make it one self-contained `.html` file — inline all CSS and JS, no external
  build step or dependencies — so it opens by double-click and is easy to share.
- Use structure that aids navigation: headings, a table of contents or tabs for
  long documents, collapsible detail sections, and SVG/diagrams over prose where
  a picture is clearer.
- Keep code and tooling-consumed files in their normal formats. The project's
  design docs in `docs/` stay Markdown (and `docs/decisions.md` stays an
  append-only Markdown index); commit messages and code comments stay plain
  text. HTML is for human-facing deliverables, not a replacement for source.

## When to reach for HTML — concrete cases

Use for any chat response that is over 150 words to minimize the need for scrolling through small chat window on Claude mobile app. 

Deliverables that land much better as a self-contained HTML file than as
Markdown or a chat wall (examples from thariqs.github.io/html-effectiveness):

- **Code review** — render the change as an annotated diff with margin notes,
  severity tags and jump links; or a PR write-up with motivation, before/after
  and a file-by-file tour that points to where the review should focus.
- **Approach comparisons** — two or three solutions to the same problem laid
  out side by side, with trade-offs in a table.
- **Architecture / code understanding** — an unfamiliar module drawn as
  boxes-and-arrows (SVG), with the hot path highlighted and entry points listed.
- **Implementation plans** — a timeline, data-flow diagrams and a risk table,
  not a flat list of steps.
- **UI mockups** — several visual directions for a screen or component, shown
  as actual rendered HTML rather than described in prose.
- **Explainers** — collapsible sections, tabbed code samples and a margin
  glossary so a new topic is navigable instead of a linear wall of text.

## Throwaway HTML tools

When a piece of data or a layout is hard to specify precisely in text, build a
small purpose-built HTML editor/tool for it instead of guessing. Always finish
such a tool with an export button — "copy as JSON" or "copy as prompt" — so the
result round-trips cleanly back into a Claude Code prompt or a committed file.

## Use judgement

"Where it makes sense" is the operative phrase. A one-line answer, a quick code
change, or a terminal command does not need an HTML file. Reach for HTML when
the deliverable is substantial, visual, or meant to be read and shared by people.
