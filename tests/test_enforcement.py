"""Stage 15 — duration + idle-timeout enforcement tests.

Pure pieces (size parsing, the activity tracker) are tested directly;
`monitor_and_enforce` is driven with a fake process, clock, and sampler so
no real Docker is involved. Real stop+relaunch is the integration tier.
"""

from __future__ import annotations

import subprocess

import pytest

import whizzard.enforcement as enf
from whizzard.adapters.base import WrapUpResult, WrapUpStatus
from whizzard.enforcement import (
    ActivitySample,
    ActivityTracker,
    _parse_io,
    _parse_size,
    monitor_and_enforce,
    sample_activity,
)

# --- size / IO parsing ------------------------------------------------------


@pytest.mark.parametrize("token,expected", [
    ("0B", 0),
    ("512B", 512),
    ("1.45kB", 1450),
    ("2MB", 2_000_000),
    ("1KiB", 1024),
    ("garbage", 0),
    ("", 0),
])
def test_parse_size(token, expected):
    assert _parse_size(token) == expected


def test_parse_io_sums_both_sides():
    assert _parse_io("1.2kB / 800B") == 2000
    assert _parse_io("0B / 0B") == 0


# --- _docker_stats ----------------------------------------------------------


def _completed(stdout="", returncode=0):
    return subprocess.CompletedProcess(args=[], returncode=returncode,
                                       stdout=stdout, stderr="")


def test_docker_stats_parses_output(monkeypatch):
    monkeypatch.setattr(
        enf.subprocess, "run",
        lambda *a, **k: _completed("12.5%\t1.2kB / 0B\t4kB / 0B"),
    )
    assert enf._docker_stats("cid") == (12.5, 1200, 4000)


def test_docker_stats_returns_none_on_nonzero_exit(monkeypatch):
    monkeypatch.setattr(enf.subprocess, "run",
                        lambda *a, **k: _completed("", returncode=1))
    assert enf._docker_stats("cid") is None


def test_docker_stats_returns_none_when_docker_missing(monkeypatch):
    def _raise(*a, **k):
        raise FileNotFoundError

    monkeypatch.setattr(enf.subprocess, "run", _raise)
    assert enf._docker_stats("cid") is None


# --- sample_activity --------------------------------------------------------


def test_sample_activity_none_when_stats_unavailable(monkeypatch):
    monkeypatch.setattr(enf, "_docker_stats", lambda cid: None)
    assert sample_activity("cid", "sess") is None


def test_sample_activity_includes_resource_and_file_signals(monkeypatch, tmp_path):
    monkeypatch.setattr(enf, "_docker_stats", lambda cid: (5.0, 100, 200))
    monkeypatch.setattr(enf, "event_log_path", lambda sid: tmp_path / "absent.jsonl")
    monkeypatch.setattr(enf, "request_dir", lambda sid: tmp_path / "absent-dir")
    s = sample_activity("cid", "sess")
    assert s is not None
    assert s.cpu_percent == 5.0
    assert s.net_bytes == 100
    assert s.event_mtime == 0.0  # absent file → 0.0


# --- ActivityTracker --------------------------------------------------------


def _sample(cpu=0.0, net=0, block=0, ev=0.0, req=0.0):
    return ActivitySample(cpu, net, block, ev, req)


def test_tracker_first_sample_counts_as_active():
    t = ActivityTracker(start_time=1000.0)
    t.observe(_sample(cpu=0.0), now=1100.0)
    assert t.idle_seconds(1100.0) == 0.0


def test_tracker_high_cpu_is_active():
    t = ActivityTracker(1000.0)
    t.observe(_sample(cpu=0.0, net=5), 1010.0)   # baseline
    t.observe(_sample(cpu=50.0, net=5), 1070.0)  # busy CPU
    assert t.idle_seconds(1070.0) == 0.0


def test_tracker_quiet_samples_accumulate_idle():
    t = ActivityTracker(1000.0)
    quiet = _sample(cpu=0.0, net=500, block=500)
    t.observe(quiet, 1010.0)   # first sample → active, last_active=1010
    t.observe(quiet, 1070.0)   # identical → idle
    assert t.idle_seconds(1070.0) == 60.0


def test_tracker_io_change_resets_idle():
    t = ActivityTracker(1000.0)
    t.observe(_sample(net=100), 1010.0)
    t.observe(_sample(net=100), 1070.0)   # quiet
    t.observe(_sample(net=999), 1130.0)   # net counter advanced
    assert t.idle_seconds(1130.0) == 0.0


def test_tracker_event_write_resets_idle():
    t = ActivityTracker(1000.0)
    t.observe(_sample(ev=1.0), 1010.0)
    t.observe(_sample(ev=1.0), 1070.0)    # quiet
    t.observe(_sample(ev=2.0), 1130.0)    # agent event file written
    assert t.idle_seconds(1130.0) == 0.0


