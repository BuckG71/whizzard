"""Stage 13 — mid-session capability adjustment (`oiq adjust`).

Implements the stop+restart mechanism per D-27 with a typed library surface
that Stage 13's CLI command and Stage 14's MCP request handler both consume.
Design captured in D-163.

This module is the CORE LOGIC layer:
- `Changes` describes a requested mutation
- `Approver` is a callable interface for human / agent approval surfaces
- `adjust_session()` is the entry point both CLI and MCP eventually call
- `AGENT_DENIED_CHANGES` is the Stage 14 filter — humans can request anything
  in this list, agents cannot

The CLI command + TTY approver live in `whizzard/cli/adjust.py`. Tests in
`tests/test_adjust.py`.
"""

from __future__ import annotations

import calendar
import json
import re
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from whizzard.session_log import SESSIONS_LOG

# --- Constants --------------------------------------------------------------

# Stage 14 forward-compat (D-163 Notes): mutations the agent-via-MCP path
# is NEVER allowed to request. The human-on-TTY adjust path ignores this
# list. Anything mutation that crosses a safety gate, escalates privilege,
# or fundamentally changes the cell's posture belongs here.
AGENT_DENIED_CHANGES: frozenset[str] = frozenset({
    "allow_broad_mount",
    "change_profile",
})


# --- Types ------------------------------------------------------------------


@dataclass(frozen=True)
class MountAddition:
    """One mount to add. `mode` is None when the user didn't specify one
    (the mount's registered default_mode applies in that case)."""
    name: str
    mode: str | None = None


@dataclass(frozen=True)
class Changes:
    """The set of mutations a single `oiq adjust` invocation requests.

    Empty fields mean "no change to this axis." Combinable in one call —
    e.g., adding mount X while extending by 30 minutes is one Changes
    object, one approval prompt, one stop+restart cycle.
    """
    add_mounts: tuple[MountAddition, ...] = ()
    remove_mounts: tuple[str, ...] = ()
    extend_seconds: int | None = None
    allow_broad_mount: bool = False

    def is_empty(self) -> bool:
        return (
            not self.add_mounts
            and not self.remove_mounts
            and self.extend_seconds is None
            and not self.allow_broad_mount
        )

    def is_narrowing_only(self) -> bool:
        """True iff every change in this Changes is unambiguously narrowing
        (currently: only `remove_mounts` qualifies). Narrowing-only adjusts
        skip the TTY approval prompt per D-163."""
        return (
            bool(self.remove_mounts)
            and not self.add_mounts
            and self.extend_seconds is None
            and not self.allow_broad_mount
        )


class ResolutionStatus(Enum):
    """Outcome of resolving a user-supplied session-id (or prefix) to a
    running container."""
    FOUND = "found"
    AMBIGUOUS_PREFIX = "ambiguous_prefix"
    ENDED = "ended"
    CRASHED = "crashed"
    NOT_FOUND = "not_found"


@dataclass(frozen=True)
class SessionResolution:
    """Result of `resolve_session()`. `container_id` and `session_id` are
    set only when status == FOUND. The other fields carry information used
    to build the user-facing error message for the failure branches."""
    status: ResolutionStatus
    container_id: str | None = None
    session_id: str | None = None
    candidates: tuple[str, ...] = ()  # ambiguous_prefix or not_found suggestions
    ended_at: str | None = None       # ended case
    detail: str = ""                  # human-readable extra info


@dataclass(frozen=True)
class AdjustResult:
    """Outcome of `adjust_session()`. `exit_code == 0` means the adjust
    completed; non-zero codes mirror the CLI exit codes the caller will
    surface."""
    exit_code: int
    detail: str = ""
    new_session_id: str | None = None


# Approver protocol. The CLI passes `tty_approver` (interactive prompt);
# Stage 14's MCP handler will pass an MCP-mediated approver. Receives a
# rendered diff string; returns True to proceed, False to cancel.
Approver = Callable[[str], bool]


# --- Helpers ----------------------------------------------------------------


_DURATION_RE = re.compile(r"^(\d+)\s*(s|sec|m|min|h|hr)?$", re.IGNORECASE)


