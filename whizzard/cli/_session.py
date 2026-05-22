"""Session-log read helpers used by status + brevity-alias dispatch.

These all read sessions.jsonl (newline-delimited JSON events). They are
read-only and side-effect-free.
"""

from __future__ import annotations

import calendar
import json
import time

from whizzard.session_log import SESSIONS_LOG


def _read_session_events() -> list[dict]:
    """Read sessions.jsonl into a list of event dicts. Empty if no file."""
    if not SESSIONS_LOG.exists():
        return []
    events: list[dict] = []
    for raw in SESSIONS_LOG.read_text().splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def _active_sessions(events: list[dict]) -> set[str]:
    """Return session_ids that have a start without a matching end.

    Note: a Whizzard crash can leave stale unended session_starts. Crash
    recovery (correlating against `docker ps`) is post-MVP.
    """
    started: set[str] = set()
    for ev in events:
        if ev.get("event") == "session_start":
            sid = ev.get("session_id")
            if sid:
                started.add(sid)
        elif ev.get("event") == "session_end":
            sid = ev.get("session_id")
            if sid in started:
                started.remove(sid)
    return started


def _most_recent_preset() -> str | None:
    """Return the preset name from the most recent session_start with a
    `preset` field, or None if no such entry exists. Used by bare `whiz r`."""
    events = _read_session_events()
    for ev in reversed(events):
        if ev.get("event") == "session_start" and "preset" in ev:
            preset: str = ev["preset"]
            return preset
    return None


def _harness_from_event(ev: dict) -> str:
    """Best-effort harness name extraction from a session_start event.

    Argv contains `--label whizzard.harness=<name>`; parse it out."""
    argv = ev.get("argv") or []
    for i, arg in enumerate(argv):
        if arg.startswith("whizzard.harness=") and i > 0 and argv[i - 1] == "--label":
            return str(arg.split("=", 1)[1])
    return "?"


def _remaining_seconds(start_event: dict, now: float | None = None) -> float | None:
    """Seconds until a session hits its duration cap (Stage 15).

    Returns None if the session has no cap (`duration_limit_seconds` null)
    or its start timestamp can't be parsed. May be negative if the logged
    session has already run past its cap.
    """
    limit = start_event.get("duration_limit_seconds")
    if not isinstance(limit, int):
        return None
    raw = start_event.get("start_time") or start_event.get("ts")
    if not isinstance(raw, str):
        return None
    try:
        struct = time.strptime(raw, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None
    started = calendar.timegm(struct)
    return limit - ((now if now is not None else time.time()) - started)
