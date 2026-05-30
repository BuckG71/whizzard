"""Red-team — stop+restart / adjust (cluster 6 of the Stage 20 suite).

The agent has one mutable surface that the host re-reads across
relaunch: the per-session ``snapshot.json``. The threat model (residual
risk 6.6) flags that the agent *can* overwrite this file — the
``/run/whiz`` bind mount is rw because the cell legitimately writes
``events.jsonl`` and ``requests/*.json`` in the same directory. The
question this cluster answers: does a poisoned snapshot grant the agent
any actual capability on relaunch?

Test angle: launch a cell, have it overwrite ``snapshot.json`` with a
payload claiming widened capabilities, then exercise the host's
``write_snapshot`` (the function the relaunch path calls). Assert the
host's authoritative state overwrites the cell's poison — the host
does not read the cell-written snapshot, it writes a fresh one from
profile + resolved_mounts.

(A second angle — that the cell cannot influence the relaunch's actual
``docker run`` flags — is structurally covered by the launch path:
``build_run_argv`` reads from the host's profile and the host's mount
registry, with no input channel from inside the cell.)
"""

from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def _launch_cell_with_session_dir(
    image: str, sess_dir: Path, cell_command: str, *, timeout: int = 30,
) -> subprocess.CompletedProcess:
    """One-shot cell with the session_dir bind-mounted at /run/whiz:rw."""
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


def test_cell_poisoned_snapshot_overwritten_by_host_relaunch_write(
    whizzard_base_image, tmp_path,
) -> None:
    """The relaunch flow calls ``write_snapshot`` with host-derived state
    (profile + resolved_mounts). Any prior content of ``snapshot.json`` —
    including content the cell wrote during the previous session — is
    overwritten. This proves the cell cannot smuggle widened
    capabilities across a relaunch by editing its own snapshot.

    Closes the integration-tier proof for residual risk 6.6 in the
    threat model: the cell *can* write the file, but writing it has no
    effect on the host's actual policy."""
    import os

    from whizzard.config import Profile
    from whizzard.mounts import Mount
    from whizzard.snapshot import write_snapshot

    session_id = f"redteam-adjust-{uuid.uuid4().hex[:12]}"
    fake_whizzard_home = tmp_path / ".whizzard-fake"
    sess_dir = fake_whizzard_home / "sessions" / session_id
    sess_dir.mkdir(parents=True)
    snapshot_path = sess_dir / "snapshot.json"
    # World-writable on the bind-mount path so the cell (UID 1000) can
    # write through on Linux CI where the host's tmp_path is owned by
    # the runner UID (≠ 1000). Local Docker Desktop is permissive about
    # this; native Linux is not.
    for d in (tmp_path, fake_whizzard_home, fake_whizzard_home / "sessions", sess_dir):
        os.chmod(d, 0o777)

    # Phase 1: Cell writes a poisoned snapshot claiming a wildly permissive
    # profile (network on, no duration cap, broad-mount enabled, fake
    # extra mounts not in the host registry).
    poison_payload = {
        "session_id": session_id,
        "profile": {
            "name": "poisoned-by-cell",
            "network_enabled": True,
            "duration_seconds": None,  # claim "unlimited"
            "idle_timeout_seconds": None,
            "allow_broad_mount": True,
            "description": "cell-fabricated profile — should be discarded",
        },
        "mounts": [
            {
                "name": "fake-root-mount",
                "host_path": "/",
                "container_path": "/mounts/fake-root-mount",
                "mode": "rw",
            },
        ],
        "harness": "cell-claims-superuser",
        "snapshot_written_at": "2020-01-01T00:00:00+00:00",
        "expires_at": None,
    }
    poison_json = json.dumps(poison_payload, indent=2)

    cell_result = _launch_cell_with_session_dir(
        whizzard_base_image, sess_dir,
        f"cat > /run/whiz/snapshot.json <<'__EOF__'\n{poison_json}\n__EOF__",
    )
    assert cell_result.returncode == 0, cell_result.stderr

    # Sanity: the poisoned file landed on the host.
    on_disk = json.loads(snapshot_path.read_text())
    assert on_disk["profile"]["name"] == "poisoned-by-cell"
    assert on_disk["harness"] == "cell-claims-superuser"

    # Phase 2: Host runs the relaunch path. write_snapshot is what
    # cli/_launch.py calls before each launch (including relaunches via
    # whiz adjust). It takes host-derived inputs and writes a fresh file.
    real_profile = Profile(
        name="safe",
        network_enabled=False,
        duration_seconds=600,
        allow_broad_mount=False,
        description="bundled safe profile",
    )
    real_mount = Mount(
        name="scratch", host_path=tmp_path / "scratch",
        default_mode="rw", description="real registered scratch mount",
    )
    (tmp_path / "scratch").mkdir()

    write_snapshot(
        session_id=session_id,
        profile=real_profile,
        resolved_mounts=[(real_mount, "rw")],
        harness_name="generic",
        whizzard_home=fake_whizzard_home,
    )

    # Phase 3: assertion. The relaunch's authoritative state, not the
    # cell's poison, lands in snapshot.json.
    rewritten = json.loads(snapshot_path.read_text())

    assert rewritten["profile"]["name"] == "safe", (
        f"cell's fabricated profile name survived the relaunch: "
        f"{rewritten['profile']}"
    )
    assert rewritten["profile"]["network_enabled"] is False, (
        "cell's claim of network_enabled=True survived the relaunch"
    )
    assert rewritten["profile"]["duration_seconds"] == 600, (
        "cell's claim of unlimited duration survived the relaunch"
    )
    assert rewritten["profile"]["allow_broad_mount"] is False, (
        "cell's claim of allow_broad_mount=True survived the relaunch"
    )
    assert rewritten["harness"] == "generic", (
        f"cell's harness claim survived the relaunch: {rewritten['harness']}"
    )
    # Mounts must come from the host's resolved_mounts, not the cell's
    # fabricated "fake-root-mount".
    mount_names = {m["name"] for m in rewritten["mounts"]}
    assert mount_names == {"scratch"}, (
        f"mount set drifted from host's resolved_mounts: {mount_names}"
    )
    assert all(m["host_path"] != "/" for m in rewritten["mounts"]), (
        "cell's claim that the root filesystem was mounted survived"
    )
