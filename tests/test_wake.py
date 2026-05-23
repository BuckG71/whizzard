"""Unit tests for whizzard.wake (Stage 15.5 / D-168 + D-169)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from whizzard import wake


def _write_log(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        for ev in events:
            fh.write(json.dumps(ev) + "\n")


def _start(sid: str, *, profile: str = "default", mounts: list[dict] | None = None,
           allow_broad_mount: bool = False, preset: str | None = None,
           ts: str = "2026-05-22T10:00:00Z", argv: list[str] | None = None) -> dict:
    ev = {
        "event": "session_start",
        "session_id": sid,
        "profile": profile,
        "image_tag": "whizzard-base:latest",
        "image_id": "sha256:abc",
        "mounts": mounts or [],
        "argv": argv or [],
        "allow_broad_mount": allow_broad_mount,
        "duration_limit_seconds": None,
        "network_enabled": False,
        "start_time": ts,
        "ts": ts,
        "overrides_used": [],
    }
    if preset is not None:
        ev["preset"] = preset
    return ev


def _end(sid: str, *, reason: str = "idle", ts: str = "2026-05-22T11:00:00Z") -> dict:
    return {
        "event": "session_end",
        "session_id": sid,
        "container_id": "cid-" + sid[:6],
        "exit_status": 137,
        "duration_seconds": 3600.0,
        "end_time": ts,
        "ts": ts,
        "expiry_reason": reason,
    }


def _woken(superseded: str, new_sid: str = "new-sid",
           ts: str = "2026-05-22T12:00:00Z") -> dict:
    return {
        "event": "session_woken",
        "superseded_session_id": superseded,
        "new_session_id": new_sid,
        "ts": ts,
    }


# --- bare wake -------------------------------------------------------------


def test_bare_wake_picks_most_recent_idle_ended():
    events = [
        _start("aaa"), _end("aaa", reason="idle", ts="2026-05-22T11:00:00Z"),
        _start("bbb"), _end("bbb", reason="idle", ts="2026-05-22T12:00:00Z"),
    ]
    res = wake.find_wakeable(None, events=events, docker_check=False)
    assert res.status == wake.WakeStatus.OK
    assert res.candidate.session_id == "bbb"


def test_bare_wake_skips_already_woken():
    events = [
        _start("aaa"), _end("aaa", reason="idle"),
        _start("bbb"), _end("bbb", reason="idle", ts="2026-05-22T12:00:00Z"),
        _woken("bbb", "ccc"),  # bbb was already woken; should skip it
    ]
    res = wake.find_wakeable(None, events=events, docker_check=False)
    assert res.status == wake.WakeStatus.OK
    assert res.candidate.session_id == "aaa"


def test_bare_wake_skips_non_idle_endings():
    events = [
        _start("aaa"), _end("aaa", reason="idle", ts="2026-05-22T11:00:00Z"),
        _start("bbb"), _end("bbb", reason="duration", ts="2026-05-22T12:00:00Z"),
    ]
    res = wake.find_wakeable(None, events=events, docker_check=False)
    assert res.status == wake.WakeStatus.OK
    assert res.candidate.session_id == "aaa"


def test_bare_wake_no_idle_sessions():
    events = [_start("aaa"), _end("aaa", reason="duration")]
    res = wake.find_wakeable(None, events=events, docker_check=False)
    assert res.status == wake.WakeStatus.NO_ELIGIBLE
    assert "No idle-ended session" in res.detail


def test_bare_wake_empty_log():
    res = wake.find_wakeable(None, events=[], docker_check=False)
    assert res.status == wake.WakeStatus.NO_ELIGIBLE


# --- explicit sid / prefix wake -------------------------------------------


def test_explicit_sid_exact_match():
    events = [_start("abc12345"), _end("abc12345", reason="idle")]
    res = wake.find_wakeable("abc12345", events=events, docker_check=False)
    assert res.status == wake.WakeStatus.OK
    assert res.candidate.session_id == "abc12345"


def test_explicit_sid_prefix_match():
    events = [_start("abc12345"), _end("abc12345", reason="idle")]
    res = wake.find_wakeable("abc12", events=events, docker_check=False)
    assert res.status == wake.WakeStatus.OK
    assert res.candidate.session_id == "abc12345"


def test_explicit_sid_ambiguous_prefix():
    events = [
        _start("abc11111"), _end("abc11111", reason="idle"),
        _start("abc22222"), _end("abc22222", reason="idle"),
    ]
    res = wake.find_wakeable("abc", events=events, docker_check=False)
    assert res.status == wake.WakeStatus.AMBIGUOUS_PREFIX
    assert set(res.candidates) == {"abc11111", "abc22222"}


def test_explicit_sid_not_found():
    events = [_start("abc"), _end("abc", reason="idle")]
    res = wake.find_wakeable("xyz", events=events, docker_check=False)
    assert res.status == wake.WakeStatus.NOT_FOUND


def test_explicit_sid_empty_prefix():
    res = wake.find_wakeable("   ", events=[], docker_check=False)
    assert res.status == wake.WakeStatus.EMPTY_PREFIX


def test_explicit_sid_not_idle_errors_with_reason():
    events = [_start("abc"), _end("abc", reason="duration")]
    res = wake.find_wakeable("abc", events=events, docker_check=False)
    assert res.status == wake.WakeStatus.NOT_IDLE
    assert "duration" in res.detail


def test_explicit_sid_no_end_recorded():
    events = [_start("abc")]
    res = wake.find_wakeable("abc", events=events, docker_check=False)
    assert res.status == wake.WakeStatus.NOT_ENDED


def test_explicit_sid_already_woken_errors_distinctly():
    events = [
        _start("abc"), _end("abc", reason="idle"),
        _woken("abc", "new"),
    ]
    res = wake.find_wakeable("abc", events=events, docker_check=False)
    assert res.status == wake.WakeStatus.ALREADY_WOKEN


def test_active_session_check(monkeypatch):
    """When docker_check=True and the sid is active, returns STILL_ACTIVE."""
    events = [_start("abc"), _end("abc", reason="idle")]
    monkeypatch.setattr(
        wake, "_docker_label_lookup",
        lambda prefix: [("abc", "container-1")],
    )
    res = wake.find_wakeable("abc", events=events, docker_check=True)
    assert res.status == wake.WakeStatus.STILL_ACTIVE


# --- mount-existence + reconstruction -------------------------------------


def test_check_mounts_exist_returns_missing(tmp_path):
    real = tmp_path / "exists"
    real.mkdir()
    fake = tmp_path / "nope"
    mounts = [
        {"name": "a", "mode": "rw", "host_path": str(real), "container_path": "/work/a"},
        {"name": "b", "mode": "ro", "host_path": str(fake), "container_path": "/work/b"},
    ]
    missing = wake.check_mounts_exist(mounts)
    assert missing == [str(fake)]


def test_check_mounts_exist_skips_malformed():
    """A mount entry without host_path is skipped silently (defensive)."""
    mounts = [{"name": "x", "mode": "ro"}, "not-a-dict"]
    assert wake.check_mounts_exist(mounts) == []  # type: ignore[arg-type]


def test_missing_mount_names_returns_names_not_paths(tmp_path):
    real = tmp_path / "exists"
    real.mkdir()
    fake = tmp_path / "nope"
    start = _start("abc", mounts=[
        {"name": "good", "mode": "rw", "host_path": str(real)},
        {"name": "bad", "mode": "ro", "host_path": str(fake)},
    ])
    names = wake.missing_mount_names(start)
    assert names == ["bad"]


def test_reconstruct_carries_all_params(tmp_path):
    start = _start(
        "abc",
        profile="build",
        allow_broad_mount=True,
        preset="alpha",
        mounts=[
            {"name": "a", "mode": "rw", "host_path": str(tmp_path)},
            {"name": "b", "mode": "ro", "host_path": str(tmp_path)},
        ],
        argv=["--label", "whizzard.harness=hermes"],
    )
    params = wake.reconstruct_launch_params(start)
    assert params["profile_name"] == "build"
    assert params["allow_broad_mount"] is True
    assert params["preset_name"] == "alpha"
    assert params["harness"] == "hermes"
    assert sorted(params["mount_specs"]) == ["a:rw", "b:ro"]


def test_reconstruct_drops_named_mounts():
    start = _start("abc", mounts=[
        {"name": "a", "mode": "rw", "host_path": "/x"},
        {"name": "b", "mode": "ro", "host_path": "/y"},
    ])
    params = wake.reconstruct_launch_params(start, drop_mount_names={"b"})
    assert params["mount_specs"] == ["a:rw"]


def test_reconstruct_defaults_harness_to_generic():
    start = _start("abc")  # no harness label in argv
    params = wake.reconstruct_launch_params(start)
    assert params["harness"] == "generic"


def test_reconstruct_preserves_allow_broad_mount_false():
    start = _start("abc", allow_broad_mount=False)
    params = wake.reconstruct_launch_params(start)
    assert params["allow_broad_mount"] is False


# --- log_wake_event audit -------------------------------------------------


def test_log_wake_event_appends_correctly(tmp_path):
    log_path = tmp_path / "sessions.jsonl"
    wake.log_wake_event(
        superseded_session_id="abc",
        new_session_id="def",
        dropped_mounts=["stale-mount"],
        path=log_path,
    )
    lines = log_path.read_text().strip().splitlines()
    assert len(lines) == 1
    ev = json.loads(lines[0])
    assert ev["event"] == "session_woken"
    assert ev["superseded_session_id"] == "abc"
    assert ev["new_session_id"] == "def"
    assert ev["dropped_mounts"] == ["stale-mount"]
    assert "ts" in ev


# --- end-to-end: read from file, find, reconstruct -------------------------


def test_round_trip_from_log_file(tmp_path):
    log_path = tmp_path / "sessions.jsonl"
    events = [
        _start("aaa11111", profile="build"),
        _end("aaa11111", reason="idle"),
    ]
    _write_log(log_path, events)
    loaded = wake._read_events(path=log_path)
    res = wake.find_wakeable("aaa", events=loaded, docker_check=False)
    assert res.status == wake.WakeStatus.OK
    params = wake.reconstruct_launch_params(res.candidate.start_event)
    assert params["profile_name"] == "build"


def test_resume_after_wake_does_not_double_resume(tmp_path):
    """After waking session A, bare wake should not match A again."""
    log_path = tmp_path / "sessions.jsonl"
    events = [
        _start("aaa", profile="default"),
        _end("aaa", reason="idle", ts="2026-05-22T11:00:00Z"),
    ]
    _write_log(log_path, events)
    # Simulate the wake action: log the session_woken event.
    wake.log_wake_event(
        superseded_session_id="aaa", new_session_id="bbb", path=log_path,
    )
    loaded = wake._read_events(path=log_path)
    res = wake.find_wakeable(None, events=loaded, docker_check=False)
    assert res.status == wake.WakeStatus.NO_ELIGIBLE


@pytest.mark.parametrize("reason", ["clean", "duration"])
def test_non_idle_endings_never_eligible(reason):
    events = [_start("abc"), _end("abc", reason=reason)]
    res = wake.find_wakeable(None, events=events, docker_check=False)
    assert res.status == wake.WakeStatus.NO_ELIGIBLE