def parse_duration(spec: str) -> int:
    """Parse '30m' / '90s' / '2h' / '3600' into seconds.

    Bare integer is interpreted as seconds for backward-compat with anyone
    who'd write `--extend 1800`. Letter-suffix forms (s/m/h, with optional
    full-word variants) are preferred in user-facing docs.
    """
    spec = spec.strip()
    m = _DURATION_RE.match(spec)
    if not m:
        raise ValueError(f"invalid duration {spec!r}; use formats like '30m', '2h', '90s'")
    value = int(m.group(1))
    unit = (m.group(2) or "s").lower()
    if unit in ("s", "sec"):
        return value
    if unit in ("m", "min"):
        return value * 60
    if unit in ("h", "hr"):
        return value * 3600
    raise ValueError(f"invalid duration unit in {spec!r}")


def _read_session_events() -> list[dict]:
    """Same shape as cli._session._read_session_events but local to avoid
    a cross-package import here (adjust.py is a library module, cli imports
    from us, not the other way)."""
    if not SESSIONS_LOG.exists():
        return []
    out: list[dict] = []
    for raw in SESSIONS_LOG.read_text().splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _docker_label_lookup(session_id_prefix: str) -> list[tuple[str, str]]:
    """Return [(session_id, container_id), ...] for running containers whose
    `whizzard.session_id` label starts with the given prefix. Empty list
    means no match. Defensive against `docker` not being on PATH."""
    try:
        result = subprocess.run(
            ["docker", "ps", "--no-trunc",
             "--format", "{{.Label \"whizzard.session_id\"}}\t{{.ID}}"],
            capture_output=True, text=True, timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    matches: list[tuple[str, str]] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line or "\t" not in line:
            continue
        sid, cid = line.split("\t", 1)
        if sid and sid.startswith(session_id_prefix):
            matches.append((sid, cid))
    return matches


def resolve_session(session_id_or_prefix: str) -> SessionResolution:
    """Map a user-supplied session id (full or prefix) to a running container.

    Resolution order per D-163:
      1. Docker label lookup, exact match → FOUND
      2. Docker label lookup, prefix match (>= 4 chars) → FOUND if unique,
         AMBIGUOUS_PREFIX if multiple
      3. Cross-check session log:
         - matching session_start with later session_end → ENDED
         - matching session_start without session_end → CRASHED
         - no matching session_start → NOT_FOUND with recent-session suggestions
    """
    prefix = session_id_or_prefix.strip()
    if not prefix:
        return SessionResolution(
            status=ResolutionStatus.NOT_FOUND,
            detail="empty session id",
        )

    # Docker lookup (handles both exact and prefix; exact is just len-equal prefix)
    matches = _docker_label_lookup(prefix)
    if len(matches) == 1:
        sid, cid = matches[0]
        return SessionResolution(
            status=ResolutionStatus.FOUND,
            session_id=sid,
            container_id=cid,
        )
    if len(matches) > 1:
        return SessionResolution(
            status=ResolutionStatus.AMBIGUOUS_PREFIX,
            candidates=tuple(sid for sid, _ in matches),
        )

    # No running container with that label. Cross-check the session log.
    events = _read_session_events()
    starts = [e for e in events if e.get("event") == "session_start"
              and (e.get("session_id") or "").startswith(prefix)]
    if not starts:
        # No record of this session at all → likely a typo.
        recent = [
            (e.get("session_id") or "")[:8]
            for e in reversed(events)
            if e.get("event") == "session_start"
        ][:5]
        return SessionResolution(
            status=ResolutionStatus.NOT_FOUND,
            candidates=tuple(recent),
        )

    # Found in the log. Did it end?
    matched_start = starts[-1]  # most recent matching start
    matched_sid: str | None = matched_start.get("session_id")
    end = next(
        (e for e in events
         if e.get("event") == "session_end" and e.get("session_id") == matched_sid),
        None,
    )
    if end is not None:
        return SessionResolution(
            status=ResolutionStatus.ENDED,
            session_id=matched_sid,
            ended_at=end.get("end_time") or end.get("ts"),
        )
    return SessionResolution(
        status=ResolutionStatus.CRASHED,
        session_id=matched_sid,
        detail="session_start exists but no session_end recorded",
    )


# --- Diff rendering ---------------------------------------------------------


def render_diff(changes: Changes, session_id: str) -> str:
    """Compact human-readable diff of what `changes` will do, for use in
    the approval prompt. Skips axes that aren't changing."""
    lines = [f"Session: {session_id[:12]}"]
    if changes.add_mounts:
        for m in changes.add_mounts:
            mode_str = f":{m.mode}" if m.mode else ""
            lines.append(f"  + mount  {m.name}{mode_str}")
    if changes.remove_mounts:
        for name in changes.remove_mounts:
            lines.append(f"  - mount  {name}")
    if changes.extend_seconds is not None:
        if changes.extend_seconds % 3600 == 0 and changes.extend_seconds >= 3600:
            dur = f"{changes.extend_seconds // 3600}h"
        elif changes.extend_seconds % 60 == 0:
            dur = f"{changes.extend_seconds // 60}m"
        else:
            dur = f"{changes.extend_seconds}s"
        lines.append(f"  ~ extend duration by {dur}")
    if changes.allow_broad_mount:
        lines.append("  ~ allow broad-mount overrides for this session")
    return "\n".join(lines)


# --- Core orchestration -----------------------------------------------------
#
# `adjust_session()` is intentionally narrow in Stage 13: it validates the
# changes, resolves the session, prompts for approval via the supplied
# Approver, and then delegates the actual stop+restart to a helper. The
# stop+restart helper isn't implemented here yet — it requires reconstructing
# launch parameters from the session_start event and re-invoking the launch
# path, which is the second phase of Stage 13 implementation. The structure
# below is the contract Stage 14 will plug into.


@dataclass(frozen=True)
class DeniedChange:
    """Raised-as-value when an agent-initiated request hits AGENT_DENIED_CHANGES."""
    field: str
    reason: str = "not permitted via agent-initiated request"


def check_agent_allowed(changes: Changes) -> DeniedChange | None:
    """For agent-initiated `adjust_session()` calls (Stage 14), reject any
    change that touches a field in AGENT_DENIED_CHANGES. Human-initiated
    calls bypass this check.

    Returns the first denied change found, or None if all changes are
    agent-permitted.
    """
    if changes.allow_broad_mount and "allow_broad_mount" in AGENT_DENIED_CHANGES:
        return DeniedChange(field="allow_broad_mount")
    # change_profile not yet a field on Changes; added when that feature lands.
    return None


# --- No-op detection --------------------------------------------------------


def _harness_from_argv(argv: list) -> str | None:
    """Extract the harness name from a session_start argv list. Returns None
    if no `whizzard.harness=` label is found (which shouldn't happen for
    correctly-recorded events)."""
    for i, arg in enumerate(argv):
        if isinstance(arg, str) and arg.startswith("whizzard.harness=") \
                and i > 0 and argv[i - 1] == "--label":
            return arg.split("=", 1)[1]
    return None


def detect_noops(changes: Changes, start_event: dict) -> tuple[Changes, list[str]]:
    """Filter `changes` to drop axes that are already in the requested state,
    and return (effective_changes, warnings). The warnings list contains
    human-readable strings for each no-op axis, suitable for printing to the
    user before / instead of an approval prompt.

    Per D-163: no-ops warn but don't error; effective_changes may be empty
    after filtering, in which case the caller can early-exit with the
    warnings as the user-facing message.
    """
    warnings: list[str] = []
    current_mount_names = {
        (m.get("name") if isinstance(m, dict) else None)
        for m in start_event.get("mounts", [])
    }
    current_mount_names.discard(None)

    effective_adds: list[MountAddition] = []
    for m in changes.add_mounts:
        if m.name in current_mount_names:
            warnings.append(f"mount {m.name!r} is already attached; no change made")
        else:
            effective_adds.append(m)

    effective_removes: list[str] = []
    for name in changes.remove_mounts:
        if name not in current_mount_names:
            warnings.append(f"mount {name!r} is not currently attached; no change made")
        else:
            effective_removes.append(name)

    effective_extend = changes.extend_seconds
    if changes.extend_seconds is not None and start_event.get("duration_limit_seconds") is None:
        warnings.append(
            f"session has no duration limit; nothing to extend (--extend {changes.extend_seconds}s ignored)"
        )
        effective_extend = None

    return (
        Changes(
            add_mounts=tuple(effective_adds),
            remove_mounts=tuple(effective_removes),
            extend_seconds=effective_extend,
            allow_broad_mount=changes.allow_broad_mount,
        ),
        warnings,
    )


# --- Stop + relaunch --------------------------------------------------------


def _stop_container(container_id: str, grace_seconds: int = 30) -> tuple[int, str]:
    """Stop a running container via `docker stop --time=<grace>`. Returns
    (exit_code, detail). Non-zero exit means the stop call itself failed
    (container missing, daemon unreachable, etc.). docker stop blocks
    until the container exits or the grace window expires."""
    try:
        result = subprocess.run(
            ["docker", "stop", "--time", str(grace_seconds), container_id],
            capture_output=True, text=True, timeout=grace_seconds + 10,
        )
    except FileNotFoundError:
        return 127, "docker not found on PATH"
    except subprocess.TimeoutExpired:
        return 1, f"docker stop did not return within {grace_seconds + 10}s"
    if result.returncode != 0:
        return result.returncode, (result.stderr or "").strip() or "docker stop failed"
    return 0, ""


def _session_elapsed_seconds(start_event: dict) -> float:
    """Seconds elapsed since the session originally started, derived from
    the session_start event's timestamp. Returns 0.0 if unparseable."""
    raw = start_event.get("start_time") or start_event.get("ts")
    if not isinstance(raw, str):
        return 0.0
    try:
        struct = time.strptime(raw, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return 0.0
    return max(0.0, time.time() - calendar.timegm(struct))


def _apply_changes(start_event: dict, changes: Changes) -> dict:
    """Compute the launch-parameter dict for the relaunch by applying
    `changes` to the original session's launch params. Returns a dict
    with the keys `_perform_launch` consumes."""
    # Carry forward original mounts; apply add/remove.
    mount_specs: list[str] = []
    removed = set(changes.remove_mounts)
    for m in start_event.get("mounts", []):
        if not isinstance(m, dict):
            continue
        name = m.get("name")
        if name and name not in removed:
            mode = m.get("mode")
            mount_specs.append(f"{name}:{mode}" if mode else name)
    for add in changes.add_mounts:
        mount_specs.append(f"{add.name}:{add.mode}" if add.mode else add.name)

    # Stage 15: carry the duration cap across the relaunch. The relaunched
    # container's clock starts fresh, so the override is the *remaining*
    # time (original limit minus elapsed) plus any `--extend`. This both
    # preserves the cap on a non-extend adjust and makes `--extend` mean
    # "remaining + N", not "a fresh full window". An unlimited session
    # (original limit None) stays unlimited. Floored so an adjust near
    # expiry doesn't relaunch into an instant kill.
    original_limit = start_event.get("duration_limit_seconds")
    duration_override: int | None = None
    if isinstance(original_limit, int):
        remaining = original_limit - _session_elapsed_seconds(start_event)
        duration_override = max(int(remaining) + (changes.extend_seconds or 0), 60)

    return {
        "profile_name": start_event.get("profile", "default"),
        "mount_specs": mount_specs,
        "image": start_event.get("image_tag", ""),
        "allow_broad_mount": (
            changes.allow_broad_mount
            or bool(start_event.get("allow_broad_mount"))
        ),
        "harness": _harness_from_argv(start_event.get("argv", []) or []) or "generic",
        "preset_name": start_event.get("preset"),
        "duration_override_seconds": duration_override,
    }


def _log_adjustment(superseded_session_id: str, changes: Changes,
                    new_session_id: str | None = None) -> None:
    """Append an adjustment event to the session log linking the old session
    to the new. Lightweight: not a session_start/session_end pair, just a
    breadcrumb so audit consumers can follow the chain."""
    import datetime as _dt
    payload = {
        "ts": _dt.datetime.now(_dt.UTC).isoformat().replace("+00:00", "Z"),
        "event": "session_adjusted",
        "superseded_session_id": superseded_session_id,
        "new_session_id": new_session_id,
        "changes": {
            "add_mounts": [{"name": m.name, "mode": m.mode} for m in changes.add_mounts],
            "remove_mounts": list(changes.remove_mounts),
            "extend_seconds": changes.extend_seconds,
            "allow_broad_mount": changes.allow_broad_mount,
        },
    }
    SESSIONS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with SESSIONS_LOG.open("a") as fh:
        fh.write(json.dumps(payload) + "\n")


def _resolution_error_message(resolution: SessionResolution,
                              session_id_or_prefix: str) -> str:
    """Format a user-facing error for non-FOUND resolutions per D-163."""
    if resolution.status == ResolutionStatus.AMBIGUOUS_PREFIX:
        short = [c[:12] for c in resolution.candidates]
        return (
            f"ambiguous session id {session_id_or_prefix!r}; matches: "
            f"{', '.join(short)}; use a longer prefix"
        )
    if resolution.status == ResolutionStatus.ENDED:
        when = resolution.ended_at or "unknown time"
        return (
            f"session {resolution.session_id} ended at {when}; "
            f"can't adjust an ended session. Start a new one with: oiq r [preset]"
        )
    if resolution.status == ResolutionStatus.CRASHED:
        return (
            f"session {resolution.session_id} has no session_end recorded; "
            "container may have crashed or been killed externally. "
            "Start a new one with: oiq r [preset]"
        )
    # NOT_FOUND
    if resolution.candidates:
        recent = ", ".join(resolution.candidates)
        return (
            f"no session matching {session_id_or_prefix!r}. "
            f"Recent sessions: {recent} (run `oiq s` for full list)"
        )
    return (
        f"no session matching {session_id_or_prefix!r}; "
        "no sessions in the log yet. Start one with: oiq r [preset]"
    )


def adjust_session(
    session_id_or_prefix: str,
    changes: Changes,
    approver: Approver,
    *,
    agent_initiated: bool = False,
    relauncher: Callable[[dict], int] | None = None,
) -> AdjustResult:
    """End-to-end adjust: resolve session, validate, prompt, stop, relaunch.

    `agent_initiated=True` enforces the AGENT_DENIED_CHANGES filter; default
    False means human-initiated and all changes are permitted.

    `relauncher` is a callable that takes the new-launch-params dict and
    returns the relaunch's exit code. Default `None` uses the CLI launch
    path (`whizzard.cli._launch._perform_launch`). Tests can inject a fake
    relauncher to avoid actually invoking docker.
    """
    if changes.is_empty():
        return AdjustResult(exit_code=2, detail="no changes requested; nothing to do")

    if agent_initiated:
        denied = check_agent_allowed(changes)
        if denied is not None:
            return AdjustResult(
                exit_code=2,
                detail=f"agent cannot request change to {denied.field}: {denied.reason}",
            )

    resolution = resolve_session(session_id_or_prefix)
    if resolution.status != ResolutionStatus.FOUND:
        return AdjustResult(
            exit_code=2,
            detail=_resolution_error_message(resolution, session_id_or_prefix),
        )

    # Invariant: status FOUND ⇒ session_id and container_id are populated.
    assert resolution.session_id is not None
    assert resolution.container_id is not None
    session_id = resolution.session_id
    container_id = resolution.container_id

    events = _read_session_events()
    start_event = next(
        (e for e in events
         if e.get("event") == "session_start"
         and e.get("session_id") == session_id),
        None,
    )
    if start_event is None:
        return AdjustResult(
            exit_code=2,
            detail=(
                f"session {session_id} container found but its "
                "session_start event is missing from the log"
            ),
        )

    effective_changes, warnings = detect_noops(changes, start_event)
    if effective_changes.is_empty():
        return AdjustResult(
            exit_code=0,
            detail="\n".join(warnings) if warnings else "no-op",
        )

    diff = render_diff(effective_changes, session_id)
    # Prepend any no-op warnings to the diff so the user sees the full picture.
    if warnings:
        diff = "\n".join(warnings) + "\n\n" + diff

    if not effective_changes.is_narrowing_only() and not approver(diff):
        return AdjustResult(exit_code=1, detail="cancelled")

    new_params = _apply_changes(start_event, effective_changes)

    stop_code, stop_detail = _stop_container(container_id)
    if stop_code != 0:
        return AdjustResult(
            exit_code=stop_code,
            detail=f"failed to stop container: {stop_detail}",
        )

    _log_adjustment(session_id, effective_changes)

    if relauncher is None:
        relauncher = _default_relauncher
    relaunch_code = relauncher(new_params)
    return AdjustResult(exit_code=relaunch_code, detail="adjusted")


def _default_relauncher(new_params: dict) -> int:
    """Default relaunch path: invoke the CLI's `_perform_launch`. `_perform_launch`
    raises typer.Exit on every path; translate that to an integer exit code."""
    import typer

    from whizzard.cli._launch import _perform_launch

    try:
        _perform_launch(
            profile_name=new_params["profile_name"],
            mount_specs=new_params["mount_specs"],
            image=new_params["image"],
            dry_run=False,
            allow_broad_mount=new_params["allow_broad_mount"],
            harness=new_params["harness"],
            preset_name=new_params.get("preset_name"),
            duration_override_seconds=new_params.get("duration_override_seconds"),
        )
    except typer.Exit as e:  # noqa: F841
        return int(e.exit_code) if e.exit_code is not None else 0
    return 0
