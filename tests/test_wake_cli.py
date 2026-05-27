"""CLI tests for `whiz wake` (Stage 15.5)."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from whizzard.cli import app


def _write_log(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        for ev in events:
            fh.write(json.dumps(ev) + "\n")


def _start(sid: str, mounts: list[dict] | None = None,
           profile: str = "default", preset: str | None = None,
           ts: str = "2026-05-22T10:00:00Z") -> dict:
    ev = {
        "event": "session_start",
        "session_id": sid,
        "profile": profile,
        "image_tag": "whizzard-base:latest",
        "mounts": mounts or [],
        "argv": [],
        "allow_broad_mount": False,
        "duration_limit_seconds": None,
        "start_time": ts,
        "ts": ts,
    }
    if preset is not None:
        ev["preset"] = preset
    return ev


def _end(sid: str, reason: str = "idle",
         ts: str = "2026-05-22T11:00:00Z") -> dict:
    return {
        "event": "session_end",
        "session_id": sid,
        "container_id": "cid",
        "exit_status": 137,
        "duration_seconds": 3600.0,
        "end_time": ts,
        "ts": ts,
        "expiry_reason": reason,
    }


def _wide_rich_console(stderr: bool = False):
    """Replacement for typer's internal help-console factory that pins width.

    Typer's `rich_format_help` builds its output via `_get_rich_console()`,
    whose default lets Rich auto-detect terminal width. On CI runners and
    in pytest's captured-stdout context, auto-detection collapses to
    something narrow enough to elide option names from the rendered
    output. The cleanest cross-version fix is to swap the factory itself
    for one that always returns a wide, force-terminal Console.
    """
    import sys

    from rich.console import Console
    return Console(width=200, force_terminal=True, file=sys.stderr if stderr else None)


def test_wake_help_renders(monkeypatch):
    # End-to-end help-render check: invoke `whiz wake --help` and assert
    # the user-visible output contains the key flag and the command
    # description. See _wide_rich_console for why we replace the factory.
    import typer.rich_utils
    monkeypatch.setattr(typer.rich_utils, "_get_rich_console", _wide_rich_console)

    runner = CliRunner()
    res = runner.invoke(app, ["wake", "--help"])
    assert res.exit_code == 0
    flat = res.stdout.replace("\n", "").replace(" ", "")
    assert "Wake(hot-restart)" in flat
    assert "allow-missing-mounts" in flat


def test_wake_bare_no_eligible_session_shows_launch_hint(tmp_path, monkeypatch):
    log = tmp_path / "sessions.jsonl"
    _write_log(log, [])  # empty log
    monkeypatch.setattr("whizzard.wake.SESSIONS_LOG", log)
    runner = CliRunner()
    res = runner.invoke(app, ["wake"])
    assert res.exit_code == 2
    assert "No idle-ended session" in res.stdout
    assert "whiz launch" in res.stdout


def test_wake_unknown_sid(tmp_path, monkeypatch):
    log = tmp_path / "sessions.jsonl"
    _write_log(log, [_start("aaa"), _end("aaa", reason="idle")])
    monkeypatch.setattr("whizzard.wake.SESSIONS_LOG", log)
    runner = CliRunner()
    res = runner.invoke(app, ["wake", "xyz"])
    assert res.exit_code == 2
    assert "no session matching" in res.stdout
    assert "whiz launch" in res.stdout


def test_wake_non_idle_ending_blocked_with_reason(tmp_path, monkeypatch):
    log = tmp_path / "sessions.jsonl"
    _write_log(log, [_start("aaa11111"), _end("aaa11111", reason="duration")])
    monkeypatch.setattr("whizzard.wake.SESSIONS_LOG", log)
    monkeypatch.setattr("whizzard.wake._docker_label_lookup", lambda p: [])
    runner = CliRunner()
    res = runner.invoke(app, ["wake", "aaa11111"])
    assert res.exit_code == 2
    assert "duration" in res.stdout
    assert "not idle" in res.stdout
    assert "whiz launch" in res.stdout


def test_wake_active_session_blocked_with_adjust_hint(tmp_path, monkeypatch):
    log = tmp_path / "sessions.jsonl"
    _write_log(log, [_start("aaa11111"), _end("aaa11111", reason="idle")])
    monkeypatch.setattr("whizzard.wake.SESSIONS_LOG", log)
    monkeypatch.setattr(
        "whizzard.wake._docker_label_lookup",
        lambda p: [("aaa11111", "container-1")],
    )
    runner = CliRunner()
    res = runner.invoke(app, ["wake", "aaa11111"])
    assert res.exit_code == 2
    assert "already running" in res.stdout
    assert "whiz adjust" in res.stdout


def test_wake_ambiguous_prefix(tmp_path, monkeypatch):
    log = tmp_path / "sessions.jsonl"
    events = [
        _start("abc111"), _end("abc111", reason="idle"),
        _start("abc222"), _end("abc222", reason="idle"),
    ]
    _write_log(log, events)
    monkeypatch.setattr("whizzard.wake.SESSIONS_LOG", log)
    monkeypatch.setattr("whizzard.wake._docker_label_lookup", lambda p: [])
    runner = CliRunner()
    res = runner.invoke(app, ["wake", "abc"])
    assert res.exit_code == 2
    assert "ambiguous" in res.stdout.lower()
    assert "longer prefix" in res.stdout


def test_wake_dry_run_prints_resolved_params(tmp_path, monkeypatch):
    log = tmp_path / "sessions.jsonl"
    real = tmp_path / "mount-dir"
    real.mkdir()
    events = [
        _start("aaa11111", profile="build", preset="alpha",
               mounts=[{"name": "m1", "mode": "rw", "host_path": str(real)}]),
        _end("aaa11111", reason="idle"),
    ]
    _write_log(log, events)
    monkeypatch.setattr("whizzard.wake.SESSIONS_LOG", log)
    monkeypatch.setattr("whizzard.wake._docker_label_lookup", lambda p: [])
    runner = CliRunner()
    res = runner.invoke(app, ["wake", "aaa11111", "--dry-run"])
    assert res.exit_code == 0
    assert "Would wake" in res.stdout
    assert "build" in res.stdout
    assert "alpha" in res.stdout
    assert "m1:rw" in res.stdout


def test_wake_missing_mount_blocked_by_default(tmp_path, monkeypatch):
    log = tmp_path / "sessions.jsonl"
    missing = tmp_path / "gone"  # does not exist
    events = [
        _start("aaa11111",
               mounts=[{"name": "m1", "mode": "rw", "host_path": str(missing)}]),
        _end("aaa11111", reason="idle"),
    ]
    _write_log(log, events)
    monkeypatch.setattr("whizzard.wake.SESSIONS_LOG", log)
    monkeypatch.setattr("whizzard.wake._docker_label_lookup", lambda p: [])
    runner = CliRunner()
    res = runner.invoke(app, ["wake", "aaa11111"])
    assert res.exit_code == 2
    assert "mount" in res.stdout.lower()
    assert "missing" in res.stdout.lower()
    assert "--allow-missing-mounts" in res.stdout


def test_wake_missing_mount_with_override_proceeds(tmp_path, monkeypatch):
    log = tmp_path / "sessions.jsonl"
    real = tmp_path / "good"
    real.mkdir()
    missing = tmp_path / "gone"
    events = [
        _start("aaa11111", mounts=[
            {"name": "good", "mode": "rw", "host_path": str(real)},
            {"name": "bad", "mode": "ro", "host_path": str(missing)},
        ]),
        _end("aaa11111", reason="idle"),
    ]
    _write_log(log, events)
    monkeypatch.setattr("whizzard.wake.SESSIONS_LOG", log)
    monkeypatch.setattr("whizzard.wake._docker_label_lookup", lambda p: [])
    runner = CliRunner()
    res = runner.invoke(app, [
        "wake", "aaa11111", "--allow-missing-mounts", "--dry-run",
    ])
    assert res.exit_code == 0, res.stdout
    assert "Dropping" in res.stdout
    assert "bad" in res.stdout
    # the kept mount should appear in the relaunch param set
    assert "good:rw" in res.stdout
    # the dropped one should not appear in the mount_specs line
    assert "bad:ro" not in res.stdout


def test_wake_bare_picks_most_recent_idle_ended_and_relaunches(tmp_path, monkeypatch):
    """Happy path: bare wake on a clean log resolves correctly and calls _perform_launch."""
    log = tmp_path / "sessions.jsonl"
    real = tmp_path / "mount-dir"
    real.mkdir()
    events = [
        _start("aaa", profile="default",
               mounts=[{"name": "m1", "mode": "rw", "host_path": str(real)}]),
        _end("aaa", reason="idle", ts="2026-05-22T11:00:00Z"),
        _start("bbb", profile="build",
               mounts=[{"name": "m1", "mode": "ro", "host_path": str(real)}]),
        _end("bbb", reason="idle", ts="2026-05-22T12:00:00Z"),
    ]
    _write_log(log, events)
    monkeypatch.setattr("whizzard.wake.SESSIONS_LOG", log)
    monkeypatch.setattr("whizzard.session_log.SESSIONS_LOG", log)
    monkeypatch.setattr("whizzard.wake._docker_label_lookup", lambda p: [])
    # Don't actually run docker; capture the relaunch call.
    # A3: fake_launch must write session_start to the audit log so the
    # post-relaunch audit-log check (find_session_start_after_offset)
    # sees the new sid and classifies as a successful wake. The real
    # _perform_launch does this inside run_shell.
    captured: dict = {}
    def fake_launch(**kw):
        captured.update(kw)
        from whizzard.session_log import log_session_start
        log_session_start(
            session_id="new-from-fake-launch",
            profile_name=kw["profile_name"],
            network_enabled=False,
            duration_limit_seconds=None,
            allow_broad_mount=kw["allow_broad_mount"],
            image_tag=kw["image"],
            image_id=None,
            mounts=[],
            argv=[],
            start_time=2_000_000_000.0,
        )
    monkeypatch.setattr("whizzard.cli.wake._perform_launch", fake_launch)
    # Also stub log_wake_event so we don't write to the test log file
    # (cleaner test isolation).
    woken_calls: list[dict] = []
    def fake_log(**kw):
        woken_calls.append(kw)
    monkeypatch.setattr("whizzard.cli.wake.log_wake_event", fake_log)

    runner = CliRunner()
    res = runner.invoke(app, ["wake"])
    assert res.exit_code == 0, res.stdout
    # bbb is the most-recent idle-ended session
    assert woken_calls[0]["superseded_session_id"] == "bbb"
    # A3: new sid is now recovered from the audit log
    assert woken_calls[0]["new_session_id"] == "new-from-fake-launch"
    # relaunched with bbb's params
    assert captured["profile_name"] == "build"
    assert captured["mount_specs"] == ["m1:ro"]


def test_wake_preserves_allow_broad_mount(tmp_path, monkeypatch):
    """D-168: a session launched with --allow-broad-mount stays broad on wake.

    F-G-02: the signal is `overrides_used` (whether the original launch
    actually invoked the override), NOT `allow_broad_mount` capability.
    Tests must seed `overrides_used` to simulate the original opt-in.
    """
    log = tmp_path / "sessions.jsonl"
    real = tmp_path / "mount-dir"
    real.mkdir()
    start = _start("aaa11111", mounts=[
        {"name": "m1", "mode": "rw", "host_path": str(real)},
    ])
    start["allow_broad_mount"] = True
    # F-G-02: original launch actually invoked the override.
    start["overrides_used"] = [
        {"path": str(real), "reason": "user invoked --allow-broad-mount"}
    ]
    events = [start, _end("aaa11111", reason="idle")]
    _write_log(log, events)
    monkeypatch.setattr("whizzard.wake.SESSIONS_LOG", log)
    monkeypatch.setattr("whizzard.session_log.SESSIONS_LOG", log)
    monkeypatch.setattr("whizzard.wake._docker_label_lookup", lambda p: [])

    # A3: fake_launch must write session_start to mirror real
    # _perform_launch behavior — the post-relaunch audit-log check
    # uses it to classify success.
    captured: dict = {}
    def fake_launch(**kw):
        captured.update(kw)
        from whizzard.session_log import log_session_start
        log_session_start(
            session_id="woken-broad-mount",
            profile_name=kw["profile_name"],
            network_enabled=False,
            duration_limit_seconds=None,
            allow_broad_mount=kw["allow_broad_mount"],
            image_tag=kw["image"],
            image_id=None,
            mounts=[],
            argv=[],
            start_time=2_000_000_000.0,
        )
    monkeypatch.setattr("whizzard.cli.wake._perform_launch", fake_launch)
    monkeypatch.setattr("whizzard.cli.wake.log_wake_event", lambda **kw: None)

    runner = CliRunner()
    res = runner.invoke(app, ["wake", "aaa11111"])
    assert res.exit_code == 0, res.stdout
    assert captured["allow_broad_mount"] is True


def test_wake_logs_audit_event_on_relaunch(tmp_path, monkeypatch):
    log = tmp_path / "sessions.jsonl"
    real = tmp_path / "mount-dir"
    real.mkdir()
    events = [
        _start("aaa11111", mounts=[
            {"name": "m1", "mode": "rw", "host_path": str(real)},
        ]),
        _end("aaa11111", reason="idle"),
    ]
    _write_log(log, events)
    # F-G-11: log_wake_event now writes through session_log.append_event,
    # which reads SESSIONS_LOG from the session_log module. Patch that
    # module's constant alongside the wake-module one.
    monkeypatch.setattr("whizzard.wake.SESSIONS_LOG", log)
    monkeypatch.setattr("whizzard.session_log.SESSIONS_LOG", log)
    monkeypatch.setattr("whizzard.wake._docker_label_lookup", lambda p: [])
    # A3: fake_launch writes session_start to mirror real
    # _perform_launch — the audit-log check uses it to classify success
    # and recover the new sid.
    def fake_launch(**kw):
        from whizzard.session_log import log_session_start
        log_session_start(
            session_id="audit-event-new-sid",
            profile_name=kw["profile_name"],
            network_enabled=False,
            duration_limit_seconds=None,
            allow_broad_mount=kw["allow_broad_mount"],
            image_tag=kw["image"],
            image_id=None,
            mounts=[],
            argv=[],
            start_time=2_000_000_000.0,
        )
    monkeypatch.setattr("whizzard.cli.wake._perform_launch", fake_launch)

    runner = CliRunner()
    res = runner.invoke(app, ["wake", "aaa11111"])
    assert res.exit_code == 0, res.stdout

    # The session_woken event should be appended to the log.
    lines = log.read_text().strip().splitlines()
    parsed = [json.loads(line) for line in lines]
    woken = [e for e in parsed if e.get("event") == "session_woken"]
    assert len(woken) == 1
    assert woken[0]["superseded_session_id"] == "aaa11111"
    # A3: new sid is now populated from the audit-log lookup
    assert woken[0]["new_session_id"] == "audit-event-new-sid"


def test_wake_signal_exit_is_classified_woken_not_failed(tmp_path, monkeypatch):
    """A3 regression: a Ctrl-C during the woken session (exit 130)
    must classify as session_woken (the new container *did* start;
    the user interrupted it), not session_wake_failed (which would
    leave the original sid wakeable and the next bare wake would
    pick the same idle session again)."""
    import typer

    log = tmp_path / "sessions.jsonl"
    real = tmp_path / "mount-dir"
    real.mkdir()
    events = [
        _start("aaa11111", mounts=[
            {"name": "m1", "mode": "rw", "host_path": str(real)},
        ]),
        _end("aaa11111", reason="idle"),
    ]
    _write_log(log, events)
    monkeypatch.setattr("whizzard.wake.SESSIONS_LOG", log)
    monkeypatch.setattr("whizzard.session_log.SESSIONS_LOG", log)
    monkeypatch.setattr("whizzard.wake._docker_label_lookup", lambda p: [])

    # Simulate: launch wrote session_start, then container exited 130
    # (user Ctrl-C). The wake should still record session_woken because
    # the new session *did* start.
    def fake_launch_then_sigint(**kw):
        from whizzard.session_log import log_session_start
        log_session_start(
            session_id="sigint-woken-sid",
            profile_name=kw["profile_name"],
            network_enabled=False,
            duration_limit_seconds=None,
            allow_broad_mount=kw["allow_broad_mount"],
            image_tag=kw["image"],
            image_id=None,
            mounts=[],
            argv=[],
            start_time=2_000_000_000.0,
        )
        raise typer.Exit(code=130)
    monkeypatch.setattr(
        "whizzard.cli.wake._perform_launch", fake_launch_then_sigint
    )

    runner = CliRunner()
    res = runner.invoke(app, ["wake", "aaa11111"])
    # Exit code propagates the session's own exit (130 = SIGINT)
    assert res.exit_code == 130, res.stdout

    parsed = [json.loads(line) for line in log.read_text().strip().splitlines()]
    woken = [e for e in parsed if e.get("event") == "session_woken"]
    wake_failed = [e for e in parsed if e.get("event") == "session_wake_failed"]
    assert len(woken) == 1, "SIGINT after session_start should be classified as woken"
    assert len(wake_failed) == 0, "must not record wake_failed when session_start was logged"
    assert woken[0]["new_session_id"] == "sigint-woken-sid"


def test_wake_no_session_start_classifies_as_wake_failed(tmp_path, monkeypatch):
    """A3: an exit before session_start (e.g. preflight, daemon, image
    not found) must remain session_wake_failed so the original sid
    stays in the wakeable set for retry."""
    import typer

    log = tmp_path / "sessions.jsonl"
    real = tmp_path / "mount-dir"
    real.mkdir()
    events = [
        _start("aaa11111", mounts=[
            {"name": "m1", "mode": "rw", "host_path": str(real)},
        ]),
        _end("aaa11111", reason="idle"),
    ]
    _write_log(log, events)
    monkeypatch.setattr("whizzard.wake.SESSIONS_LOG", log)
    monkeypatch.setattr("whizzard.session_log.SESSIONS_LOG", log)
    monkeypatch.setattr("whizzard.wake._docker_label_lookup", lambda p: [])

    # Simulate: launch exited with a preflight failure (exit 2). No
    # session_start was written. The wake must record session_wake_failed.
    def fake_launch_preflight_fail(**kw):
        raise typer.Exit(code=2)
    monkeypatch.setattr(
        "whizzard.cli.wake._perform_launch", fake_launch_preflight_fail
    )

    runner = CliRunner()
    res = runner.invoke(app, ["wake", "aaa11111"])
    assert res.exit_code == 2, res.stdout

    parsed = [json.loads(line) for line in log.read_text().strip().splitlines()]
    woken = [e for e in parsed if e.get("event") == "session_woken"]
    wake_failed = [e for e in parsed if e.get("event") == "session_wake_failed"]
    assert len(wake_failed) == 1
    assert len(woken) == 0
    assert wake_failed[0]["superseded_session_id"] == "aaa11111"
