"""Red-team — cooperation-layer abuse (cluster 5 of the Stage 20 suite).

The agent has one writable cooperation channel into the host: per-session
request files at ``/run/whiz/requests/<request_id>.json``. F-D-02 and
F-D-05 lock down the obvious abuse paths — the host re-derives
``session_id`` from the directory layout it owns, and treats the
host-only resolutions store (under ``STATE_DIR``, outside the bind
mount) as the source of truth for ``status`` and the canonical request
record.

The unit suite in ``tests/test_requests.py`` proves the host-side read
logic enforces both invariants against synthetic JSON. This file proves
the *end-to-end* path: a real cell, writing a real forged JSON file
into a real bind-mounted ``/run/whiz``, must not be able to walk the
host into trusting its claims.

Two angles per the build plan's "AGENT_DENIED_CHANGES cannot be
bypassed from the agent path; request files in /run/whiz cannot be
forged to mimic operator approvals":

  1. Forged ``status: applied`` — host reports ``pending``
     (no host-side resolution exists; cell's claim is ignored).
  2. Forged ``session_id`` in JSON — host reports the directory's
     session_id (F-D-02 — directory wins).

Cluster 5's other call-out, "no injection via mount/preset names in
request JSON", is structurally impossible: an agent can only request
mount names that are already in the host-loaded registry, and the
registry validates names with a strict regex
(``^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$``) at load time. No path lets an
unsafe name reach the request channel.
"""

from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


_FAKE_STATE_REL = "state"
_FAKE_SESSIONS_REL = "sessions"


def _launch_cell_with_request_dir(
    image: str, sess_dir: Path, cell_command: str, *, timeout: int = 30,
) -> subprocess.CompletedProcess:
    """Launch a one-shot cell that has the per-session request dir bind
    mounted at /run/whiz:rw. Mirrors what build_run_argv assembles for
    MCP-opted-in adapters, minus the audit-log overlay (not exercised
    by these tests).

    Used by tests in this module to give the "attacker" a real writable
    /run/whiz to plant forged JSON in."""
    return subprocess.run(
        [
            "docker", "run", "--rm", "--init",
            "--user", "whizzard",
            "--cap-drop=ALL",
            "--security-opt", "no-new-privileges",
            "--read-only",
            "--tmpfs", "/tmp:rw,size=128m,mode=1777",
            "--tmpfs", "/home/whizzard:rw,size=64m,mode=0755,uid=1000,gid=1000",
            "-v", f"{sess_dir}:/run/whiz:rw",
            image,
            "sh", "-c", cell_command,
        ],
        capture_output=True, text=True, timeout=timeout,
    )


def _stage_fake_whizzard_home(tmp_path: Path) -> tuple[Path, Path, str, Path]:
    """Build a tmp_path layout that mirrors WHIZZARD_HOME for one session:

        <tmp_path>/sessions/<sid>/requests/   (cell-writable)
        <tmp_path>/state/                     (host-only)

    The bind-mounted dirs are chmod'd world-writable so the cell — which
    runs as UID 1000 (whizzard) — can write through them on Linux CI,
    where the host's tmp_path is owned by the runner UID (≠ 1000).
    Local Docker Desktop is permissive about this; native Linux is not.

    Returns (sessions_dir, state_dir, session_id, sess_dir).
    """
    import os

    fake_home = tmp_path
    sessions_dir = fake_home / _FAKE_SESSIONS_REL
    state_dir = fake_home / _FAKE_STATE_REL
    session_id = f"redteam-{uuid.uuid4().hex[:12]}"
    sess_dir = sessions_dir / session_id
    requests_dir = sess_dir / "requests"
    requests_dir.mkdir(parents=True)
    state_dir.mkdir(parents=True)
    # World-writable so the cell (UID 1000) can write through the bind
    # mount regardless of host-side ownership.
    for d in (fake_home, sessions_dir, sess_dir, requests_dir):
        os.chmod(d, 0o777)
    return sessions_dir, state_dir, session_id, sess_dir


