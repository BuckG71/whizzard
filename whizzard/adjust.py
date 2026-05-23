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

import json
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

from whizzard.session_log import SESSIONS_LOG, append_event

# --- Constants --------------------------------------------------------------

# F-G-06: allowlist (default-deny) for agent-via-MCP requests. Anything in
# `Changes` not listed here is rejected for `agent_initiated=True` calls.
# The human-on-TTY adjust path bypasses this filter. Default-deny is
# important because adding a new `Changes` field (e.g., a future
# `change_profile` axis) must NOT silently become agent-requestable — it
# must be explicitly opted in by adding the field name here. Stage 14
# (D-165) and the host-side MCP path build on this guarantee.
AGENT_ALLOWED_CHANGES: frozenset[str] = frozenset({
    "add_mounts",
    "remove_mounts",
    "extend_seconds",
})

# F-G-14: hard upper bound on `--extend` to prevent a typo (`--extend
# 99999h`) from effectively unlimiting the session. 7 days is generous
# for a single extend; users can extend again if they really need more.
_MAX_EXTEND_SECONDS = 7 * 24 * 60 * 60  # 604_800

# Daemon-down indicators — mirrors `docker_cmd._DAEMON_DOWN_INDICATORS`
# (kept local to avoid importing the docker_cmd module for the substring
# match alone). If `docker ps` returns these phrases in stderr, the
# daemon is unreachable — surfaced as a distinct resolution status so
# the user sees "Docker Desktop not running" instead of "session not
# found" (F-G-10).
_DAEMON_DOWN_INDICATORS = (
    "Cannot connect to the Docker daemon",
    "Is the docker daemon running",
    "error during connect",
)


