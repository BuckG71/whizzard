---
name: whiz-status
description: "Show status of Whizzard-contained sessions: which are currently running, plus a table of the last ten launches. Use when the user asks what's running, what's the latest session, or to inspect Whizzard state. Read-only; safe to invoke any time."
---

## Triggers

- **Explicit:** `/whiz-status`
- **Conversational:** "what's running", "session status", "any active Whizzard sessions", "show me Whizzard activity", "what was the last preset I ran"

## Action

Invoke the Whizzard CLI's status command. Read-only — no side effects.

## Underlying command

```sh
whiz s
```

Equivalent: `whiz status`.

## Output to expect

Two-part display:
1. **Active sessions count** — number of sessions that have `session_start` events without a matching `session_end` in `~/.whizzard/logs/sessions.jsonl`. (A crash that prevents `session_end` writing can leave stale entries; crash-recovery cleanup is a planned post-v0.1.0 feature.)
2. **Recent sessions table** — last ten `session_start` events with status (RUNNING / ended), short session ID, profile, preset, harness, and start time.

If no sessions have ever been logged, Whizzard prints "no sessions logged yet" and points at `--help`.

## When NOT to use

- The user wants to inspect a specific session's audit log → use `/whiz-sessions-tail` instead.
- The user wants to launch something → use `/whiz-launch` instead.
