"""Hot-restart of idle-ended sessions (Stage 15.5).

D-168: any user-initiated wake preserves the full prior permission set,
including any one-time `--allow-broad-mount` overrides. Stripping reserved
for non-user-initiated triggers (none exist today).

D-169: the four UX details:
  - `whiz wake` (bare) selects the most-recent session whose end carries
    `expiry_reason: idle` AND that has not already been woken (a woken
    session emits a `session_woken` event tying old sid → new sid; the
    selection rule excludes any sid that appears as a
    `superseded_session_id` in such an event).
  - `whiz wake <sid>` resolves by exact / prefix match against the
    session log; errors with reason on no-match, ambiguous prefix,
    not-yet-ended, ended-via-non-idle, currently-active, or already-woken.
  - Missing mounts at wake time: caller checks via `check_mounts_exist`
    and either errors or accepts `--allow-missing-mounts`; missing mounts
    are dropped from the relaunch param set when override is set.
  - Active-sid wake is refused — restarting an active session goes
    through `whiz adjust`, not `whiz wake`.

Reconstruction reuses the same shape as `adjust._apply_changes`:
mounts + profile + image + harness + preset + allow_broad_mount carried
forward from the `session_start` event. Unlike `adjust`, wake never
applies a Changes diff — it's a pure resume.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from whizzard.adjust import (
    DockerDaemonUnavailable,
    _docker_label_lookup,
    _harness_from_argv,
)
from whizzard.session_log import SESSIONS_LOG, append_event


class WakeStatus(Enum):
    OK = "ok"
    NO_ELIGIBLE = "no_eligible"  # bare wake, no idle-ended session
    NOT_FOUND = "not_found"  # sid doesn't exist in the log
    NOT_IDLE = "not_idle"  # sid ended via duration / clean — not eligible
    NOT_ENDED = "not_ended"  # sid started but never ended (crashed?)
    STILL_ACTIVE = "still_active"  # sid is currently running
    ALREADY_WOKEN = "already_woken"  # sid was already woken; pick a newer one
    AMBIGUOUS_PREFIX = "ambiguous"  # multiple sids share the given prefix
    EMPTY_PREFIX = "empty_prefix"  # whiz wake "" — nothing to look up


@dataclass(frozen=True)
class WakeCandidate:
    """A resolved, eligible session ready to wake."""

    session_id: str
    start_event: dict
    end_event: dict  # the session_end with expiry_reason=idle


@dataclass(frozen=True)
class WakeResolution:
    """Result of wake-candidate lookup."""

    status: WakeStatus
    candidate: WakeCandidate | None = None
    detail: str = ""
    candidates: tuple[str, ...] = field(default_factory=tuple)


def _read_events(path: Path | None = None) -> list[dict]:
    """Read the sessions.jsonl log into a list of event dicts."""
    target = path or SESSIONS_LOG
    if not target.exists():
        return []
    out: list[dict] = []
    for raw in target.read_text().splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _build_index(events: list[dict]) -> tuple[dict[str, dict], dict[str, dict], set[str]]:
    """Build (start, end, woken_sids) indexes from the event stream.

    The woken_sids set names any sid that appears as a `superseded_session_id`
    in a `session_woken` event — i.e., it has already been woken once and
    should not be matched again. New wakes log a `session_woken` event so
    repeated `whiz wake` doesn't double-resume the same idle session.
    """
    starts: dict[str, dict] = {}
    ends: dict[str, dict] = {}
    woken: set[str] = set()
    for ev in events:
        e_type = ev.get("event")
        sid = ev.get("session_id") or ""
        if e_type == "session_start" and sid:
            starts[sid] = ev
        elif e_type == "session_end" and sid:
            ends[sid] = ev
        elif e_type == "session_woken":
            superseded = ev.get("superseded_session_id")
            if isinstance(superseded, str):
                woken.add(superseded)
    return starts, ends, woken


def _is_active(session_id: str) -> bool:
    """True iff a docker container is currently running with this sid label.

    F-G-10 carryover: if the docker daemon is unreachable, we can't tell
    — treat as "not currently active" so the wake attempt proceeds to
    relaunch. The relaunch itself will fail loudly if the daemon is
    down, surfacing the real problem.
    """
    try:
        return bool(_docker_label_lookup(session_id))
    except DockerDaemonUnavailable:
        return False


def find_wakeable(
    sid_or_prefix: str | None = None,
    *,
    events: list[dict] | None = None,
    docker_check: bool = True,
) -> WakeResolution:
    """Find a session eligible for wake per D-169.

    Bare (`sid_or_prefix=None`): most-recent idle-ended, not-yet-woken session.
    Explicit: prefix-match against session_start sids, then run the eligibility
    gauntlet (exists → ended → idle → not woken → not currently active).

    `docker_check=False` lets unit tests skip the live-docker probe; default
    True for real CLI invocations.
    """
    if events is None:
        events = _read_events()
    starts, ends, woken = _build_index(events)

    if sid_or_prefix is None:
        # Bare: iterate session_end events in reverse, find first idle-ended
        # not-yet-woken sid.
        for ev in reversed(events):
            if ev.get("event") != "session_end":
                continue
            if ev.get("expiry_reason") != "idle":
                continue
            sid = ev.get("session_id") or ""
            if not sid or sid in woken:
                continue
            start_ev = starts.get(sid)
            if start_ev is None:
                # Defensive: orphan end with no start. Skip.
                continue
            if docker_check and _is_active(sid):
                # Already active somehow; skip and look further back.
                continue
            return WakeResolution(
                status=WakeStatus.OK,
                candidate=WakeCandidate(
                    session_id=sid, start_event=start_ev, end_event=ev,
                ),
            )
        return WakeResolution(
            status=WakeStatus.NO_ELIGIBLE,
            detail="No idle-ended session to wake.",
        )

    # Explicit sid or prefix path
    prefix = sid_or_prefix.strip()
    if not prefix:
        return WakeResolution(status=WakeStatus.EMPTY_PREFIX, detail="empty session id")

    matches = sorted(sid for sid in starts if sid.startswith(prefix))
    if not matches:
        return WakeResolution(
            status=WakeStatus.NOT_FOUND,
            detail=f"no session matching {prefix!r}",
        )
    if len(matches) > 1:
        return WakeResolution(
            status=WakeStatus.AMBIGUOUS_PREFIX,
            detail=f"ambiguous prefix {prefix!r}; matches: {', '.join(s[:12] for s in matches)}",
            candidates=tuple(matches),
        )

    sid = matches[0]

    # Active-check first per D-169: refuse to wake an already-running session.
    if docker_check and _is_active(sid):
        return WakeResolution(
            status=WakeStatus.STILL_ACTIVE,
            detail=f"Session {sid[:8]} is already running.",
        )

    if sid not in ends:
        return WakeResolution(
            status=WakeStatus.NOT_ENDED,
            detail=f"Session {sid[:8]} has no session_end recorded (crashed?).",
        )

    if sid in woken:
        return WakeResolution(
            status=WakeStatus.ALREADY_WOKEN,
            detail=f"Session {sid[:8]} was already woken; pick a more recent session.",
        )

    end_ev = ends[sid]
    reason = end_ev.get("expiry_reason", "clean")
    if reason != "idle":
        return WakeResolution(
            status=WakeStatus.NOT_IDLE,
            detail=f"Session {sid[:8]} ended via {reason}, not idle — not eligible for wake.",
        )

    return WakeResolution(
        status=WakeStatus.OK,
        candidate=WakeCandidate(
            session_id=sid, start_event=starts[sid], end_event=end_ev,
        ),
    )


def check_mounts_exist(mounts: list[dict]) -> list[str]:
    """Return paths of mounts whose `host_path` doesn't exist on disk.

    Each mount dict in the session_start event carries `host_path`
    (per docker_cmd._mounts_for_log). Missing host_path field → skipped
    silently (defensive against older log entries pre-host-path schema).
    """
    missing: list[str] = []
    for m in mounts or []:
        if not isinstance(m, dict):
            continue
        host_path = m.get("host_path")
        if not host_path:
            continue
        if not Path(host_path).expanduser().exists():
            missing.append(str(host_path))
    return missing


def reconstruct_launch_params(
    start_event: dict,
    drop_mount_names: set[str] | None = None,
) -> dict:
    """Build the launch-param dict for `_perform_launch` from a session_start.

    Mirrors `adjust._apply_changes` for the no-changes case: carries mounts,
    profile, image, harness, preset, and `allow_broad_mount` forward (D-168).
    `drop_mount_names` is the set of registered mount names to drop from
    the relaunch (used when `--allow-missing-mounts` is set and some host
    paths went missing).
    """
    drop = drop_mount_names or set()
    mount_specs: list[str] = []
    for m in start_event.get("mounts", []) or []:
        if not isinstance(m, dict):
            continue
        name = m.get("name")
        if not name or name in drop:
            continue
        mode = m.get("mode")
        mount_specs.append(f"{name}:{mode}" if mode else name)

    # F-G-02: source `allow_broad_mount` from `overrides_used` (whether the
    # original launch actually invoked the override), not from
    # `allow_broad_mount` (which is the profile *capability*).
    # `start_event["allow_broad_mount"]` being True only means the profile
    # permits the override — but the original user may not have actually
    # opted in via `--allow-broad-mount`. D-168 says wake preserves the
    # prior permission *set*, meaning the override is carried forward iff
    # it was actually used.
    original_used_override = bool(start_event.get("overrides_used"))
    return {
        "profile_name": start_event.get("profile", "default"),
        "mount_specs": mount_specs,
        "image": start_event.get("image_tag", ""),
        "allow_broad_mount": original_used_override,
        "harness": _harness_from_argv(start_event.get("argv", []) or []) or "generic",
        "preset_name": start_event.get("preset"),
    }


def missing_mount_names(start_event: dict) -> list[str]:
    """Return the *names* of mounts whose host_path is missing on disk.

    Returns the registered mount *names* (not paths) because the
    `reconstruct_launch_params` `drop_mount_names` parameter expects names.
    """
    out: list[str] = []
    for m in start_event.get("mounts", []) or []:
        if not isinstance(m, dict):
            continue
        host_path = m.get("host_path")
        name = m.get("name")
        if not host_path or not name:
            continue
        if not Path(host_path).expanduser().exists():
            out.append(str(name))
    return out


def log_wake_event(
    superseded_session_id: str,
    new_session_id: str | None = None,
    dropped_mounts: list[str] | None = None,
    path: Path | None = None,
    *,
    event: str = "session_woken",
    detail: str = "",
) -> None:
    """Append a `session_woken` audit event linking the old sid to the new.

    Same shape as `adjust._log_adjustment` but for wakes. The
    `superseded_session_id` field is the load-bearing piece —
    ``find_wakeable`` uses it to exclude already-woken sids from future
    bare-wake matches.

    F-G-11: uses ``append_event`` for consistent microsecond ISO + ``v: 1``
    schema-version stamping (F-D-08, F-D-10), instead of a manual JSON
    write that produced a Z-suffix mix and no version stamp.

    F-G-03: ``event`` lets the caller distinguish ``session_woken``
    (success — recorded only after a successful relaunch) from
    ``session_wake_failed`` (attempted but relaunch failed). The
    failure variant does NOT add the sid to the woken set (the woken
    set keys off ``session_woken`` specifically), so a failed wake
    remains visible to bare ``whiz wake``.
    """
    from datetime import UTC, datetime
    from typing import Any

    payload: dict[str, Any] = {
        "ts": datetime.now(UTC).isoformat(),
        "event": event,
        "superseded_session_id": superseded_session_id,
        "new_session_id": new_session_id,
        "dropped_mounts": dropped_mounts or [],
        "origin": "whizzard",
    }
    if detail:
        payload["detail"] = detail
    if path is not None:
        # Tests still pass an explicit path; preserve the override.
        path.parent.mkdir(parents=True, exist_ok=True)
        payload["v"] = 1  # match append_event's stamp
        with path.open("a") as fh:
            fh.write(json.dumps(payload) + "\n")
    else:
        append_event(payload)
