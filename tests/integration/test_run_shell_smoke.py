"""run_shell launch path — real-Docker smoke (Stage 15 integration).

Drives the *full* run_shell path non-interactively against real Docker:
build_run_argv -> Popen -> monitor_and_enforce -> session-end logging. A
short duration cap is set; the test verifies the container is launched, run,
and terminated at the cap, with expiry_reason recorded in the session log.
This is the most complete end-to-end check of the launch path — the unit
tests only ever exercised it with Docker mocked.
"""

from __future__ import annotations

import json
import subprocess
import threading

import pytest

from whizzard.adapters import GenericShellAdapter
from whizzard.config import Profile

pytestmark = pytest.mark.integration


def _kill_by_session_label(session_id: str) -> None:
    """Force-remove any container tagged with this session id — cleanup
    backstop in case enforcement didn't (or the test failed mid-run)."""
    result = subprocess.run(
        ["docker", "ps", "-aq", "--filter",
         f"label=whizzard.session_id={session_id}"],
        capture_output=True, text=True,
    )
    for cid in result.stdout.split():
        subprocess.run(
            ["docker", "rm", "-f", cid],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )


def test_run_shell_enforces_duration_cap_end_to_end(
    whizzard_base_image: str, tmp_path, monkeypatch
) -> None:
    """A session launched through the real run_shell path, with a short
    duration cap, is terminated at the cap — expiry_reason=duration logged."""
    import whizzard.docker_cmd as dc
    from whizzard import enforcement, session_log

    log = tmp_path / "sessions.jsonl"
    monkeypatch.setattr(session_log, "SESSIONS_LOG", log)
    monkeypatch.setattr(dc, "STATE_DIR", tmp_path / "state")
    # Shrink the monitor poll so the test runs in seconds, not half a minute.
    monkeypatch.setattr(enforcement, "POLL_INTERVAL_SECONDS", 2.0)

    session_id = "smoke-runshell-duration"
    profile = Profile(
        name="smoke", network_enabled=False, duration_seconds=6,
        description="run_shell smoke",
    )
    # A long-lived in-cell command so the duration cap — not the command
    # finishing — is what ends the session.
    adapter = GenericShellAdapter(config={"start_command": ["sleep", "3600"]})

    holder: dict = {}

    def _go() -> None:
        holder["result"] = dc.run_shell(
            profile, image=whizzard_base_image, session_id=session_id,
            adapter=adapter, interactive=False,
        )

    thread = threading.Thread(target=_go, daemon=True)
    thread.start()
    thread.join(timeout=60)

    try:
        assert not thread.is_alive(), "run_shell never returned — enforcement hung"
        result = holder["result"]
        # The container was SIGTERM'd at the cap — not a clean exit.
        assert result.exit_code != 0

        events = [
            json.loads(line)
            for line in log.read_text().splitlines() if line.strip()
        ]
        kinds = [e["event"] for e in events]
        assert "session_start" in kinds, kinds
        end = next(e for e in events if e["event"] == "session_end")
        assert end["expiry_reason"] == "duration", end
    finally:
        _kill_by_session_label(session_id)
