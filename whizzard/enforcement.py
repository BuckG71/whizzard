"""Stage 15 — duration + idle-timeout enforcement.

A contained session is time-bounded by its profile: `duration_seconds` (a
hard wall-clock cap) and `idle_timeout_seconds` (kill after N seconds with
no agent activity). Stage 5 logged these limits; Stage 15 enforces them.

`run_shell` launches the container with `subprocess.Popen` and hands the
process to `monitor_and_enforce`, which polls on an interval: it checks the
wall-clock deadline and samples the container's activity. On a limit hit it
runs the adapter's graceful wrap-up (or `docker stop` for adapters with no
native shutdown) and returns the reason — recorded as `expiry_reason` in the
session-end log.

Idle detection is hybrid (D-166): the primary signal is container resource
activity sampled from `docker stats` (CPU, network I/O, block I/O); a write
to the agent event file or the request channel also counts as activity and
resets the idle clock. Resource activity catches an abandoned or crashed
session; the event/request signal confirms a live agent even when its
resource use is momentarily low (a slow model call also still shows network
traffic, so that case is covered twice over).
"""

from __future__ import annotations

import contextlib
import re
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from whizzard.adapters.base import HarnessAdapter, WrapUpStatus
from whizzard.session_log import log_expiry_warning
from whizzard.snapshot import event_log_path, request_dir

# How often the monitor wakes to check limits. The clean-exit path is not
# bounded by this — `proc.wait(timeout=...)` returns the instant the
# container exits; the interval only governs limit-check granularity.
POLL_INTERVAL_SECONDS = 30.0

# docker-stats CPU% above this counts as "active" for idle detection.
_CPU_ACTIVE_THRESHOLD = 1.0

# Grace window handed to the adapter's wrap-up / `docker stop` on a limit hit.
_STOP_GRACE_SECONDS = 30

# Lead time for the pre-expiry warning before a duration cap.
_DEFAULT_WARNING_LEAD_SECONDS = 300


