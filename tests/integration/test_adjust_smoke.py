"""adjust.py real-Docker primitives — integration smoke (Stage 13).

`whiz adjust` resolves a running session by its Docker label and stops the
container. Those two operations touch real Docker; the rest of adjust.py
(Changes, detect_noops, render_diff, the orchestration) is pure Python and
covered by the unit tier. These verify the two real-Docker primitives
against live containers.
"""

from __future__ import annotations

import subprocess
import time

import pytest

from whizzard.adjust import _docker_label_lookup, _stop_container

pytestmark = pytest.mark.integration


def _await_container_id(reader, deadline_seconds: float = 30.0) -> str:
    """Wait for the cidfile to appear with content.

    L1 review finding: bumped from 15s to 30s — shared-runner Docker
    daemons in GitHub Actions can stall under load and the test flaked
    once at 15s. Local Docker Desktop is always sub-second.
    """
    deadline = time.time() + deadline_seconds
    while time.time() < deadline:
        cid = reader()
        if cid is not None:
            return cid
        time.sleep(0.5)
    raise AssertionError("container id never appeared (cidfile not written)")


def _await_label_match(session_id: str, deadline_seconds: float = 30.0):
    """Poll the label lookup until the cell is registered + running.

    The cidfile is written at container *creation*, but `_docker_label_lookup`
    uses `docker ps`, which lists only *running* containers — so there's a
    brief window after the cidfile appears where the lookup returns []. Under
    shared-runner Docker load that window is occasionally wide enough that a
    single-shot lookup flakes ("expected exactly one match, got []"). Polling
    removes the race; returns the last result so the caller's assertion still
    reports a genuine empty/late outcome if the deadline is hit.
    """
    deadline = time.time() + deadline_seconds
    matches: list = []
    while time.time() < deadline:
        matches = _docker_label_lookup(session_id)
        if matches:
            return matches
        time.sleep(0.5)
    return matches


def _container_running(container_id: str) -> bool:
    result = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", container_id],
        capture_output=True, text=True,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def test_docker_label_lookup_finds_running_cell(launch_real_cell) -> None:
    """resolve_session's label lookup locates a running OIQ cell by its
    `whizzard.session_id` label — the format string in the `docker ps`
    invocation works against a real container."""
    proc, cid_reader, session_id = launch_real_cell(["sleep", "3600"])
    cid = _await_container_id(cid_reader)

    matches = _await_label_match(session_id)

    assert len(matches) == 1, f"expected exactly one match, got {matches}"
    found_sid, found_cid = matches[0]
    assert found_sid == session_id
    assert found_cid == cid


def test_stop_container_stops_a_running_cell(launch_real_cell) -> None:
    """adjust's `_stop_container` actually stops a live cell — the real
    `docker stop` half of the mid-session stop+restart."""
    proc, cid_reader, _ = launch_real_cell(["sleep", "3600"])
    cid = _await_container_id(cid_reader)
    assert _container_running(cid)

    code, detail = _stop_container(cid, grace_seconds=10)

    assert code == 0, f"_stop_container failed: {detail}"
    assert not _container_running(cid), "container still running after _stop_container"
