"""Session logging at ~/.whizzard/logs/sessions.jsonl.

Stage 5 scope: writes session_start when a session begins and session_end
when the container exits. JSONL format — one JSON object per line, easy to
grep/jq/tail and trivial to extend with new fields.

Wrap-up events (adapter-driven graceful shutdown) and SIGTERM/SIGKILL
bookkeeping land in Stage 7 alongside the adapter interface; the schema
already reserves room for them by being open-ended JSON.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from whizzard.config import LOGS_DIR

SESSIONS_LOG = LOGS_DIR / "sessions.jsonl"


def new_session_id() -> str:
    """Generate a fresh UUID for a session."""
    return str(uuid.uuid4())


def _iso(ts: float | None = None) -> str:
    """ISO 8601 UTC timestamp, suitable for log lines."""
    if ts is None:
        ts = time.time()
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def append_event(event: dict[str, Any], path: Path | None = None) -> None:
    """Append a single JSON object as one line in the sessions log."""
    target = path or SESSIONS_LOG
    target.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(event, separators=(",", ":"))
    with target.open("a") as f:
        f.write(line + "\n")


def log_session_start(
    session_id: str,
    profile_name: str,
    network_enabled: bool,
    duration_limit_seconds: int | None,
    allow_broad_mount: bool,
    image_tag: str,
    image_id: str | None,
    mounts: list[dict[str, Any]],
    argv: list[str],
    start_time: float,
    overrides_used: list[dict[str, Any]] | None = None,
    preset_name: str | None = None,
    path: Path | None = None,
) -> None:
    event: dict[str, Any] = {
        "ts": _iso(start_time),
        "event": "session_start",
        "session_id": session_id,
        "profile": profile_name,
        "network_enabled": network_enabled,
        "duration_limit_seconds": duration_limit_seconds,
        "allow_broad_mount": allow_broad_mount,
        "image_tag": image_tag,
        "image_id": image_id,
        "mounts": mounts,
        "argv": argv,
        "overrides_used": overrides_used or [],
        "start_time": _iso(start_time),
    }
    # Stage 10: preset name (when launched via `whiz preset launch` or
    # `whiz r <preset>`). Absent for `whiz run` invocations. Used by
    # `whiz r` (bare) to look up the most-recent preset.
    if preset_name is not None:
        event["preset"] = preset_name
    append_event(event, path=path)


def log_session_end(
    session_id: str,
    container_id: str | None,
    exit_status: int,
    end_time: float,
    duration_seconds: float,
    path: Path | None = None,
) -> None:
    append_event(
        {
            "ts": _iso(end_time),
            "event": "session_end",
            "session_id": session_id,
            "container_id": container_id,
            "exit_status": exit_status,
            "duration_seconds": round(duration_seconds, 3),
            "end_time": _iso(end_time),
        },
        path=path,
    )


def merge_agent_events(
    session_id: str,
    event_log_path: Path,
    target_log: Path | None = None,
) -> int:
    """Merge agent-emitted events from a per-session file into the audit log.

    Stage 9 (D-156): the in-cell MCP server's `whiz_emit_event` writes
    agent-authored entries to a per-session ephemeral file. At session_end,
    Whizzard reads that file and merges entries into the main audit log.
    Each entry already has `origin: agent` from the cell-side write (per
    D-12: agent-authored entries are clearly distinguished from
    Whizzard-authored entries so they're never confused for system events).

    Defensive behavior:
    - Missing event file → return 0 (the agent may simply not have emitted)
    - Malformed JSON lines → skipped quietly (the cell may have crashed
      mid-write)
    - Entries with wrong session_id → skipped (defensive against any
      cross-session leakage that shouldn't happen but might)
    - origin marker enforced — entries without `origin` get `agent` added

    Returns the count of entries merged.
    """
    if not event_log_path.exists():
        return 0
    merged = 0
    try:
        content = event_log_path.read_text()
    except OSError:
        return 0
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("session_id") != session_id:
            continue
        entry.setdefault("origin", "agent")
        append_event(entry, path=target_log)
        merged += 1
    return merged
