---
name: oiq-sessions-tail
description: "Show recent entries from the OIQ session audit log. Use when the user wants to see what happened in past sessions, inspect session_start / session_end events, or trace activity. Read-only; never modifies the log."
---

## Triggers

- **Explicit:** `/oiq-sessions-tail`, `/oiq-sessions-tail -n 20`
- **Conversational:** "show me recent OIQ activity", "tail the session log", "what happened in the last few sessions", "show me the audit trail"

## Action

Invoke OIQ's sessions-log tail. Read-only.

Default shows the last 10 lines. Pass `-n <N>` to show a different count.

## Underlying command

```sh
oiq sessions tail [-n N]
```

Equivalents: `whiz sessions tail`, `whizzard sessions tail`. Until the OIQ rename ([D-158](../../../decisions.md)) ships, the binary is `whiz`.

## Output to expect

Raw JSONL lines from `~/.whizzard/logs/sessions.jsonl`. Each line is one event — `session_start`, `session_end`, or an agent-emitted event from the in-sandbox MCP server. Fields include timestamps, session IDs, profile, image, mounts, exit status, etc.

If the log file doesn't exist yet (no sessions ever launched), OIQ prints "no session log yet" with the expected path.

## When NOT to use

- The user wants a compact overview of activity → use `/oiq-status` instead (formatted table, much easier to read than raw JSONL).
- The user wants to launch something → use `/oiq-launch` instead.
