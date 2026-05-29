# Claude Code skill bundle for Whizzard

Four Claude Code skill files that wrap the Whizzard CLI so common operations are one-keystroke from inside Claude Code.

Each skill is a thin wrapper around a Whizzard CLI command (the CLI is Whizzard's harness-neutral surface; skills just give Claude Code an ergonomic invocation path).

## Skills

| Skill | Wraps | What it does |
|-------|-------|--------------|
| `whiz-launch` | `whiz r [preset]` | Launch a preset session, or the most-recent preset if no argument |
| `whiz-status` | `whiz s` | Show active sessions + recent history |
| `whiz-presets` | `whiz p [name]` | List all presets (no arg) or show details of one preset |
| `whiz-sessions-tail` | `whiz sessions tail` | Tail the audit log |

Skills for mutating operations (`whiz extend`, `whiz adjust`, `whiz approve`) are not included yet — they'll be added once the underlying CLI verbs ship. They're deliberately omitted rather than shipped as "not yet implemented" placeholders.

## Install

```sh
# from the Whizzard repo root:
cp -r docs/examples/claude_code/whiz-launch ~/.claude/skills/
cp -r docs/examples/claude_code/whiz-status ~/.claude/skills/
cp -r docs/examples/claude_code/whiz-presets ~/.claude/skills/
cp -r docs/examples/claude_code/whiz-sessions-tail ~/.claude/skills/
```

Or pick and choose. After install, Claude Code picks up the skills the next time it starts; type `/whiz-launch`, `/whiz-status`, etc., or let Claude invoke them when you describe what you want in natural language.

## Prerequisites

- Whizzard installed (`pip install whizzard`).
- `whiz` binary on `$PATH`.
- For preset launches: at least one preset configured (run `whiz preset list` to confirm; `whiz preset init` to seed bundled defaults).

## Notes

- These are **starter recipes**, not the canonical interface. The Whizzard CLI itself is the contract; these skill files are convenience wrappers you can edit freely.
- If you fork or customize, keep the underlying CLI call accurate — Claude Code uses the skill's `entry` to actually invoke the command.
- For non-Claude-Code harnesses, see siblings under `docs/examples/`.
