"""Duration + idle enforcement — real-Docker smoke (Stage 15).

Drives `monitor_and_enforce` against a real running container and verifies
it actually stops the container — on a duration cap and on an idle timeout.
This exercises the real `docker stats` sampling and `docker stop` path that
the unit tests (which mock Docker) cannot reach.
"""

from __future__ import annotations

import subprocess
import time

import pytest

from whizzard.adapters import GenericShellAdapter
from whizzard.enforcement import monitor_and_enforce

pytestmark = pytest.mark.integration


def _container_running(container_id: str) -> bool:
    """True iff the container exists and is running. A `--rm` container that
    has been stopped is removed, so `docker inspect` fails — also not running."""
    result = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", container_id],
        capture_output=True, text=True,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def _await_container_id(reader, deadline_seconds: float = 15.0) -> str:
    """Block until docker has written the cidfile, or fail."""
    deadline = time.time() + deadline_seconds
    while time.time() < deadline:
        cid = reader()
        if cid is not None:
            return cid
        time.sleep(0.5)
    raise AssertionError("container id never appeared (cidfile not written)")


def test_duration_cap_stops_real_container(launch_real_cell) -> None:
    """A duration cap actually terminates a live container."""
    proc, cid_reader = launch_real_cell(["sleep", "3600"])
    cid = _await_container_id(cid_reader)
    assert _container_running(cid), "container should be up before enforcement"

    reason = monitor_and_enforce(
        proc,
        container_id_reader=cid_reader,
        adapter=GenericShellAdapter(),
        session_id="smoke",
        start_time=time.time(),
        duration_limit=5,
        idle_limit=None,
        poll_interval=2,
        grace_seconds=10,
    )

    assert reason == "duration"
    assert not _container_running(cid), "container still running past its duration cap"


def test_idle_timeout_stops_real_container(launch_real_cell) -> None:
    """An idle timeout terminates a container with no activity. Uses the
    `safe` profile (`--network none`) so there is no network jitter — the
    `sleep` container is genuinely quiet across `docker stats` samples."""
    proc, cid_reader = launch_real_cell(["sleep", "3600"], profile="safe")
    cid = _await_container_id(cid_reader)
    assert _container_running(cid)

    reason = monitor_and_enforce(
        proc,
        container_id_reader=cid_reader,
        adapter=GenericShellAdapter(),
        session_id="smoke",
        start_time=time.time(),
        duration_limit=None,
        idle_limit=8,
        poll_interval=3,
        grace_seconds=10,
    )

    assert reason == "idle"
    assert not _container_running(cid), "container still running past its idle timeout"
