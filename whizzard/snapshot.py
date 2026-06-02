"""Per-session state snapshot for the in-cell MCP server (D-156).

Whizzard writes a JSON snapshot of the launch-time session state into a
per-session directory before container start. The Hermes adapter (and
future MCP-using adapters) mount that directory into the cell so the
in-cell MCP server (`whizzard/mcp_server.py`) can read it.

Snapshot layout:

    <WHIZZARD_HOME>/sessions/<session_id>/
        snapshot.json   ← written here by `write_snapshot`
        events.jsonl    ← written by the in-cell MCP server as the agent
                          emits events; merged into the host audit log at
                          session_end (see `session_log.py`)
        requests/       ← one JSON file per agent capability-change request
                          (Stage 14, D-165); the host reads these via
                          `whiz requests` (see `whizzard/requests.py`)

Snapshot content is read-only from the cell's perspective; the event file
is the cell-writable channel back to host. Per D-12, the snapshot does
*not* include anything that would let the agent influence its own
permission boundary — only descriptive fields (what is, not what could be).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from whizzard._atomic import atomic_write_text
from whizzard.config import WHIZZARD_HOME
from whizzard.mounts import Mount, MountMode

SESSIONS_DIR = WHIZZARD_HOME / "sessions"


def session_dir(session_id: str, whizzard_home: Path | None = None) -> Path:
    """Per-session state directory: ``<WHIZZARD_HOME>/sessions/<session_id>``."""
    base = (whizzard_home or WHIZZARD_HOME) / "sessions"
    return base / session_id


def snapshot_path(session_id: str, whizzard_home: Path | None = None) -> Path:
    """Path to the JSON snapshot file for a session."""
    return session_dir(session_id, whizzard_home) / "snapshot.json"


def event_log_path(session_id: str, whizzard_home: Path | None = None) -> Path:
    """Path to the per-session agent-event file the cell writes to."""
    return session_dir(session_id, whizzard_home) / "events.jsonl"


def request_dir(session_id: str, whizzard_home: Path | None = None) -> Path:
    """Per-session directory holding agent capability-change requests.

    The in-cell MCP server writes one JSON file per request here (Stage 14,
    D-165); the host reads them via `whiz requests`. It sits inside the
    per-session directory so the existing `/run/whiz` bind mount exposes it
    to the cell with no extra `-v` flag.
    """
    return session_dir(session_id, whizzard_home) / "requests"


def write_snapshot(
    session_id: str,
    profile,
    resolved_mounts: list[tuple[Mount, MountMode]],
    harness_name: str,
    whizzard_home: Path | None = None,
    duration_override_seconds: int | None = None,
) -> Path:
    """Write the launch-time state snapshot for the cell's MCP server.

    Returns the path to the written file. Creates the per-session directory
    if it doesn't exist. Profile is typed `Any` to avoid a hard import of
    `whizzard.config.Profile` in this module's signature; the caller passes
    a `Profile` instance.

    ``duration_override_seconds`` (F-D-06): when set, this is the effective
    duration cap for the session — typically from an ``oiq adjust --extend``
    relaunch. The snapshot records the effective limit, not the underlying
    profile value, so the agent's ``whiz_status`` reports the same cap that
    enforcement is using. Per D-156 the snapshot is "the agent's view of
    its own constraints" — that view must reflect runtime overrides.
    """
    directory = session_dir(session_id, whizzard_home)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "snapshot.json"

    effective_duration = (
        duration_override_seconds
        if duration_override_seconds is not None
        else profile.duration_seconds
    )

    # F-E-04: compute an absolute expires_at instead of making the agent
    # do wall-clock math against `snapshot_written_at + duration_seconds`.
    # `None` when the session is unlimited (duration_seconds=None). Uses a
    # single `now` reading so snapshot_written_at and the expires_at base
    # don't drift relative to each other.
    now = datetime.now(UTC)
    snapshot_written_at = now.isoformat()
    expires_at: str | None = None
    if effective_duration is not None:
        expires_at = (now + timedelta(seconds=effective_duration)).isoformat()

    payload: dict[str, Any] = {
        "session_id": session_id,
        "profile": {
            "name": profile.name,
            "network_enabled": profile.network_enabled,
            "duration_seconds": effective_duration,
            "idle_timeout_seconds": profile.idle_timeout_seconds,
            "allow_broad_mount": profile.allow_broad_mount,
            "description": profile.description,
        },
        "mounts": [
            {
                "name": m.name,
                "host_path": m.host_path.as_posix(),
                "container_path": m.container_path(),
                "mode": str(mode),
            }
            for m, mode in resolved_mounts
        ],
        "harness": harness_name,
        "snapshot_written_at": snapshot_written_at,
        "expires_at": expires_at,
    }
    # Record the override explicitly so the cell can tell "extended via
    # adjust" from "profile says X" — useful in the capability banner.
    if duration_override_seconds is not None:
        payload["profile"]["duration_override_active"] = True

    atomic_write_text(target, json.dumps(payload, indent=2))
    return target