def test_tracker_none_sample_is_ignored():
    t = ActivityTracker(1000.0)
    t.observe(_sample(net=1), 1010.0)
    t.observe(None, 1200.0)               # no information
    assert t.idle_seconds(1200.0) == 190.0


# --- monitor_and_enforce ----------------------------------------------------


class FakeProc:
    """subprocess.Popen stand-in. Raises TimeoutExpired on `wait(timeout)`
    until call number `exit_on_call`, then 'exits' with `returncode`. A
    `wait()` with no timeout returns immediately."""

    def __init__(self, exit_on_call: int | None = None, returncode: int = 0):
        self._calls = 0
        self._exit_on = exit_on_call
        self._final_rc = returncode
        self.returncode: int | None = None
        self.killed = False

    def wait(self, timeout=None):
        self._calls += 1
        if timeout is None or (
            self._exit_on is not None and self._calls >= self._exit_on
        ):
            self.returncode = self._final_rc
            return self._final_rc
        raise subprocess.TimeoutExpired(cmd="docker", timeout=timeout)

    def kill(self):
        self.killed = True
        self.returncode = -9


class FakeClock:
    """Monotonic clock — each call advances by `step`."""

    def __init__(self, start: float, step: float):
        self.t = start
        self.step = step

    def __call__(self) -> float:
        self.t += self.step
        return self.t


class _OkAdapter:
    name = "fake"

    def wrap_up(self, container_id, grace_seconds):
        return WrapUpResult(status=WrapUpStatus.SUCCESS, detail="stopped")


class _NoOpAdapter:
    name = "generic"

    def wrap_up(self, container_id, grace_seconds):
        return WrapUpResult(status=WrapUpStatus.NO_OP, detail="no-op")


def test_monitor_no_limits_just_waits():
    proc = FakeProc()
    reason = monitor_and_enforce(
        proc, container_id_reader=lambda: "cid", adapter=_OkAdapter(),
        session_id="s", start_time=1000.0,
        duration_limit=None, idle_limit=None,
    )
    assert reason == "clean"
    assert proc.returncode == 0


def test_monitor_clean_exit_before_duration_limit():
    proc = FakeProc(exit_on_call=2, returncode=0)
    reason = monitor_and_enforce(
        proc, container_id_reader=lambda: "cid", adapter=_OkAdapter(),
        session_id="s", start_time=1000.0,
        duration_limit=10_000, idle_limit=None,
        poll_interval=0.01, now=FakeClock(1000.0, 5.0),
    )
    assert reason == "clean"


def test_monitor_duration_expiry():
    proc = FakeProc(exit_on_call=3, returncode=137)
    reason = monitor_and_enforce(
        proc, container_id_reader=lambda: "cid", adapter=_OkAdapter(),
        session_id="s", start_time=1000.0,
        duration_limit=100, idle_limit=None,
        poll_interval=0.01, now=FakeClock(1000.0, 60.0),
    )
    assert reason == "duration"


def test_monitor_idle_expiry():
    proc = FakeProc(exit_on_call=4, returncode=137)
    quiet = ActivitySample(cpu_percent=0.0, net_bytes=10, block_bytes=10,
                           event_mtime=0.0, request_mtime=0.0)
    reason = monitor_and_enforce(
        proc, container_id_reader=lambda: "cid", adapter=_OkAdapter(),
        session_id="s", start_time=1000.0,
        duration_limit=None, idle_limit=100,
        poll_interval=0.01, now=FakeClock(1000.0, 60.0),
        sampler=lambda cid, sid: quiet,
    )
    assert reason == "idle"


def test_monitor_noop_adapter_falls_back_to_docker_stop(monkeypatch):
    stopped: list[str] = []
    monkeypatch.setattr(enf, "_docker_stop",
                        lambda cid, grace: stopped.append(cid))
    proc = FakeProc(exit_on_call=2, returncode=137)
    monitor_and_enforce(
        proc, container_id_reader=lambda: "cid-noop", adapter=_NoOpAdapter(),
        session_id="s", start_time=1000.0,
        duration_limit=50, idle_limit=None,
        poll_interval=0.01, now=FakeClock(1000.0, 60.0),
    )
    assert stopped == ["cid-noop"]


def test_monitor_idle_not_triggered_by_active_session():
    # CPU stays busy every poll → never idle; container exits cleanly.
    proc = FakeProc(exit_on_call=4, returncode=0)
    busy = ActivitySample(cpu_percent=80.0, net_bytes=0, block_bytes=0,
                          event_mtime=0.0, request_mtime=0.0)
    reason = monitor_and_enforce(
        proc, container_id_reader=lambda: "cid", adapter=_OkAdapter(),
        session_id="s", start_time=1000.0,
        duration_limit=None, idle_limit=100,
        poll_interval=0.01, now=FakeClock(1000.0, 60.0),
        sampler=lambda cid, sid: busy,
    )
    assert reason == "clean"
