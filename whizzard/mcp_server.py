"""Whiz MCP server — Stage 9 read-only cooperation layer.

Runs as a Python child process inside the execution cell (per D-156).
Exposes a small set of tools the contained agent can call to introspect
its own Whizzard-imposed constraints.

The server is configured entirely via environment variables set by the
adapter at cell launch time:

- ``WHIZ_SNAPSHOT_PATH``  — path to a JSON state snapshot (read-only)
- ``WHIZ_AUDIT_LOG_PATH`` — path to the host audit log mounted into the cell (read-only)
- ``WHIZ_EVENT_LOG_PATH`` — path to a per-session event file the agent writes
- ``WHIZ_SESSION_ID``     — current session id, used to filter audit entries

Stage 9 tools (all read-only-ish; ``whiz_emit_event`` writes to a per-session
ephemeral file, *not* directly to the host audit log — Whizzard merges
agent-emitted events into the host log at session_end per D-156):

- ``whiz_status``       — current profile, mounts, network, expiry, harness, session_id
- ``whiz_audit_self``   — this session's audit log entries (filtered by session_id)
- ``whiz_emit_event``   — agent-authored entry appended to the per-session event file
- ``whiz_list_presets`` — enumerable presets (stub until Stage 10)

Tool implementations are exposed as plain Python functions so they can be
unit-tested without spinning up an MCP runtime. The ``main()`` entry point
wraps them in MCP tool registrations using the ``mcp`` SDK; that import is
deferred so test code doesn't require the SDK.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# Env-var names — module-level constants so adapters and tests share them.
ENV_SNAPSHOT_PATH = "WHIZ_SNAPSHOT_PATH"
ENV_AUDIT_LOG_PATH = "WHIZ_AUDIT_LOG_PATH"
ENV_EVENT_LOG_PATH = "WHIZ_EVENT_LOG_PATH"
ENV_SESSION_ID = "WHIZ_SESSION_ID"


def tool_whiz_status() -> dict[str, Any]:
    """Return the current session's Whizzard-imposed constraints.

    Reads the snapshot file written by Whizzard at launch. If the snapshot
    is missing or unreadable, returns an error response — the agent should
    treat this as "Whizzard's cooperation layer is not available right now"
    rather than infer state from the absence.
    """
    path = os.environ.get(ENV_SNAPSHOT_PATH)
    if not path:
        return {"error": f"{ENV_SNAPSHOT_PATH} not set"}
    p = Path(path)
    if not p.exists():
        return {"error": f"snapshot not found at {path}"}
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return {"error": f"snapshot unreadable: {e}"}


def tool_whiz_audit_self() -> list[dict[str, Any]]:
    """Return this session's audit log entries (filtered by session_id).

    Reads from the audit log mounted from the host. Returns an empty list
    if either the log path or session id env var is unset, or the log is
    absent. JSON-decode errors on individual lines are skipped quietly —
    the log can be appended to live while we read it.
    """
    audit_path = os.environ.get(ENV_AUDIT_LOG_PATH)
    session_id = os.environ.get(ENV_SESSION_ID)
    if not audit_path or not session_id:
        return []
    p = Path(audit_path)
    if not p.exists():
        return []
    entries: list[dict[str, Any]] = []
    try:
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("session_id") == session_id:
                entries.append(entry)
    except OSError:
        return []
    return entries


def tool_whiz_emit_event(event_type: str, detail: str = "") -> dict[str, Any]:
    """Append an agent-authored entry to this session's event file.

    Writes to the per-session event file inside the cell. Whizzard's
    termination flow merges these entries into the host audit log at
    session_end, tagged with ``origin: agent`` so they're not confused
    with Whizzard-authored entries (D-12 / D-156 boundary).

    Returns ``{"ok": True, "logged": <entry>}`` on success; ``{"ok": False,
    "error": <reason>}`` if the event log is not configured or writing fails.
    """
    event_log_path = os.environ.get(ENV_EVENT_LOG_PATH)
    session_id = os.environ.get(ENV_SESSION_ID)
    if not event_log_path or not session_id:
        return {"ok": False, "error": "event-logging not configured"}
    entry = {
        "session_id": session_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "detail": detail,
        "origin": "agent",
    }
    try:
        Path(event_log_path).parent.mkdir(parents=True, exist_ok=True)
        with open(event_log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError as e:
        return {"ok": False, "error": f"event write failed: {e}"}
    return {"ok": True, "logged": entry}


def tool_whiz_list_presets() -> list[dict[str, Any]]:
    """Enumerable presets. Stage 10 dependency; returns empty for now."""
    return []


# --- MCP wiring ----------------------------------------------------------
# The MCP SDK is imported lazily inside `main()` so test code can import
# this module without requiring the SDK to be installed.


def main() -> None:
    """Entry point for `python -m whizzard.mcp_server`.

    Registers the four tools with an MCP stdio server and runs it. The MCP
    client (the contained harness's MCP runtime, e.g. Hermes's) launches
    this process as a subprocess and communicates over stdio.
    """
    from mcp.server.fastmcp import FastMCP  # local import: SDK only needed here

    server = FastMCP("whiz-mcp")
    server.tool()(tool_whiz_status)
    server.tool()(tool_whiz_audit_self)
    server.tool()(tool_whiz_emit_event)
    server.tool()(tool_whiz_list_presets)
    server.run()


if __name__ == "__main__":
    main()
