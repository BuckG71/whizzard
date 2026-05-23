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
    monkeypatch.setattr("whizzard.wake._docker_label_lookup", lambda p: [])
    # Don't actually run docker; capture the relaunch call.
    captured: dict = {}
    def fake_launch(**kw):
        captured.update(kw)
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
    # relaunched with bbb's params
    assert captured["profile_name"] == "build"
    assert captured["mount_specs"] == ["m1:ro"]


def test_wake_preserves_allow_broad_mount(tmp_path, monkeypatch):
    """D-168: a session launched with --allow-broad-mount stays broad on wake."""
    log = tmp_path / "sessions.jsonl"
    real = tmp_path / "mount-dir"
    real.mkdir()
    start = _start("aaa11111", mounts=[
        {"name": "m1", "mode": "rw", "host_path": str(real)},
    ])
    start["allow_broad_mount"] = True
    events = [start, _end("aaa11111", reason="idle")]
    _write_log(log, events)
    monkeypatch.setattr("whizzard.wake.SESSIONS_LOG", log)
    monkeypatch.setattr("whizzard.wake._docker_label_lookup", lambda p: [])

    captured: dict = {}
    def fake_launch(**kw):
        captured.update(kw)
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
    # Both modules read SESSIONS_LOG; patch both to ensure the audit
    # event writes into the test file we can read back.
    monkeypatch.setattr("whizzard.wake.SESSIONS_LOG", log)
    monkeypatch.setattr("whizzard.wake._docker_label_lookup", lambda p: [])
    monkeypatch.setattr("whizzard.cli.wake._perform_launch", lambda **kw: None)

    runner = CliRunner()
    res = runner.invoke(app, ["wake", "aaa11111"])
    assert res.exit_code == 0, res.stdout

    # The session_woken event should be appended to the log.
    lines = log.read_text().strip().splitlines()
    parsed = [json.loads(line) for line in lines]
    woken = [e for e in parsed if e.get("event") == "session_woken"]
    assert len(woken) == 1
    assert woken[0]["superseded_session_id"] == "aaa11111"