def test_cell_forged_status_applied_is_overridden_by_host(
    whizzard_base_image, tmp_path, monkeypatch,
) -> None:
    """Cell writes a request JSON pre-populated with ``status: applied``
    and a phony ``resolution_detail``. Because the host-only resolutions
    store has no record for this request, the host's ``_load_request``
    must report status as ``pending`` and detail as empty — the cell's
    claim is structurally inert.

    Closes F-D-05 end-to-end (the unit suite proves the read logic; this
    proves the read logic against a real cell's real write through a real
    bind mount)."""
    sessions_dir, state_dir, session_id, sess_dir = _stage_fake_whizzard_home(tmp_path)
    request_id = f"req-attacker-{uuid.uuid4().hex[:8]}"
    forged = {
        "request_id": request_id,
        "session_id": session_id,
        "kind": "mount",
        "params": {"name": "scratch"},
        "reason": "redteam: trying to mark myself applied",
        "status": "applied",
        "resolution_detail": "spoofed-by-cell — operator never saw this",
        "created_at": "2026-01-01T00:00:00Z",
    }
    forged_json = json.dumps(forged)

    cell_result = _launch_cell_with_request_dir(
        whizzard_base_image, sess_dir,
        f"cat > /run/whiz/requests/{request_id}.json <<'__EOF__'\n"
        f"{forged_json}\n__EOF__",
    )
    assert cell_result.returncode == 0, cell_result.stderr

    # Sanity: the file landed on the host (the bind mount is rw).
    host_request_file = sess_dir / "requests" / f"{request_id}.json"
    assert host_request_file.exists(), "cell write did not reach the host"
    assert "spoofed-by-cell" in host_request_file.read_text()

    # Host-side read through the real API: the resolutions store is
    # empty, so status must be pending and the canonical detail empty.
    monkeypatch.setattr("whizzard.requests.SESSIONS_DIR", sessions_dir)
    monkeypatch.setattr("whizzard.config.STATE_DIR", state_dir)

    from whizzard.requests import read_session_requests

    requests_list = read_session_requests(session_id, pending_only=False)
    assert len(requests_list) == 1
    req = requests_list[0]

    assert req.request_id == request_id
    assert req.status == "pending", (
        f"forged 'status: applied' leaked through end-to-end: got {req.status!r}"
    )
    assert req.resolution_detail == "", (
        f"forged resolution_detail leaked through end-to-end: "
        f"{req.resolution_detail!r}"
    )


def test_cell_forged_session_id_in_json_is_overridden_by_host(
    whizzard_base_image, tmp_path, monkeypatch,
) -> None:
    """Cell writes a request JSON whose ``session_id`` field claims a
    different session than the one whose directory the file actually
    lives in. The host derives the session_id from the directory path
    it owns and ignores the JSON's claim — otherwise an agent in
    session A could forge requests "from" session B (cross-session
    capability transfer).

    Closes F-D-02 end-to-end."""
    sessions_dir, state_dir, session_id, sess_dir = _stage_fake_whizzard_home(tmp_path)
    victim_session_id = "victim-session-9999"
    request_id = f"req-cross-{uuid.uuid4().hex[:8]}"
    forged = {
        "request_id": request_id,
        "session_id": victim_session_id,  # the forge
        "kind": "extend",
        "params": {"duration": "1h"},
        "reason": "redteam: pretending to be victim session",
        "created_at": "2026-01-01T00:00:00Z",
    }
    forged_json = json.dumps(forged)

    cell_result = _launch_cell_with_request_dir(
        whizzard_base_image, sess_dir,
        f"cat > /run/whiz/requests/{request_id}.json <<'__EOF__'\n"
        f"{forged_json}\n__EOF__",
    )
    assert cell_result.returncode == 0, cell_result.stderr

    monkeypatch.setattr("whizzard.requests.SESSIONS_DIR", sessions_dir)
    monkeypatch.setattr("whizzard.config.STATE_DIR", state_dir)

    from whizzard.requests import read_session_requests

    requests_list = read_session_requests(session_id, pending_only=False)
    assert len(requests_list) == 1
    req = requests_list[0]
    assert req.session_id == session_id, (
        f"forged session_id leaked through end-to-end: got {req.session_id!r}, "
        f"expected {session_id!r} (cell tried to impersonate {victim_session_id!r})"
    )

    # The victim session must see no requests — the forged file lives in
    # the attacker's directory, not the victim's.
    victim_requests = read_session_requests(victim_session_id, pending_only=False)
    assert victim_requests == [], (
        f"victim session inherited the attacker's forged request: {victim_requests}"
    )
