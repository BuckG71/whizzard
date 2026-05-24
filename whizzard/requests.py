"""Stage 14 — host-side reader/processor for the agent request channel.

The in-cell MCP server (`whizzard/mcp_server.py`) lets a contained agent
*request* a capability change — a new mount, a longer duration — by writing
a JSON file into the per-session request directory (`snapshot.request_dir`).
This module is the host side of that channel: it reads pending requests,
pre-validates them, and routes approved ones through `adjust_session`
(Stage 13 / D-163), which performs the stop+restart.

Per D-165 the MVP host-side pickup is the operator-invoked `whiz requests`
command (see `whizzard/cli/requests.py`), not a background watcher — Whizzard
stays CLI-driven, consistent with D-156's rejection of a host daemon. A
real-time watcher / host-side MCP server is the planned v1.0 revisit.

Request lifecycle — the `status` field in each request file:

    pending  → agent wrote it; the host has not acted
    applied  → operator approved; adjust_session completed the stop+restart
    denied   → operator declined, or the request failed pre-validation
    error    → approved, but the adjust failed partway

`agent_initiated=True` is always passed to `adjust_session` here, so the
`AGENT_ALLOWED_CHANGES` allowlist (D-163, F-G-06) applies — an agent
cannot obtain a broad-mount override or any other non-allowlisted change
through this channel even if a malformed request asks for one.
"""

from __future__ import annotations

import datetime as _dt
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import whizzard.config as _config
from whizzard.adjust import (
    AdjustResult,
    Approver,
    Changes,
    MountAddition,
    adjust_session,
    parse_duration,
)
from whizzard.config import ProfileConfigError, get_profile
from whizzard.mounts import MountRegistryError, load_mounts, resolve_mount_spec
from whizzard.safety import SafetyViolation, check_mount_path
from whizzard.session_log import SESSIONS_LOG, append_event
from whizzard.snapshot import SESSIONS_DIR


def _resolutions_path(session_id: str, request_id: str) -> Path:
    """Host-only authoritative resolution store (F-D-05).

    Lives under STATE_DIR — outside the cell-writable /run/whiz mount. The
    cell can write anything to the request file in its own request_dir;
    the host's view of a request's status comes from here instead, so a
    cell-claimed status of ``"applied"`` can never bypass operator review.

    Read STATE_DIR lazily through the config module so tests that
    monkeypatch ``config.STATE_DIR`` see the redirected path.
    """
    return _config.STATE_DIR / "request-resolutions" / session_id / f"{request_id}.json"


def _read_resolution_record(session_id: str, request_id: str) -> dict | None:
    """Return the host-only resolution record for a request, or None if
    no host resolution has been recorded yet.

    F-E-02: extends the F-D-05 store from "status only" to "the full
    canonical record". For resolved requests this is the source of truth
    for kind, params, reason, and created_at too — the cell-writable
    request file is no longer trusted for any field of a resolved
    request, closing the repaint-on-resolved attack.
    """
    p = _resolutions_path(session_id, request_id)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data

# Request kinds the agent may submit. Mirrors the `whiz_request_*` MCP tools.
VALID_KINDS = frozenset({"mount", "extend"})

# Terminal statuses — a request in one of these is resolved and `whiz requests`
# (without --all) no longer surfaces it.
TERMINAL_STATUSES = frozenset({"applied", "denied", "error"})


# --- Types ------------------------------------------------------------------


@dataclass(frozen=True)
class AgentRequest:
    """One capability-change request read from the channel.

    `path` is the backing JSON file; `mark_resolved` rewrites it in place so
    the file doubles as the audit record of the request and its outcome.
    """
    request_id: str
    session_id: str
    kind: str
    params: dict
    reason: str
    status: str
    created_at: str
    path: Path
    resolution_detail: str = ""

    def summary(self) -> str:
        """One-line human description of what the agent is asking for."""
        if self.kind == "mount":
            name = self.params.get("name", "?")
            mode = self.params.get("mode")
            return f"add mount {name}" + (f" ({mode})" if mode else "")
        if self.kind == "extend":
            return f"extend duration by {self.params.get('duration', '?')}"
        return f"{self.kind} {self.params}"


