# docs/examples/ — harness integration recipes

OIQ ships a CLI; **the CLI is the harness-neutral integration surface**. Any agent harness — Claude Code, Codex, Cline, OpenClaw, Hermes, anything that can shell out — can invoke `oiq r`, `oiq s`, `oiq run --harness ...` directly. No harness-specific runtime in OIQ core.

This directory holds **copy-paste integration recipes** showing how to wire OIQ into popular harnesses ergonomically. Each subdirectory is one harness; install the relevant files into your harness's config location and you get one-keystroke OIQ commands inside that harness.

> **Design context:** the choice to ship integration as docs/examples rather than as core code was captured in [D-161](../decisions.md). Earlier proposals (host-side MCP server, canonical commands.yaml with per-harness emitters, locking integration to Claude-Code-specific slash commands) were all rejected — see D-161's Rationale for the full deliberation.

## Production-grade examples (shipped)

These are the recipes the MVP user (Bryan) uses daily; they're proven working setups, not stubs.

- **[`claude_code/`](claude_code/)** — Claude Code skill files wrapping `oiq r` / `oiq s` / `oiq p` / `oiq sessions tail`. Drop into `~/.claude/skills/<name>/` to install.
- **[`hermes/`](hermes/)** — Hermes adapter setup recipe (the [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) harness): `harnesses.json` snippet, profile-clone walkthrough, provider config (Ollama via `host.docker.internal`, or Anthropic via the D-162 `secrets:` block).

## Contribution targets (PRs welcome)

These would benefit from community-contributed recipes once OIQ goes OSS:

- `codex/` — OpenAI Codex CLI integration
- `cline/` — Cline (VS Code agent) integration
- `openclaw/` — OpenClaw harness setup (v1.0 OIQ adapter target)
- `nanoclaw/` — NanoClaw harness setup (v1.0 OIQ adapter target per D-155)
- `deployments/home_lab/` — companion to [`../home_lab_deployment.md`](../home_lab_deployment.md), with the actual Tailscale + Ollama setup scripts

## How to contribute a recipe

1. **Use OIQ end-to-end in your harness** to validate the setup before writing the recipe — readers will notice if the steps don't actually work.
2. **Create `docs/examples/<harness>/`** with:
   - `README.md` walking through install / configure / launch
   - Any config snippets the user needs (with placeholder values clearly marked)
   - Pointer to any harness-side commands or skills they install
3. **Use lowercase filenames** (D-151).
4. **Don't put secrets in any example file.** Use placeholder names (`<YOUR_API_KEY>`) and reference the D-162 `secrets:` mechanism for runtime resolution.
5. **PR the recipe.** Each harness recipe is independent; they don't need to coordinate with OIQ core.
