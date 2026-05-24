"""Whiz MCP server — in-cell cooperation layer.

Runs as a Python child process inside the execution cell (per D-156).
Exposes a small set of tools the contained agent can call to introspect
its own Whizzard-imposed constraints (Stage 9) and to *request* changes
to them (Stage 14).

The server is configured entirely via environment variables set by the
adapter at cell launch time:

- ``WHIZ_SNAPSHOT_PATH``  — path to a JSON state snapshot (read-only)
- ``WHIZ_AUDIT_LOG_PATH`` — path to the host audit log mounted into the cell (read-only)
- ``WHIZ_EVENT_LOG_PATH`` — path to a per-session event file the agent writes
- ``WHIZ_REQUEST_DIR``    — per-session directory the agent writes requests into
- ``WHIZ_SESSION_ID``     — current session id, used to filter audit entries

Stage 9 read tools (``whiz_emit_event`` writes to a per-session ephemeral
file, *not* directly to the host audit log — Whizzard merges agent-emitted
events into the host log at session_end per D-156):

- ``whiz_status``       — current profile, mounts, network, expires_at, harness, session_id
- ``whiz_audit_self``   — this session's audit log entries (filtered by session_id)
- ``whiz_emit_event``   — agent-authored entry appended to the per-session event file

Stage 14 request tools (D-156 event-file pattern / D-165). These do NOT grant
anything — they drop a request file into ``WHIZ_REQUEST_DIR``; the host
operator reviews it via ``whiz requests`` and, if approved, applies it via the
Stage 13 stop+restart. The agent polls the outcome with ``whiz_check_request``:

- ``whiz_request_mount``  — ask the host to add a registered mount
- ``whiz_request_extend`` — ask the host to extend the session's duration
- ``whiz_check_request``  — look up the status/outcome of a prior request

Tool implementations are exposed as plain Python functions so they can be
unit-tested without spinning up an MCP runtime. The ``main()`` entry point
wraps them in MCP tool registrations using the ``mcp`` SDK; that import is
deferred so test code doesn't require the SDK.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Env-var names — module-level constants so adapters and tests share them.
ENV_SNAPSHOT_PATH = "WHIZ_SNAPSHOT_PATH"
ENV_AUDIT_LOG_PATH = "WHIZ_AUDIT_LOG_PATH"
ENV_EVENT_LOG_PATH = "WHIZ_EVENT_LOG_PATH"
ENV_REQUEST_DIR = "WHIZ_REQUEST_DIR"
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
        data: dict[str, Any] = json.loads(p.read_text())
        return data
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
    # F-A4 (catch-up review pass 2): use `ts` (matches the rest of the
    # audit log) not `timestamp`. The chunk-D F-D-08 fix unified host
    # timestamps to ISO microsecond + `ts` key; agent events were still
    # writing `timestamp` and the F-D-10 schema-version stamp didn't
    # rename them. Any analytics query that sorts/filters by `ts` would
    # silently miss every agent event. `merge_agent_events` on the host
    # side also handles the legacy `timestamp` key for in-flight events
    # written by a not-yet-rebuilt cell image.
    entry = {
        "session_id": session_id,
        "ts": datetime.now(UTC).isoformat(),
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


# F-E-01: `tool_whiz_list_presets` removed. It was a stub returning [] but
# remained registered as a production MCP tool, telling agents the preset
# registry was empty when it wasn't (D-156 cooperation-layer drift). Its
# use cases were thin — the cell already sees its own preset via
# whiz_status, and listing other presets is informational, not
# action-enabling. Removed in the catch-up review rather than implemented
# to avoid publishing a marginally-useful surface.
#
# RE-INTRODUCE IF D-171 (sub-agent permission scoping) lands: a parent
# agent choosing how to scope a sub-agent could legitimately want to
# enumerate presets to pick a narrower one. At that point the use case
# becomes action-enabling and the tool is worth bringing back.


# --- Stage 14: request-side tools ----------------------------------------
# These write a request file into WHIZ_REQUEST_DIR. They do NOT apply a
# change — the host operator reviews each request via `whiz requests` and,
# if approved, applies it via the Stage 13 stop+restart. Per D-156 the only
# channel out of the sealed cell is this mounted file; per D-165 the host
# picks it up on-demand (operator-invoked), not via a background watcher.


def _submit_request(kind: str, params: dict[str, Any], reason: str) -> dict[str, Any]:
    """Write one capability-change request to the per-session request channel.

    Shared by ``whiz_request_mount`` / ``whiz_request_extend``. The file is
    written atomically (temp + rename) so a concurrent host read never sees
    a partial record. Returns a pending-request acknowledgement — never a
    grant; the change is not in effect until the operator approves it.
    """
    request_dir = os.environ.get(ENV_REQUEST_DIR)
    session_id = os.environ.get(ENV_SESSION_ID)
    if not request_dir or not session_id:
        return {"ok": False, "error": "request channel not configured"}
    request_id = uuid.uuid4().hex[:12]
    # F-E-03: drop the cell-written `session_id` field — the host derives
    # the canonical session_id from the directory path (F-D-02) and ignores
    # any JSON-supplied value. Keeping it in the record would imply a
    # contract that no longer exists. (The `session_id` env-var lookup
    # above still gates whether the request channel is configured at all.)
    _ = session_id  # gates write attempt; not embedded in the record
    record = {
        "request_id": request_id,
        "kind": kind,
        "params": params,
        "reason": reason,
        "status": "pending",
        "created_at": datetime.now(UTC).isoformat(),
        "resolved_at": None,
        "resolution_detail": "",
    }
    try:
        d = Path(request_dir)
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / f".{request_id}.json.tmp"
        tmp.write_text(json.dumps(record, indent=2))
        tmp.replace(d / f"{request_id}.json")
    except OSError as e:
        return {"ok": False, "error": f"request write failed: {e}"}
    return {
        "ok": True,
        "request_id": request_id,
        "status": "pending",
        "note": (
            "request submitted to the host operator; it is NOT yet applied. "
            "Poll whiz_check_request with this request_id to see the outcome."
        ),
    }


def tool_whiz_request_mount(
    name: str, mode: str = "", reason: str = ""
) -> dict[str, Any]:
    """Request that Whizzard add a registered mount to this session.

    The host operator reviews the request and, if approved, applies it via a
    stop+restart of the cell (the harness's on-disk state persists across the
    restart). ``name`` is a registered mount name; ``mode`` is ``ro``/``rw``
    (omit to use the mount's registered default); ``reason`` is a short
    free-text justification the operator sees.

    Returns a pending-request acknowledgement, NOT a grant. The mount is not
    available until the operator approves it and the restart completes — poll
    ``whiz_check_request`` for the outcome.
    """
    if not name:
        return {"ok": False, "error": "mount name is required"}
    if mode and mode not in ("ro", "rw"):
        return {"ok": False, "error": f"invalid mode {mode!r}; use 'ro' or 'rw'"}
    return _submit_request("mount", {"name": name, "mode": mode or None}, reason)


def tool_whiz_request_extend(duration: str, reason: str = "") -> dict[str, Any]:
    """Request that Whizzard extend this session's duration limit.

    ``duration`` is a span like ``30m``, ``2h``, ``90s``; ``reason`` is a
    short free-text justification. As with ``whiz_request_mount`` this returns
    a pending-request acknowledgement — the extension is not in effect until
    the host operator approves it.
    """
    if not duration:
        return {"ok": False, "error": "duration is required"}
    return _submit_request("extend", {"duration": duration}, reason)


def tool_whiz_check_request(request_id: str) -> dict[str, Any]:
    """Look up the current status of a request made via ``whiz_request_*``.

    Returns the request record. Its ``status`` is one of: ``pending``
    (awaiting the operator), ``applied`` (approved and applied), ``denied``
    (the operator declined, or the request failed a pre-check), or ``error``
    (approved but applying it failed). ``resolution_detail`` carries a
    human-readable explanation once the request is resolved.
    """
    request_dir = os.environ.get(ENV_REQUEST_DIR)
    if not request_dir:
        return {"ok": False, "error": "request channel not configured"}
    p = Path(request_dir) / f"{request_id}.json"
    if not p.exists():
        return {"ok": False, "error": f"no request with id {request_id!r}"}
    try:
        return {"ok": True, "request": json.loads(p.read_text())}
    except (OSError, json.JSONDecodeError) as e:
        return {"ok": False, "error": f"request unreadable: {e}"}


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
    # Register each tool under its agent-facing name (without the `tool_`
    # Python-function prefix). FastMCP defaults to the function's __name__,
    # which would publish them as `tool_whiz_status` etc. — contrary to the
    # documented surface in architecture.md / decisions / the module
    # docstring. The MCP stdio smoke test catches this drift.
    server.tool(name="whiz_status")(tool_whiz_status)
    server.tool(name="whiz_audit_self")(tool_whiz_audit_self)
    server.tool(name="whiz_emit_event")(tool_whiz_emit_event)
    server.tool(name="whiz_request_mount")(tool_whiz_request_mount)
    server.tool(name="whiz_request_extend")(tool_whiz_request_extend)
    server.tool(name="whiz_check_request")(tool_whiz_check_request)
    server.run()


if __name__ == "__main__":
    main()
