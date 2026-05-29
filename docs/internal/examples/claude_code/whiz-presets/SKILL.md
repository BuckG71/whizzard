---
name: whiz-presets
description: "List available Whizzard presets, or show the resolved config of one preset by name. Use when the user asks what presets exist, what a specific preset does, or wants to inspect preset definitions before launching. Read-only."
---

## Triggers

- **Explicit:** `/whiz-presets`, `/whiz-presets <name>`
- **Conversational:** "what presets do I have", "show me the hermes preset", "what does the shell preset do", "list configured presets"

## Action

Invoke Whizzard's preset list/show shortcut. Read-only.

**Bare (`/whiz-presets`):** runs `whiz p` which lists all configured presets with profile, harness, mounts, platforms, and description.

**Named (`/whiz-presets <name>`):** runs `whiz p <name>` which shows the resolved config of one preset, including any override fields the preset sets (duration, idle timeout, broad-mount).

## Underlying command

```sh
whiz p [name]
```

Equivalent: `whiz preset list`, `whiz preset show <name>`.

## Output to expect

**List (bare):** a table of presets with columns Name / Profile / Harness / Mounts / Platforms / Description. Header notes whether the source is user config (`~/.whizzard/config/presets.json`) or bundled defaults.

**Show (named):** key-value lines for one preset including any override fields set (omit-to-inherit fields aren't shown unless explicitly overridden).

If the user has not initialized `presets.json`, the bundled defaults (`hermes`, `shell`) show. `whiz preset init` writes the bundled set to `~/.whizzard/config/presets.json` for editing.

## When NOT to use

- The user wants to launch a preset → use `/whiz-launch <name>` instead.
- The user wants to edit / create a preset → direct them to edit `~/.whizzard/config/presets.json` (or `whiz preset init` to seed defaults).