def _warning_lead(duration_limit: int) -> int:
    """Lead time for the pre-expiry warning — the default, or a fifth of a
    short cap, whichever is smaller (so a short session still gets a warning
    rather than none)."""
    return min(_DEFAULT_WARNING_LEAD_SECONDS, max(duration_limit // 5, 1))

ExpiryReason = str  # "clean" | "duration" | "idle"


# --- Activity sampling ------------------------------------------------------


@dataclass(frozen=True)
class ActivitySample:
    """One observation of a session's activity at a point in time."""
    cpu_percent: float
    net_bytes: int        # cumulative container network I/O (in + out)
    block_bytes: int      # cumulative container block I/O (read + write)
    event_mtime: float    # mtime of the agent event file (0.0 if absent)
    request_mtime: float  # newest mtime in the request channel (0.0 if absent)


_SIZE_UNITS: dict[str, float] = {
    "B": 1, "kB": 1e3, "MB": 1e6, "GB": 1e9, "TB": 1e12,
    "KiB": 1024, "MiB": 1024 ** 2, "GiB": 1024 ** 3, "TiB": 1024 ** 4,
}
_SIZE_RE = re.compile(r"([0-9.]+)\s*([A-Za-z]+)")


def _parse_size(token: str) -> int:
    """Parse a docker-stats size token ('1.45kB', '0B', '2MiB') into bytes.
    Unrecognized units fall back to a 1x multiplier; unparseable → 0."""
    m = _SIZE_RE.search(token.strip())
    if not m:
        return 0
    try:
        value = float(m.group(1))
    except ValueError:
        return 0
    return int(value * _SIZE_UNITS.get(m.group(2), 1))


def _parse_io(field: str) -> int:
    """Parse a docker-stats I/O field ('1.2kB / 800B') into total bytes."""
    return sum(_parse_size(part) for part in field.split("/"))


def _docker_stats(container_id: str) -> tuple[float, int, int] | None:
    """Return (cpu_percent, net_bytes, block_bytes) from `docker stats`.

    None if docker is unavailable, the call fails or times out, or the
    output is unparseable — the caller treats None as "no new information".
    """
    try:
        result = subprocess.run(
            ["docker", "stats", "--no-stream", "--format",
             "{{.CPUPerc}}\t{{.NetIO}}\t{{.BlockIO}}", container_id],
            capture_output=True, text=True, timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    line = result.stdout.strip()
    if not line or "\t" not in line:
        return None
    parts = line.split("\t")
    if len(parts) != 3:
        return None
    try:
        cpu = float(parts[0].rstrip("%").strip() or "0")
    except ValueError:
        return None
    return (cpu, _parse_io(parts[1]), _parse_io(parts[2]))


def _mtime(path: Path) -> float:
    """mtime of a file, or 0.0 if it doesn't exist / can't be stat'd."""
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _newest_mtime(directory: Path) -> float:
    """Newest mtime among *.json files in a directory, 0.0 if none/absent."""
    try:
        return max((f.stat().st_mtime for f in directory.glob("*.json")),
                   default=0.0)
    except OSError:
        return 0.0


def sample_activity(container_id: str, session_id: str) -> ActivitySample | None:
    """Sample a running session's activity. None if `docker stats` is
    unavailable — the caller leaves the idle clock untouched on a None."""
    stats = _docker_stats(container_id)
    if stats is None:
        return None
    cpu, net, block = stats
    return ActivitySample(
        cpu_percent=cpu,
        net_bytes=net,
        block_bytes=block,
        event_mtime=_mtime(event_log_path(session_id)),
        request_mtime=_newest_mtime(request_dir(session_id)),
    )


# --- Idle tracking ----------------------------------------------------------


class ActivityTracker:
    """Decides whether a session has gone idle by comparing successive
    samples. A sample counts as activity if CPU is above the threshold, the
    cumulative network/block I/O counters advanced, or the agent wrote to the
    event file / request channel since the last sample. Any of those resets
    the idle clock.
    """

    def __init__(self, start_time: float) -> None:
        self._last_active = start_time
        self._prev: ActivitySample | None = None

    def observe(self, sample: ActivitySample | None, now: float) -> None:
        """Fold one sample into the idle clock. A None sample carries no
        information and is ignored (clock neither advances nor resets)."""
        if sample is None:
            return
        if self._prev is None:
            # First sample — no baseline to diff against; treat as active so
            # a session is never declared idle on its very first observation.
            active = True
        elif sample.cpu_percent > _CPU_ACTIVE_THRESHOLD:
            active = True
        else:
            active = (
                sample.net_bytes != self._prev.net_bytes
                or sample.block_bytes != self._prev.block_bytes
                or sample.event_mtime > self._prev.event_mtime
                or sample.request_mtime > self._prev.request_mtime
            )
        if active:
            self._last_active = now
        self._prev = sample

    def idle_seconds(self, now: float) -> float:
        """Seconds since the last observed activity."""
        return now - self._last_active


# --- Container stop ---------------------------------------------------------


def _docker_stop(container_id: str, grace_seconds: int) -> None:
    """`docker stop` a container, swallowing docker-unavailable errors —
    used as the enforcement stop for adapters with no native wrap-up."""
    with contextlib.suppress(FileNotFoundError, subprocess.TimeoutExpired):
        subprocess.run(
            ["docker", "stop", "--time", str(grace_seconds), container_id],
            capture_output=True, text=True, timeout=grace_seconds + 10,
        )


def _enforce_stop(
    adapter: HarnessAdapter, container_id: str, grace_seconds: int
) -> None:
    """Stop a container that hit a limit. Prefer the adapter's native
    graceful wrap-up; if the adapter has none (NO_OP), `docker stop` it
    directly so the container actually terminates."""
    result = adapter.wrap_up(container_id, grace_seconds)
    if result.status == WrapUpStatus.NO_OP:
        _docker_stop(container_id, grace_seconds)


def _reap(proc: subprocess.Popen, grace_seconds: int) -> None:
    """Ensure the `docker run` client process exits after its container has
    been stopped. If it lingers past the grace window, kill it."""
    try:
        proc.wait(timeout=grace_seconds + 15)
    except subprocess.TimeoutExpired:
        proc.kill()
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=5)


# --- Monitor loop -----------------------------------------------------------


def monitor_and_enforce(
    proc: subprocess.Popen,
    *,
    container_id_reader: Callable[[], str | None],
    adapter: HarnessAdapter,
    session_id: str,
    start_time: float,
    duration_limit: int | None,
    idle_limit: int | None,
    grace_seconds: int = _STOP_GRACE_SECONDS,
    poll_interval: float | None = None,
    now: Callable[[], float] = time.time,
    sampler: Callable[[str, str], ActivitySample | None] = sample_activity,
    warner: Callable[[str, int], None] = log_expiry_warning,
) -> ExpiryReason:
    """Block until the container exits or a limit is hit.

    On a limit hit, gracefully stop the container and reap the `docker run`
    client. Returns the expiry reason: ``clean`` (container exited on its
    own), ``duration`` (hard cap), or ``idle`` (idle timeout).

    `container_id_reader` is called lazily — the container id isn't known
    until docker writes the cidfile, a moment after launch.

    `poll_interval` defaults to the module's `POLL_INTERVAL_SECONDS`,
    resolved at call time so it stays monkeypatchable (the integration smoke
    harness drops it to a few seconds).

    `warner` is called once, at a lead time before a duration cap, with
    `(session_id, seconds_remaining)` — the pre-expiry warning. It is not
    called for idle limits (an idle session has nobody watching).
    """
    if poll_interval is None:
        poll_interval = POLL_INTERVAL_SECONDS

    if duration_limit is None and idle_limit is None:
        # Nothing to enforce — just wait for the container, as pre-Stage-15.
        proc.wait()
        return "clean"

    tracker = ActivityTracker(start_time) if idle_limit is not None else None
    container_id: str | None = None
    reason: ExpiryReason = "clean"
    warned = False

    while True:
        try:
            proc.wait(timeout=poll_interval)
            break  # container exited on its own
        except subprocess.TimeoutExpired:
            pass

        t = now()
        if container_id is None:
            container_id = container_id_reader()

        if duration_limit is not None:
            elapsed = t - start_time
            if elapsed >= duration_limit:
                reason = "duration"
                break
            if not warned and elapsed >= duration_limit - _warning_lead(duration_limit):
                warner(session_id, int(duration_limit - elapsed))
                warned = True

        if tracker is not None and container_id is not None:
            tracker.observe(sampler(container_id, session_id), t)
            if idle_limit is not None and tracker.idle_seconds(t) >= idle_limit:
                reason = "idle"
                break

    if reason != "clean":
        if container_id is None:
            container_id = container_id_reader()
        if container_id is not None:
            _enforce_stop(adapter, container_id, grace_seconds)
        _reap(proc, grace_seconds)

    return reason