class DockerDaemonUnavailable(Exception):
    """Raised by `_docker_label_lookup` when docker stderr indicates the
    daemon is unreachable (vs. simply having no containers with our
    label). Caught at `resolve_session` and converted to a distinct
    `ResolutionStatus.DAEMON_UNAVAILABLE` (F-G-10)."""


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
    # F-G-10: docker CLI is installed but the daemon isn't reachable.
    # Distinct from NOT_FOUND so the user sees "start Docker Desktop"
    # instead of "use a longer prefix."
    DAEMON_UNAVAILABLE = "daemon_unavailable"


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

    F-G-07: rejects 0 (and anything ≤0) — a 0-second extension is not a
    real change, but `Changes(extend_seconds=0)` previously satisfied
    `is_empty()` and triggered a real stop+restart cycle.

    F-G-14: hard-caps at 7 days. A typo (`--extend 99999h`) effectively
    unlimits the session, defeating the safety budget. The user can
    extend again if they really need more.
    """
    spec = spec.strip()
    m = _DURATION_RE.match(spec)
    if not m:
        raise ValueError(f"invalid duration {spec!r}; use formats like '30m', '2h', '90s'")
    value = int(m.group(1))
    unit = (m.group(2) or "s").lower()
    if unit in ("s", "sec"):
        seconds = value
    elif unit in ("m", "min"):
        seconds = value * 60
    elif unit in ("h", "hr"):
        seconds = value * 3600
    else:
        raise ValueError(f"invalid duration unit in {spec!r}")
    if seconds <= 0:
        raise ValueError(
            f"invalid duration {spec!r}; must be positive"
        )
    if seconds > _MAX_EXTEND_SECONDS:
        raise ValueError(
            f"duration {spec!r} exceeds the {_MAX_EXTEND_SECONDS // 86400}-day "
            f"cap on a single extend; extend again later if you need more"
        )
    return seconds


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
    means no match.

    F-G-10: raises ``DockerDaemonUnavailable`` when docker stderr matches
    the daemon-down patterns — distinguishes "daemon not running" from
    "no session matching prefix". Previously both surfaced as an empty
    list and the user got a misleading "session not found" message when
    Docker Desktop was just paused. ``FileNotFoundError`` (docker CLI
    not on PATH) still returns [] so the session-log fallback path runs.
    """
    try:
        result = subprocess.run(
            ["docker", "ps", "--no-trunc",
             "--format", "{{.Label \"whizzard.session_id\"}}\t{{.ID}}"],
            capture_output=True, text=True, timeout=10,
        )
    except FileNotFoundError:
        # docker CLI not installed — fall back to session-log lookup;
        # ENDED/NOT_FOUND outcomes are still meaningful in that mode.
        return []
    except subprocess.TimeoutExpired as exc:
        raise DockerDaemonUnavailable(
            f"docker ps timed out after 10s ({exc}); is the docker daemon "
            "responsive?"
        ) from exc
    if result.returncode != 0:
        stderr = (result.stderr or "")
        if any(token in stderr for token in _DAEMON_DOWN_INDICATORS):
            raise DockerDaemonUnavailable(
                f"Docker daemon unreachable: {stderr.strip()}"
            )
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
    try:
        matches = _docker_label_lookup(prefix)
    except DockerDaemonUnavailable as exc:
        # F-G-10: daemon down — distinct from "no match". Surface a clear
        # error instead of falling through to the session-log path (which
        # would mis-blame the session as ENDED/NOT_FOUND).
        return SessionResolution(
            status=ResolutionStatus.DAEMON_UNAVAILABLE,
            detail=str(exc),
        )
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
    change that touches a field NOT in ``AGENT_ALLOWED_CHANGES``.
    Human-initiated calls bypass this check.

    F-G-06: the filter is an allowlist (default-deny). Previously it was
    a denylist (`AGENT_DENIED_CHANGES`), which meant any future
    ``Changes`` field — for example, a hypothetical ``change_profile``
    or ``disable_idle`` axis — would default-permit if someone forgot
    to add it to the deny set. With the allowlist, only ``add_mounts``,
    ``remove_mounts``, and ``extend_seconds`` are agent-requestable;
    every other current and future axis is denied by default. Approving
    a new axis for agents is an explicit edit to ``AGENT_ALLOWED_CHANGES``.

    Returns the first denied change found, or None if all changes are
    agent-permitted.
    """
    if changes.allow_broad_mount and "allow_broad_mount" not in AGENT_ALLOWED_CHANGES:
        return DeniedChange(field="allow_broad_mount")
    # When a new sensitive axis lands on Changes, add a check here AND
    # decide whether to include it in AGENT_ALLOWED_CHANGES. The dataclass
    # introspection below catches forgotten checks: any non-empty field
    # not in the allowlist also denies, so a missing per-field check is
    # a safety belt rather than a silent permit.
    allowed_fields = AGENT_ALLOWED_CHANGES
    sensitive_fields = {"allow_broad_mount"}  # explicitly checked above
    for field_name in changes.__dataclass_fields__:
        if field_name in allowed_fields or field_name in sensitive_fields:
            continue
        value = getattr(changes, field_name)
        # "Empty" = the field-default sentinel: empty tuple, None, False.
        if value in ((), None, False):
            continue
        return DeniedChange(
            field=field_name,
            reason=(
                f"field {field_name!r} is not in AGENT_ALLOWED_CHANGES; "
                "explicit allowlist entry required to permit it for agents"
            ),
        )
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
    the session_start event's timestamp. Returns 0.0 if unparseable.

    F-G-01: previously used `time.strptime(..., "%Y-%m-%dT%H:%M:%SZ")`,
    which broke when F-D-08 changed `session_log._iso()` to microsecond
    ISO with `+00:00` offset. A failed parse returned 0.0 and
    `adjust --extend` silently reset the duration cap to "full original
    limit + extension" instead of "remaining + N". Now uses
    `datetime.fromisoformat` which accepts both the old `Z` suffix
    (Python 3.11+) and the current `+00:00` offset.
    """
    raw = start_event.get("start_time") or start_event.get("ts")
    if not isinstance(raw, str):
        return 0.0
    # `fromisoformat` accepts trailing 'Z' in 3.11+. For 3.10 compat
    # (the project floor) substitute it with '+00:00' first.
    candidate = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return 0.0
    # Naive datetimes are unexpected but defensible — treat as UTC.
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    elapsed = datetime.now(UTC).timestamp() - parsed.timestamp()
    return max(0.0, elapsed)


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

    # F-G-02: the carried-forward `allow_broad_mount` signal must reflect
    # whether the original launch *actually invoked* the override — not
    # just whether the profile permits it. `start_event["allow_broad_mount"]`
    # is the profile *capability* and would re-grant the override on every
    # adjust even when the original user never typed the flag (silently
    # collapsing D-46's two-gate model). `overrides_used` is non-empty iff
    # at least one safety override actually fired at the original launch,
    # which is the load-bearing signal. The adjust user can re-affirm at
    # adjust time via `--allow-broad-mount` (the OR with `changes.allow_broad_mount`).
    original_used_override = bool(start_event.get("overrides_used"))
    return {
        "profile_name": start_event.get("profile", "default"),
        "mount_specs": mount_specs,
        "image": start_event.get("image_tag", ""),
        "allow_broad_mount": (
            changes.allow_broad_mount or original_used_override
        ),
        "harness": _harness_from_argv(start_event.get("argv", []) or []) or "generic",
        "preset_name": start_event.get("preset"),
        "duration_override_seconds": duration_override,
    }