# --- Channel reading --------------------------------------------------------


def _session_request_dir(session_id: str) -> Path:
    """Per-session request directory under the (monkeypatch-friendly) module
    SESSIONS_DIR. Mirrors `snapshot.request_dir` but resolves against this
    module's SESSIONS_DIR so tests can redirect it."""
    return SESSIONS_DIR / session_id / "requests"


def _load_request(path: Path) -> AgentRequest | None:
    """Parse one request JSON file. Returns None if it is unreadable or
    structurally invalid — a corrupt file in the channel must not break
    listing the rest.

    F-D-02: ``session_id`` is derived from the directory path
    (``<SESSIONS_DIR>/<sid>/requests/<reqid>.json``) — the host owns the
    directory layout, the cell does not. A request whose JSON
    ``session_id`` field disagrees with its directory is tampering; we
    use the directory's session_id and ignore the JSON's claim.

    F-D-05: ``status`` and ``resolution_detail`` are read from the
    host-only resolutions store, not from the cell-writable request
    file. A cell-supplied ``"status": "applied"`` in a fresh request
    cannot bypass operator review — until the host has recorded a
    resolution, the request is "pending" regardless of what the cell
    wrote.
    """
    try:
        canonical_session_id = path.parent.parent.name
    except (AttributeError, IndexError):
        return None
    if not canonical_session_id:
        return None

    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    request_id = data.get("request_id")
    kind = data.get("kind")
    if not request_id or kind not in VALID_KINDS:
        return None

    # F-D-05 / F-E-02: for resolved requests, the entire record (kind,
    # params, reason, created_at, status, resolution_detail) comes from
    # the host-only store. Cell can repaint its own file with new
    # kind/params after resolution, but listing reads from the immutable
    # host snapshot. For pending requests, cell-supplied fields are
    # used — there's nothing to forge against yet.
    resolution = _read_resolution_record(canonical_session_id, str(request_id))
    if resolution is not None:
        cell_params = data.get("params")
        res_params = resolution.get("params")
        canonical_kind = str(resolution.get("kind") or kind)
        canonical_params = res_params if isinstance(res_params, dict) else (
            cell_params if isinstance(cell_params, dict) else {}
        )
        canonical_reason = str(resolution.get("reason") or data.get("reason") or "")
        canonical_created_at = str(
            resolution.get("created_at") or data.get("created_at") or ""
        )
        canonical_status = str(resolution.get("status") or "pending")
        canonical_detail = str(resolution.get("resolution_detail") or "")
    else:
        cell_params = data.get("params")
        canonical_kind = str(kind)
        canonical_params = cell_params if isinstance(cell_params, dict) else {}
        canonical_reason = str(data.get("reason") or "")
        canonical_created_at = str(data.get("created_at") or "")
        canonical_status = "pending"
        canonical_detail = ""

    return AgentRequest(
        request_id=str(request_id),
        session_id=canonical_session_id,
        kind=canonical_kind,
        params=canonical_params,
        reason=canonical_reason,
        status=canonical_status,
        created_at=canonical_created_at,
        path=path,
        resolution_detail=canonical_detail,
    )


def _read_dir(request_dir: Path, *, pending_only: bool) -> list[AgentRequest]:
    """Read every request file in one `requests/` directory."""
    if not request_dir.is_dir():
        return []
    out: list[AgentRequest] = []
    for f in sorted(request_dir.glob("*.json")):
        req = _load_request(f)
        if req is None:
            continue
        if pending_only and req.status != "pending":
            continue
        out.append(req)
    return out


def read_session_requests(
    session_id: str, *, pending_only: bool = True
) -> list[AgentRequest]:
    """All requests for one session, sorted oldest-first by creation time."""
    reqs = _read_dir(_session_request_dir(session_id), pending_only=pending_only)
    reqs.sort(key=lambda r: r.created_at)
    return reqs


