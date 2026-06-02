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
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from whizzard.config import LOGS_DIR

SESSIONS_LOG = LOGS_DIR / "sessions.jsonl"

# F-D-10: every line of sessions.jsonl carries this version stamp so a
# future schema change has a robust detection handle. Mirrors what
# `validate_schema_version` does for the envelope-versioned JSON config
# files (F-A-03). The host always force-writes this — cell-merged entries
# get re-stamped to v=1 too, since the cell cannot claim a schema version.
AUDIT_LOG_SCHEMA_VERSION = 1

# F-D-04: bounds on cell-supplied agent events. A misbehaving (or
# malicious) cell can write events.jsonl at arbitrary size; without these
# caps `merge_agent_events` would balloon RAM on read and bloat the host
# audit log. Per-line cap rejects huge individual entries; total caps
# stop the merge after either limit is hit.
_AGENT_EVENT_LINE_MAX_BYTES = 64 * 1024
_AGENT_EVENT_TOTAL_LINES_MAX = 10_000
_AGENT_EVENT_TOTAL_BYTES_MAX = 16 * 1024 * 1024


def new_session_id() -> str:
    """Generate a fresh UUID for a session."""
    return str(uuid.uuid4())


def session_log_size(path: Path | None = None) -> int:
    """Current byte size of the audit log (zero if it doesn't exist).

    A3: used by wake + adjust to snapshot the log offset *before* a
    relaunch so they can detect whether `session_start` got written
    during the call — the audit-log ground truth for "did the new
    session actually launch?" (vs. "did setup fail before the
    container ever started?").
    """
    target = path or SESSIONS_LOG
    try:
        return target.stat().st_size
    except FileNotFoundError:
        return 0


def find_session_start_after_offset(
    offset: int,
    path: Path | None = None,
) -> str | None:
    """Return the session_id of the most-recent session_start event
    appended to the audit log after byte `offset`, or None if none.

    A3: wake + adjust call this after `_perform_launch` to find out
    whether a new container actually started. If yes, the relaunch
    succeeded (regardless of whatever exit code the new session
    eventually returned — SIGINT, crash, whatever); the wake/adjust
    event is logged with the recovered new sid. If no, the relaunch
    never got off the ground and the original session remains
    wakeable / adjustable.

    Closes the longstanding TODO at adjust.py:843 ("have _perform_launch
    return its sid for cleaner audit") without refactoring the five
    call sites — the audit log is the source of truth either way.
    """
    target = path or SESSIONS_LOG
    if not target.exists():
        return None
    try:
        with target.open("rb") as fh:
            fh.seek(offset)
            tail = fh.read()
    except OSError:
        return None
    text = tail.decode("utf-8", errors="replace")
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("event") == "session_start":
            sid = event.get("session_id")
            if isinstance(sid, str):
                return sid
    return None


def _iso(ts: float | None = None) -> str:
    """ISO 8601 UTC timestamp with microsecond precision (F-D-08).

    Previously this used second-precision while the cell-side and adjust
    paths used microsecond ISO — sorting by ts produced ties for events
    that happened within the same second. Microsecond throughout removes
    the tie and matches every other timestamp surface in the codebase.
    """
    if ts is None:
        return datetime.now(UTC).isoformat()
    return datetime.fromtimestamp(ts, UTC).isoformat()


def append_event(event: dict[str, Any], path: Path | None = None) -> None:
    """Append a single JSON object as one line in the sessions log.

    F-D-10: force-stamps `v = AUDIT_LOG_SCHEMA_VERSION` on every entry so
    a future schema change has a robust detection handle. Cell-supplied
    entries (via `merge_agent_events`) flow through here too and get
    re-stamped — the cell cannot claim a different schema version for
    its log entries.
    """
    target = path or SESSIONS_LOG
    target.parent.mkdir(parents=True, exist_ok=True)
    event["v"] = AUDIT_LOG_SCHEMA_VERSION
    line = json.dumps(event, separators=(",", ":"))
    # F-G-15: pin UTF-8 + LF. Default text mode on Windows translates "\n"
    # to "\r\n", which (a) skews the byte offsets the wake/adjust recovery
    # reads (find_session_start_after_offset) and (b) inflates line lengths;
    # and the default cp1252 encoding on Windows could mangle non-ASCII
    # audit content. LF + UTF-8 keeps the log byte-identical cross-platform.
    with target.open("a", encoding="utf-8", newline="\n") as f:
        f.write(line + "\n")
        # F-G-12: durable-sync each append. The wake and adjust paths
        # read the audit log immediately after writing a session_start
        # event to recover the new session_id; without fsync, an OS
        # crash between buffer-flush and disk-commit makes the running
        # container an orphan with no audit anchor. Per-event fsync
        # cost is negligible — audit writes are infrequent.
        f.flush()
        os.fsync(f.fileno())


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
    allow_ephemeral: bool = False,
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
    # A1+A2: persist the --allow-ephemeral opt-in so adjust + wake can
    # rehydrate it on relaunch. Without this, an adjust or wake of an
    # ephemeral Hermes session fails preflight (Hermes refuses without
    # hermes_home unless allow_ephemeral=True) and the session is lost.
    # Only written when set; absent for the common non-ephemeral path.
    if allow_ephemeral:
        event["allow_ephemeral"] = True
    append_event(event, path=path)


