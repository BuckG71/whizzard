# docs/examples/ — harness integration recipes

Whizzard ships a CLI; **the CLI is the harness-neutral integration surface**. Any agent harness — Claude Code, Codex, Cline, OpenClaw, Hermes, anything that can shell out — can invoke `whiz r`, `whiz s`, `whiz run --harness ...` directly. No harness-specific runtime in Whizzard core.

This directory holds **copy-paste integration recipes** showing how to wire Whizzard into popular harnesses ergonomically. Each subdirectory is one harness; install the relevant files into your harness's config location and you get one-keystroke Whizzard commands inside that harness.

> **Design context:** integration ships as docs/examples (copy-paste recipes) rather than as harness-specific code in core. Earlier proposals — a host-side MCP server, a canonical `commands.yaml` with per-harness emitters, locking integration to Claude-Code-specific slash commands — were rejected to keep core harness-neutral.

## Production-grade examples (shipped)

These are recipes used daily by the maintainer; they're proven working setups, not stubs.

- **[`claude_code/`](claude_code/)** — Claude Code skill files wrapping `whiz r` / `whiz s` / `whiz p` / `whiz sessions tail`. Drop into `~/.claude/skills/<name>/` to install.
- **[`hermes/`](hermes/)** — Hermes adapter setup recipe (the [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) harness): `harnesses.json` snippet, profile-clone walkthrough, provider config (Ollama via `host.docker.internal`, or Anthropic via the harness `secrets:` field — Whizzard's mechanism for injecting named credentials at session launch).

## Contribution targets (PRs welcome)

These would benefit from community-contributed recipes:

- `codex/` — OpenAI Codex CLI integration
- `cline/` — Cline (VS Code agent) integration
- `openclaw/` — OpenClaw harness setup (a Whizzard adapter is planned for v1.0)
- `nanoclaw/` — NanoClaw harness setup (a Whizzard adapter is planned for v1.0)
- `deployments/home_lab/` — companion to [`../home_lab_deployment.md`](../home_lab_deployment.md), with the actual Tailscale + Ollama setup scripts

## How to contribute a recipe

1. **Use Whizzard end-to-end in your harness** to validate the setup before writing the recipe — readers will notice if the steps don't actually work.
2. **Create `docs/examples/<harness>/`** with:
   - `README.md` walking through install / configure / launch
   - Any config snippets the user needs (with placeholder values clearly marked)
   - Pointer to any harness-side commands or skills they install
3. **Use lowercase filenames.**
4. **Don't put secrets in any example file.** Use placeholder names (`<YOUR_API_KEY>`) and reference the harness `secrets:` mechanism for runtime resolution.
5. **PR the recipe.** Each harness recipe is independent; they don't need to coordinate with Whizzard core.
