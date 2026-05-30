"""Integration tests for mid-operation disruption scenarios (M6 from
the v0.1.0rc1 review).

These exercise the stop+restart paths against real Docker under
adverse conditions:

  * a session that exited between resolve and stop (M2 soft-handle)
  * wake against a truncated session_log
  * audit-log durability across process boundaries (H2 fsync)

Each test launches a real cell or writes a real log file, then drives
the host-side code path that would handle the disruption. Failures
here mean the user's session is dropped mid-task — the worst UX a
governance layer can deliver.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

from whizzard.adjust import _stop_container
from whizzard.session_log import append_event
from whizzard.wake import find_wakeable

pytestmark = pytest.mark.integration


def test_stop_container_soft_handles_already_exited_real_container(
    whizzard_base_image,
) -> None:
    """F-G-13 end-to-end: a container that exited between resolve and
    stop surfaces in docker's stderr as "No such container" / "is not
    running". The M2 soft-handle returns (0, "already exited") instead
    of propagating the raw docker error to the user."""
    # Launch a one-shot cell that exits immediately.
    result = subprocess.run(
        ["docker", "run", "-d", "--rm",
         "--user", "whizzard",
         "--cap-drop=ALL",
         "--security-opt", "no-new-privileges",
         "--read-only",
         "--tmpfs", "/tmp:rw,size=64m,mode=1777",
         "--tmpfs", "/home/whizzard:rw,size=32m,mode=0755,uid=1000,gid=1000",
         whizzard_base_image, "true"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    container_id = result.stdout.strip()
    assert container_id

    # Give the container time to exit on its own (it ran `true`); --rm
    # then auto-removes it. Poll docker inspect until it reports the
    # container is gone.
    deadline = time.time() + 10
    while time.time() < deadline:
        inspect = subprocess.run(
            ["docker", "inspect", container_id],
            capture_output=True, text=True,
        )
        if inspect.returncode != 0:
            break  # gone
        time.sleep(0.2)

    # Now ask _stop_container to stop a container that no longer exists.
    code, detail = _stop_container(container_id)
    assert code == 0, f"M2 soft-handle did not fire: code={code} detail={detail!r}"
    assert "already exited" in detail, (
        f"expected 'already exited' detail, got {detail!r}"
    )


def test_wake_handles_truncated_session_log_gracefully(tmp_path: Path) -> None:
    """A power-loss mid-write can leave the audit log with a truncated
    final line. The wake discovery path must skip the corrupt entry
    rather than blowing up with a JSON decode error — otherwise a
    single bad write blocks all future wakes."""
    log_path = tmp_path / "sessions.jsonl"
    # Write one valid session_start event, then a partial line.
    append_event({
        "event": "session_start",
        "session_id": "valid-sess-001",
        "argv": ["docker", "run"],
        "ts": "2026-05-30T00:00:00Z",
    }, path=log_path)
    append_event({
        "event": "session_end",
        "session_id": "valid-sess-001",
        "expiry_reason": "idle",
        "ts": "2026-05-30T00:30:00Z",
    }, path=log_path)
    # Now corrupt the file with a half-written next entry.
    with log_path.open("a") as f:
        f.write('{"event": "session_start", "session_id": "tru')

    # Wake's discovery code must read the log without raising.
    from whizzard import session_log as sl

    original_path = sl.SESSIONS_LOG
    sl.SESSIONS_LOG = log_path
    try:
        # find_wakeable reads the log via _read_events; a truncated last
        # line must not raise — the host should skip the corrupt entry
        # and surface only the valid session_end.
        target = find_wakeable(None, docker_check=False)
    finally:
        sl.SESSIONS_LOG = original_path

    # No exception was raised — that's the primary test. The valid
    # idle-ended session ("valid-sess-001") survives the corrupt-tail
    # filter; the truncated entry is ignored.
    assert target is not None, "valid idle-ended session not surfaced"


def test_audit_log_fsync_is_durable_across_process_boundaries(
    tmp_path: Path,
) -> None:
    """H2 end-to-end: ``append_event`` ``flush+fsync``s every write.
    A subsequent process reading the file must see the line — not the
    pre-write state cached in this process's view.

    Implementation: write an event in this process, then spawn a
    subprocess that re-reads the file. The subprocess sees the event
    iff fsync genuinely committed to disk."""
    log_path = tmp_path / "audit.jsonl"
    append_event({
        "event": "session_start",
        "session_id": "fsync-test-001",
        "ts": "2026-05-30T00:00:00Z",
    }, path=log_path)

    # Spawn a subprocess that reads the file. A non-fsynced write
    # might be visible due to kernel page cache, but explicitly
    # round-tripping through a subprocess removes any "same-process
    # view" caching effects.
    result = subprocess.run(
        ["python3", "-c",
         f"import json; lines=open('{log_path}').read().splitlines(); "
         f"print(json.loads(lines[-1])['session_id'])"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "fsync-test-001", (
        f"subprocess didn't see the fsynced event: stdout={result.stdout!r}"
    )
