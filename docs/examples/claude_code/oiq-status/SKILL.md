---
name: oiq-status
description: "Show status of OIQ-contained sessions: which are currently running, plus a table of the last ten launches. Use when the user asks what's running, what's the latest session, or to inspect OIQ state. Read-only; safe to invoke any time."
---

## Triggers

- **Explicit:** `/oiq-status`
- **Conversational:** "what's running", "session status", "any active OIQ sessions", "show me OIQ activity", "what was the last preset I ran"

## Action

Invoke the OIQ CLI's status command. Read-only — no side effects.

## Underlying command

```sh
oiq s
```

Equivalents: `whiz s`, `whiz status`, `whizzard status`. Until the OIQ rename ([D-158](../../../decisions.md)) ships, the binary is `whiz`.

## Output to expect

Two-part display:
1. **Active sessions count** — number of sessions that have `session_start` events without a matching `session_end` in `~/.whizzard/logs/sessions.jsonl`. (Note: a crash that prevents `session_end` writing can leave stale entries; crash recovery is post-MVP.)
2. **Recent sessions table** — last ten `session_start` events with status (RUNNING / ended), short session ID, profile, preset, harness, and start time.

If no sessions have ever been logged, OIQ prints "no sessions logged yet" and points at `--help`.

## When NOT to use

- The user wants to inspect a specific session's audit log → use `/oiq-sessions-tail` instead.
- The user wants to launch something → use `/oiq-launch` instead.