def _log_adjustment(
    superseded_session_id: str,
    changes: Changes,
    new_session_id: str | None = None,
    *,
    event: str = "session_adjusted",
    detail: str = "",
) -> None:
    """Append an adjustment event to the session log linking the old session
    to the new. Lightweight: not a session_start/session_end pair, just a
    breadcrumb so audit consumers can follow the chain.

    F-G-11: uses ``append_event`` (the canonical audit-log writer), so
    the entry gets microsecond ISO timestamps (F-D-08) and the ``v: 1``
    schema-version stamp (F-D-10) — previously the manual write produced
    a Z-suffix mix and no version stamp.

    F-G-04 / F-G-05: ``event`` parameter lets the caller distinguish
    ``session_adjusted`` (success) from ``session_adjust_failed`` (stop
    succeeded but relaunch did not). The default preserves the original
    success path; failure callers pass the failed-variant.
    """
    payload = {
        "ts": datetime.now(UTC).isoformat(),
        "event": event,
        "superseded_session_id": superseded_session_id,
        "new_session_id": new_session_id,
        "origin": "whizzard",
        "changes": {
            "add_mounts": [{"name": m.name, "mode": m.mode} for m in changes.add_mounts],
            "remove_mounts": list(changes.remove_mounts),
            "extend_seconds": changes.extend_seconds,
            "allow_broad_mount": changes.allow_broad_mount,
        },
    }
    if detail:
        payload["detail"] = detail
    append_event(payload)


def _resolution_error_message(resolution: SessionResolution,
                              session_id_or_prefix: str) -> str:
    """Format a user-facing error for non-FOUND resolutions per D-163."""
    if resolution.status == ResolutionStatus.DAEMON_UNAVAILABLE:
        return (
            f"docker daemon unreachable while looking up session "
            f"{session_id_or_prefix!r}.\n"
            f"On macOS/Windows, start Docker Desktop. On Linux, check "
            f"`systemctl status docker`.\n"
            f"({resolution.detail})"
        )
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
    relauncher: Callable[[dict], int | tuple[int, str | None]] | None = None,
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

    # F-G-08: narrowing-only path skips the approver, but any no-op
    # warnings (e.g. "--remove-mount Y, Y wasn't attached") would
    # otherwise be silently dropped. Carry them in the result detail
    # so the CLI can surface them.
    warning_prefix = "\n".join(warnings) + "\n" if warnings else ""

    new_params = _apply_changes(start_event, effective_changes)

    stop_code, stop_detail = _stop_container(container_id)
    if stop_code != 0:
        return AdjustResult(
            exit_code=stop_code,
            detail=f"{warning_prefix}failed to stop container: {stop_detail}",
        )

    if relauncher is None:
        relauncher = _default_relauncher
    # F-G-12: any unexpected exception from the relauncher must not break
    # the AdjustResult contract; capture it and surface as an error result.
    try:
        relaunch_result = relauncher(new_params)
    except Exception as exc:
        # F-G-04/F-G-05: container already stopped; relaunch failed. Log
        # a distinct failed-variant audit event so the chain is visible.
        _log_adjustment(
            session_id, effective_changes,
            new_session_id=None,
            event="session_adjust_failed",
            detail=f"{type(exc).__name__}: {exc}",
        )
        return AdjustResult(
            exit_code=125,
            detail=(
                f"{warning_prefix}stop succeeded but relaunch raised "
                f"{type(exc).__name__}: {exc}. The original session is "
                "gone; start a new one with `oiq r`."
            ),
        )

    # Relauncher API: int exit code OR (exit_code, new_session_id) tuple.
    # _default_relauncher returns the tuple; older callers (tests) may
    # still pass int-returning fakes.
    if isinstance(relaunch_result, tuple):
        relaunch_code, new_session_id = relaunch_result
    else:
        relaunch_code = int(relaunch_result)
        new_session_id = None

    if relaunch_code == 0:
        _log_adjustment(
            session_id, effective_changes, new_session_id=new_session_id,
        )
        return AdjustResult(
            exit_code=0,
            detail=f"{warning_prefix}session adjusted",
            new_session_id=new_session_id,
        )

    # F-G-04/F-G-05: relaunch returned non-zero. Audit log records a
    # distinct event so the chain shows "adjusted (succeeded)" vs
    # "adjust_failed (session torched)" without ambiguity.
    _log_adjustment(
        session_id, effective_changes,
        new_session_id=new_session_id,
        event="session_adjust_failed",
        detail=f"relauncher returned exit code {relaunch_code}",
    )
    return AdjustResult(
        exit_code=relaunch_code,
        detail=(
            f"{warning_prefix}stop succeeded but relaunch returned exit "
            f"{relaunch_code}; the original session is gone."
        ),
    )


def _default_relauncher(new_params: dict) -> tuple[int, str | None]:
    """Default relaunch path: invoke the CLI's `_perform_launch`.

    Returns ``(exit_code, new_session_id)``. ``_perform_launch`` raises
    ``typer.Exit`` on every path; we translate to an int. The new
    session_id is not yet wired through ``_perform_launch``'s return
    path (it mints internally via `new_session_id()`), so this returns
    ``None`` for the id — the audit-log breadcrumb still links the
    superseded sid forward, just without the new sid filled in. Future
    work: have ``_perform_launch`` return its sid for cleaner audit.
    """
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
        return (int(e.exit_code) if e.exit_code is not None else 0, None)
    return (0, None)
