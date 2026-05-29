---
name: whiz-launch
description: "Launch a Whizzard-contained agent session via a named preset. Use when the user asks to start a session, run an agent, fire up a harness, or launch a preset by name. Bare invocation launches the most-recently-used preset. Whizzard wraps each session in a hardened Docker sandbox with capability boundaries per the preset's profile + mounts + harness config."
---

## Triggers

- **Explicit:** `/whiz-launch`, `/whiz-launch <preset>`
- **Conversational:** "launch hermes", "start a session", "fire up the agent", "run the X preset", "spin up a Whizzard sandbox"

## Action

Invoke the Whizzard CLI's smart launch shortcut. The CLI handles preset resolution, banner display, and container lifecycle — this skill just calls it.

**Bare (`/whiz-launch`):** runs `whiz r` which launches the most-recent preset (the one most recently used per `~/.whizzard/logs/sessions.jsonl`). If no recent preset exists, Whizzard errors with a clear message.

**Named (`/whiz-launch <preset>`):** runs `whiz r <preset>` which launches the named preset.

## Underlying command

```sh
whiz r [preset]
```

## Output to expect

The launch banner shows:
- Profile (e.g. `DEFAULT`), network on/off, duration limit, broad-mount override status
- Image being used (`whizzard-base:latest` or a harness-specific image like `whizzard-hermes:latest`)
- Harness name + active capabilities (declared platforms, MCP availability)
- Session ID
- Mounts (named + paths)

Followed by the actual containerized session (interactive shell, Hermes chat, etc.). The session ends when the user exits the harness's native quit mechanism; `whiz` returns to the shell after.

## When NOT to use

- The user just wants to see what's available — use `/whiz-presets` instead.
- The user wants status of running sessions — use `/whiz-status` instead.
- The user is configuring a new preset (no preset exists yet) — direct them to edit `~/.whizzard/config/presets.json` or run `whiz preset init`.