def log_session_end(
    session_id: str,
    container_id: str | None,
    exit_status: int,
    end_time: float,
    duration_seconds: float,
    path: Path | None = None,
    expiry_reason: str = "clean",
) -> None:
    """Write the session_end event.

    Stage 15: `expiry_reason` records *why* the session ended —
    ``clean`` (container exited on its own), ``duration`` (hard duration
    cap), or ``idle`` (idle timeout). Hot-restart eligibility keys off this
    field (only ``idle`` sessions are hot-restartable; see build plan
    Stage 15.5).
    """
    append_event(
        {
            "ts": _iso(end_time),
            "event": "session_end",
            "session_id": session_id,
            "container_id": container_id,
            "exit_status": exit_status,
            "duration_seconds": round(duration_seconds, 3),
            "end_time": _iso(end_time),
            "expiry_reason": expiry_reason,
        },
        path=path,
    )


def log_expiry_warning(
    session_id: str,
    seconds_remaining: int,
    path: Path | None = None,
) -> None:
    """Stage 15: a pre-expiry heads-up, written once when a session nears its
    duration cap. The in-cell agent sees it via `whiz_audit_self`; the host
    surfaces remaining time in `whiz status`. Lets either side react — extend
    the session, or checkpoint — before the cap fires.
    """
    append_event(
        {
            "ts": _iso(),
            "event": "session_expiry_warning",
            "session_id": session_id,
            "seconds_remaining": seconds_remaining,
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

    Defensive behavior:
    - Missing event file → return 0 (the agent may simply not have emitted)
    - Malformed JSON lines → skipped quietly (the cell may have crashed
      mid-write)
    - Entries with wrong session_id → skipped (defensive against cross-
      session leakage that shouldn't happen but might).
    - F-D-01: ``origin`` is force-set to ``"agent"`` regardless of what the
      cell wrote. Previously `setdefault` left a cell-supplied
      ``"origin": "whizzard"`` intact, letting an attacker-controlled agent
      forge system-authored audit entries — defeating D-12.
    - F-D-04: per-line and total-size caps prevent a cell from DoS-ing the
      host log by writing gigabytes of valid JSON. On overflow we append a
      Whizzard-origin marker event and stop reading.

    Returns the count of entries merged (not including the truncation
    marker, if any was emitted).
    """
    if not event_log_path.exists():
        return 0
    merged = 0
    bytes_seen = 0
    truncated_reason: str | None = None
    try:
        # F-D-04: stream line-by-line so a gigabyte file doesn't blow up
        # memory. The whole-file slurp this replaces meant `read_text()`
        # held the entire content before splitting.
        fh = event_log_path.open(encoding="utf-8", newline="\n")
    except OSError:
        return 0
    try:
        for raw_line in fh:
            line = raw_line.rstrip("\n").strip()
            if not line:
                continue
            line_bytes = len(raw_line.encode("utf-8"))
            if line_bytes > _AGENT_EVENT_LINE_MAX_BYTES:
                # Skip the oversize line but keep reading — one big line
                # isn't necessarily a DoS attempt, and dropping just the
                # offender preserves whatever else the agent emitted.
                continue
            bytes_seen += line_bytes
            if bytes_seen > _AGENT_EVENT_TOTAL_BYTES_MAX:
                truncated_reason = (
                    f"agent events truncated: cumulative size exceeded "
                    f"{_AGENT_EVENT_TOTAL_BYTES_MAX} bytes"
                )
                break
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(entry, dict):
                continue
            if entry.get("session_id") != session_id:
                continue
            # F-D-01: force, don't setdefault. Cell-supplied origin field
            # is overridden — only the host can claim "whizzard" origin.
            entry["origin"] = "agent"
            # F-A4 (catch-up review pass 2): backward-compat for cells
            # whose mcp_server.py was built before the timestamp→ts
            # rename. Promote `timestamp` to `ts` if `ts` is missing so
            # the audit log's sort key is uniform across host and agent
            # events, regardless of cell-image vintage.
            if "ts" not in entry and "timestamp" in entry:
                entry["ts"] = entry.pop("timestamp")
            append_event(entry, path=target_log)
            merged += 1
            if merged >= _AGENT_EVENT_TOTAL_LINES_MAX:
                truncated_reason = (
                    f"agent events truncated: merged the first "
                    f"{_AGENT_EVENT_TOTAL_LINES_MAX} entries; remainder dropped"
                )
                break
    finally:
        fh.close()

    if truncated_reason is not None:
        # Whizzard-origin marker so post-hoc audit consumers can see that
        # a truncation happened. Stamped with origin="whizzard" by the
        # explicit assignment — this is genuinely a host-authored event.
        append_event(
            {
                "ts": _iso(),
                "event": "session_agent_events_truncated",
                "session_id": session_id,
                "origin": "whizzard",
                "detail": truncated_reason,
                "merged_count": merged,
            },
            path=target_log,
        )
    return merged
