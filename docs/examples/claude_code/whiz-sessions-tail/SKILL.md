---
name: whiz-sessions-tail
description: "Show recent entries from the Whizzard session audit log. Use when the user wants to see what happened in past sessions, inspect session_start / session_end events, or trace activity. Read-only; never modifies the log."
---

## Triggers

- **Explicit:** `/whiz-sessions-tail`, `/whiz-sessions-tail -n 20`
- **Conversational:** "show me recent Whizzard activity", "tail the session log", "what happened in the last few sessions", "show me the audit trail"

## Action

Invoke Whizzard's sessions-log tail. Read-only.

Default shows the last 10 lines. Pass `-n <N>` to show a different count.

## Underlying command

```sh
whiz sessions tail [-n N]
```

## Output to expect

Raw JSONL lines from `~/.whizzard/logs/sessions.jsonl`. Each line is one event — `session_start`, `session_end`, or an agent-emitted event from the in-sandbox MCP server. Fields include timestamps, session IDs, profile, image, mounts, exit status, etc.

If the log file doesn't exist yet (no sessions ever launched), Whizzard prints "no session log yet" with the expected path.

## When NOT to use

- The user wants a compact overview of activity → use `/whiz-status` instead (formatted table, much easier to read than raw JSONL).
- The user wants to launch something → use `/whiz-launch` instead.
