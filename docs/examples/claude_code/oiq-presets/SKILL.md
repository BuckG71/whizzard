---
name: oiq-presets
description: "List available OIQ presets, or show the resolved config of one preset by name. Use when the user asks what presets exist, what a specific preset does, or wants to inspect preset definitions before launching. Read-only."
---

## Triggers

- **Explicit:** `/oiq-presets`, `/oiq-presets <name>`
- **Conversational:** "what presets do I have", "show me the hermes preset", "what does the shell preset do", "list configured presets"

## Action

Invoke OIQ's preset list/show shortcut. Read-only.

**Bare (`/oiq-presets`):** runs `oiq p` which lists all configured presets with profile, harness, mounts, platforms, and description.

**Named (`/oiq-presets <name>`):** runs `oiq p <name>` which shows the resolved config of one preset, including any override fields the preset sets (duration, idle timeout, broad-mount).

## Underlying command

```sh
oiq p [name]
```

Equivalents: `whiz p`, `whiz preset list`, `whiz preset show <name>`. Until the OIQ rename ([D-158](../../../decisions.md)) ships, the binary is `whiz`.

## Output to expect

**List (bare):** a table of presets with columns Name / Profile / Harness / Mounts / Platforms / Description. Header notes whether the source is user config (`~/.whizzard/config/presets.json`) or bundled defaults.

**Show (named):** key-value lines for one preset including any override fields set (omit-to-inherit fields aren't shown unless explicitly overridden).

If the user has not initialized `presets.json`, the bundled defaults (`hermes`, `shell`) show. `whiz preset init` writes the bundled set to `~/.whizzard/config/presets.json` for editing.

## When NOT to use

- The user wants to launch a preset → use `/oiq-launch <name>` instead.
- The user wants to edit / create a preset → direct them to edit `~/.whizzard/config/presets.json` (or `whiz preset init` to seed defaults).
