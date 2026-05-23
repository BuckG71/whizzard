"""wake.py end-to-end — integration smoke (Stage 15.5).

Most of wake's surface is pure-Python (selection, eligibility, mount-check,
reconstruction) and covered by the unit + CLI tiers. The integration smoke
proves two things that pure unit tests can't:

1. The compiled CLI binary (`python -m whizzard wake ...`) correctly
   reads the session log, resolves an idle-ended session, and renders the
   reconstructed launch params under --dry-run. This catches packaging
   wiring bugs — module imports, entry-point registration, config-dir
   bootstrap (`ensure_whizzard_home`) — that the in-process CliRunner
   tests don't see.

2. `_docker_label_lookup` correctly reports "no match" for a sid that has
   no live container — i.e., a freshly idle-ended session resolves cleanly
   on wake without a false-positive STILL_ACTIVE block.

A heavier "full real launch via wake" smoke is deliberately skipped: it
would require the test to provision profile/mount config inside an
isolated WHIZZARD_HOME and clean up the launched container afterwards.
The launch path is already exercised by other integration tests and by
the wake CLI tests' `_perform_launch` mocking; layering another full
launch here doesn't catch new surface.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def _write_log(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        for ev in events:
            fh.write(json.dumps(ev) + "\n")


def _start(sid: str, **kw) -> dict:
    return {
        "event": "session_start",
        "session_id": sid,
        "profile": kw.get("profile", "default"),
        "image_tag": "whizzard-base:latest",
        "image_id": "sha256:abc",
        "mounts": kw.get("mounts", []),
        "argv": kw.get("argv", []),
        "allow_broad_mount": False,
        "duration_limit_seconds": None,
        "network_enabled": False,
        "start_time": "2026-05-22T10:00:00Z",
        "ts": "2026-05-22T10:00:00Z",
    }


def _end(sid: str, reason: str = "idle") -> dict:
    return {
        "event": "session_end",
        "session_id": sid,
        "container_id": "cid-stale",
        "exit_status": 137,
        "duration_seconds": 3600.0,
        "end_time": "2026-05-22T11:00:00Z",
        "ts": "2026-05-22T11:00:00Z",
        "expiry_reason": reason,
    }


def _whiz_subprocess(args: list[str], whizzard_home: Path) -> subprocess.CompletedProcess:
    """Run `python -m whizzard <args>` with WHIZZARD_HOME pointing at an
    isolated test directory. Returns the CompletedProcess for assertions."""
    env = os.environ.copy()
    env["WHIZZARD_HOME"] = str(whizzard_home)
    # PYTHONPATH ensures the repo's whizzard package is importable when the
    # test environment uses an editable / source install.
    repo_root = Path(__file__).resolve().parent.parent.parent
    env["PYTHONPATH"] = f"{repo_root}:{env.get('PYTHONPATH', '')}"
    # Invoke the Typer app via a one-liner rather than `python -m`, since
    # whizzard.cli is a package (no __main__.py). This is the most
    # packaging-realistic way to drive the app in-process for the smoke
    # without depending on `whiz` being on PATH in the test environment.
    return subprocess.run(
        [sys.executable, "-c",
         "import sys; from whizzard.cli import app; "
         "sys.argv = ['whiz', *sys.argv[1:]]; app()",
         *args],
        capture_output=True, text=True, env=env, timeout=30,
    )


def test_wake_subprocess_dry_run_resolves_idle_session(tmp_path):
    """End-to-end through the CLI module entry point.

    The dry-run output should contain the resolved session's profile and
    mount set, proving the full chain (CLI invocation → log read →
    selection → reconstruction → render) works as packaged.
    """
    whizzard_home = tmp_path / "whiz-home"
    log = whizzard_home / "logs" / "sessions.jsonl"
    real_mount = tmp_path / "project"
    real_mount.mkdir()
    _write_log(log, [
        _start("aaa11111", profile="default",
               mounts=[{"name": "proj", "mode": "rw",
                        "host_path": str(real_mount),
                        "container_path": "/work/proj"}]),
        _end("aaa11111", reason="idle"),
    ])

    res = _whiz_subprocess(["wake", "aaa11111", "--dry-run"], whizzard_home)

    assert res.returncode == 0, (
        f"non-zero exit: stdout={res.stdout}\nstderr={res.stderr}"
    )
    assert "Would wake" in res.stdout
    assert "default" in res.stdout
    assert "proj:rw" in res.stdout


def test_wake_subprocess_idle_only_eligibility_via_real_cli(tmp_path):
    """Duration-capped sessions are rejected with reason at the CLI level."""
    whizzard_home = tmp_path / "whiz-home"
    log = whizzard_home / "logs" / "sessions.jsonl"
    _write_log(log, [
        _start("aaa11111"),
        _end("aaa11111", reason="duration"),  # not idle — not wakeable
    ])

    res = _whiz_subprocess(["wake", "aaa11111"], whizzard_home)

    # Exit 2 = the documented error code per the CLI module
    assert res.returncode == 2, res.stdout
    assert "duration" in res.stdout
    assert "not idle" in res.stdout
    # The "next verb" pointer is the operationally-important part —
    # users without a wakeable session need to know what to do.
    assert "whiz launch" in res.stdout


def test_wake_docker_label_lookup_negative_for_ended_session(tmp_path):
    """An idle-ended session whose container is gone resolves cleanly without
    triggering the STILL_ACTIVE block. This is the regression case where
    `_docker_label_lookup` against a non-running sid would (incorrectly)
    return a stale match — confirming the real docker query is correct."""
    whizzard_home = tmp_path / "whiz-home"
    log = whizzard_home / "logs" / "sessions.jsonl"
    real_mount = tmp_path / "project"
    real_mount.mkdir()
    # Use a sid the live docker daemon will never have running.
    sid = "wake-smoke-aaa1234567890"
    _write_log(log, [
        _start(sid, mounts=[{"name": "p", "mode": "rw",
                              "host_path": str(real_mount),
                              "container_path": "/work/p"}]),
        _end(sid, reason="idle"),
    ])

    res = _whiz_subprocess(["wake", sid, "--dry-run"], whizzard_home)

    assert res.returncode == 0, (
        f"sid that no container holds should resolve fine on wake: "
        f"stdout={res.stdout}\nstderr={res.stderr}"
    )
    assert "Would wake" in res.stdout
    # The STILL_ACTIVE branch's message must NOT appear — that's the
    # regression-guard signal.
    assert "already running" not in res.stdout
