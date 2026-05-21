# Claude Code skill bundle for OIQ

Four Claude Code skill files that wrap the OIQ CLI so common operations are one-keystroke from inside Claude Code.

Each skill is a thin wrapper around an OIQ CLI command (the CLI is OIQ's harness-neutral surface; skills just give Claude Code an ergonomic invocation path).

## Skills

| Skill | Wraps | What it does |
|-------|-------|--------------|
| `oiq-launch` | `oiq r [preset]` | Launch a preset session, or the most-recent preset if no argument |
| `oiq-status` | `oiq s` | Show active sessions + recent history |
| `oiq-presets` | `oiq p [name]` | List all presets (no arg) or show details of one preset |
| `oiq-sessions-tail` | `oiq sessions tail` | Tail the audit log |

Skills for mutating operations (`oiq extend`, `oiq adjust`, `oiq approve`) will be added once the underlying CLI verbs ship (OIQ Stages 13–14). They're deliberately omitted today rather than shipped as "not yet implemented" placeholders.

## Install

```sh
# from the OIQ repo root:
cp -r docs/examples/claude_code/oiq-launch ~/.claude/skills/
cp -r docs/examples/claude_code/oiq-status ~/.claude/skills/
cp -r docs/examples/claude_code/oiq-presets ~/.claude/skills/
cp -r docs/examples/claude_code/oiq-sessions-tail ~/.claude/skills/
```

Or pick and choose. After install, Claude Code picks up the skills the next time it starts; type `/oiq-launch`, `/oiq-status`, etc., or let Claude invoke them when you describe what you want in natural language.

## Prerequisites

- OIQ installed (`pip install -e .` from the repo, or `pip install whizzard` once published).
- `oiq` binary on `$PATH`. (Currently bundled as `whiz` / `whizzard` until the rename per [D-158](../../decisions.md); update the skill `entry` lines accordingly while the rename is pending.)
- For preset launches: at least one preset configured (run `whiz preset list` to confirm; `whiz preset init` to seed bundled defaults).

## Notes

- These are **starter recipes**, not the canonical interface. The OIQ CLI itself is the contract; these skill files are convenience wrappers you can edit freely.
- If you fork or customize, keep the underlying CLI call accurate — Claude Code uses the skill's `entry` to actually invoke the command.
- For non-Claude-Code harnesses, see siblings under `docs/examples/`.