def read_all_requests(*, pending_only: bool = True) -> list[AgentRequest]:
    """All requests across every session directory, sorted oldest-first."""
    if not SESSIONS_DIR.is_dir():
        return []
    out: list[AgentRequest] = []
    for sess in sorted(SESSIONS_DIR.iterdir()):
        if not sess.is_dir():
            continue
        out.extend(_read_dir(sess / "requests", pending_only=pending_only))
    out.sort(key=lambda r: r.created_at)
    return out


def find_request(request_id: str) -> AgentRequest | None:
    """Locate a request by id across all sessions. Exact match only — request
    ids are 12 hex chars, so prefix matching isn't needed."""
    for req in read_all_requests(pending_only=False):
        if req.request_id == request_id:
            return req
    return None


def mark_resolved(req: AgentRequest, status: str, detail: str) -> None:
    """Record the operator's resolution authoritatively and mirror it to
    the cell so ``whiz_check_request`` can see the outcome.

    F-D-05: the authoritative record lives in the host-only resolutions
    store (``STATE_DIR/request-resolutions/<sid>/<reqid>.json``), outside
    the cell-writable mount. The cell-visible request file is updated as
    a mirror so the cell can read the outcome via its MCP server, but the
    cell can tamper with that mirror without affecting host-side listing
    — ``_load_request`` reads status from the authoritative store.

    F-D-03: denied / error resolutions are also appended to the host
    audit log as a ``session_request_resolved`` event. ``applied`` is
    already logged by ``adjust._log_adjustment``, so we don't duplicate
    it here.
    """
    resolved_at = _dt.datetime.now(_dt.UTC).isoformat()

    # Authoritative record in the host-only store. F-E-02: snapshot the
    # full request shape (kind / params / reason / created_at) here so
    # `_load_request` can source those fields from this store for
    # resolved requests — the cell-writable file can no longer be used
    # to retroactively repaint a resolved request's apparent semantics.
    res_path = _resolutions_path(req.session_id, req.request_id)
    res_path.parent.mkdir(parents=True, exist_ok=True)
    res_path.write_text(json.dumps({
        "request_id": req.request_id,
        "session_id": req.session_id,
        "kind": req.kind,
        "params": req.params,
        "reason": req.reason,
        "created_at": req.created_at,
        "status": status,
        "resolution_detail": detail,
        "resolved_at": resolved_at,
    }, indent=2))

    # Mirror to the cell-visible request file. The cell can stomp this
    # afterward, but host listing reads from the authoritative store above.
    try:
        data = json.loads(req.path.read_text())
        if not isinstance(data, dict):
            raise ValueError
    except (OSError, json.JSONDecodeError, ValueError):
        # Backing file lost or corrupt — reconstruct from the in-memory record.
        data = {
            "request_id": req.request_id,
            "session_id": req.session_id,
            "kind": req.kind,
            "params": req.params,
            "reason": req.reason,
            "created_at": req.created_at,
        }
    data["status"] = status
    data["resolution_detail"] = detail
    data["resolved_at"] = resolved_at
    tmp = req.path.with_name(f".{req.path.name}.tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(req.path)

    # F-D-03: log denials/errors to the host audit log. Applied resolutions
    # are already logged by adjust._log_adjustment; we skip them here so the
    # log doesn't carry duplicate events for the same outcome.
    if status in ("denied", "error"):
        append_event({
            "ts": resolved_at,
            "event": "session_request_resolved",
            "session_id": req.session_id,
            "request_id": req.request_id,
            "kind": req.kind,
            "params": req.params,
            "status": status,
            "resolution_detail": detail,
            "origin": "whizzard",
        })


# --- Request → Changes mapping + validation ---------------------------------


def request_to_changes(req: AgentRequest) -> Changes:
    """Map a request to a Stage 13 `Changes`. Raises ValueError on a
    structurally bad request (missing/invalid params)."""
    if req.kind == "mount":
        name = req.params.get("name")
        if not name:
            raise ValueError("mount request is missing 'name'")
        mode = req.params.get("mode")
        if mode is not None and mode not in ("ro", "rw"):
            raise ValueError(f"invalid mount mode {mode!r}; use 'ro' or 'rw'")
        return Changes(add_mounts=(MountAddition(name=str(name), mode=mode),))
    if req.kind == "extend":
        spec = req.params.get("duration")
        if not spec:
            raise ValueError("extend request is missing 'duration'")
        return Changes(extend_seconds=parse_duration(str(spec)))
    raise ValueError(f"unknown request kind {req.kind!r}")


def _session_profile_name(session_id: str) -> str:
    """Profile name from the session's session_start event, or 'default' if
    not found. Used only for the pre-flight mount safety check."""
    if not SESSIONS_LOG.exists():
        return "default"
    for raw in SESSIONS_LOG.read_text().splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("event") == "session_start" and ev.get("session_id") == session_id:
            return str(ev.get("profile") or "default")
    return "default"


def validate_request(req: AgentRequest) -> str | None:
    """Pre-flight a request BEFORE any stop+restart. Returns an error string
    if it cannot be safely applied, else None.

    Critical for the mount case: an agent-requested mount that needs a
    broad-mount override must be rejected *here*. If it reached the relaunch
    it would fail `check_mount_path` only *after* the container is already
    stopped, killing the session. The pre-flight denies it cleanly with the
    session still running.
    """
    try:
        changes = request_to_changes(req)
    except ValueError as e:
        return str(e)

    if req.kind == "extend":
        # parse_duration already ran inside request_to_changes; enforcement of
        # the extended duration itself is Stage 15. Nothing else to check.
        return None

    if req.kind == "mount":
        try:
            registry = load_mounts()
        except MountRegistryError as e:
            return f"cannot load the mount registry: {e}"
        add = changes.add_mounts[0]
        try:
            mount, _mode = resolve_mount_spec(add.name, registry)
        except MountRegistryError:
            available = ", ".join(sorted(registry)) or "(none registered)"
            return (
                f"mount {add.name!r} is not registered; an agent can only "
                f"request registered mounts. Available: {available}"
            )
        try:
            profile = get_profile(_session_profile_name(req.session_id))
        except (KeyError, ProfileConfigError) as e:
            return f"cannot load the session's profile: {e}"
        other_paths = [
            other.host_path for name, other in registry.items()
            if name != mount.name
        ]
        try:
            check_mount_path(
                mount.host_path,
                profile,
                False,  # agents can never trigger a broad-mount override
                other_registered_paths=other_paths,
            )
        except SafetyViolation as e:
            return (
                f"mount {add.name!r} needs a broad-mount override, which an "
                f"agent cannot request via this channel ({e})"
            )
        return None

    return f"unknown request kind {req.kind!r}"


# --- Processing -------------------------------------------------------------


def process_request(
    req: AgentRequest,
    approver: Approver,
    *,
    relauncher: Callable[[dict], int] | None = None,
) -> AdjustResult:
    """Validate, then route an approved request through `adjust_session`.

    Always runs with `agent_initiated=True`, so the `AGENT_ALLOWED_CHANGES`
    allowlist applies (default-deny per F-G-06). Pre-validation failures and the adjust outcome are both
    written back into the request file via `mark_resolved`, so both
    `whiz_check_request` (cell side) and `whiz requests` (host side) see it.

    `relauncher` is forwarded to `adjust_session` — tests inject a fake to
    avoid invoking docker.
    """
    error = validate_request(req)
    if error is not None:
        mark_resolved(req, "denied", error)
        return AdjustResult(exit_code=2, detail=error)

    # Safe: validate_request already parsed the request without raising.
    changes = request_to_changes(req)
    result = adjust_session(
        req.session_id,
        changes,
        approver,
        agent_initiated=True,
        relauncher=relauncher,
    )
    if result.exit_code == 0:
        mark_resolved(req, "applied", result.detail or "applied")
    elif result.exit_code == 1:
        mark_resolved(req, "denied", result.detail or "declined by operator")
    else:
        mark_resolved(req, "error", result.detail or "adjust failed")
    return result
