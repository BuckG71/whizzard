"""Integration smoke: container resource caps are enforced by Docker.

Drives the real ``build_run_argv`` launch path (per the "smokes drive the real
argv path" rule) with explicit capped Profiles, then verifies Docker actually
enforces the cap — a memory hog is OOM-killed under a hard memory ceiling, and
a fork storm is contained by ``--pids-limit``. Uses tiny caps so the
assertions are fast and unambiguous, and constructs Profiles directly (not via
``get_profile``) so the result does not depend on the user's config overlay.
"""

import subprocess
from pathlib import Path  # noqa: F401  (kept for parity with sibling smokes)

import pytest

from whizzard.config import Profile
from whizzard.docker_cmd import build_run_argv

pytestmark = pytest.mark.integration


def _run_capped(image: str, profile: Profile, cmd: list[str], timeout: int = 60):
    """Launch a real cell for `profile` via the production argv and run `cmd`.

    Mirrors the conftest `run_in_cell` harness: build the real argv, drop
    `-it` (pytest has no TTY), then swap the harness start-command for `cmd`.
    """
    argv = build_run_argv(profile, image=image)
    image_idx = next(i for i, a in enumerate(argv) if a == image)
    launch = [a for a in argv[:image_idx] if a != "-it"]
    launch.append(image)
    launch.extend(cmd)
    return subprocess.run(launch, capture_output=True, text=True, timeout=timeout)


def test_memory_cap_oom_kills_a_hog(whizzard_base_image):
    """A hard 64m ceiling (swap disabled) OOM-kills a process that tries to
    balloon to ~512MB. The allocation must never complete."""
    prof = Profile(
        name="mem-smoke",
        network_enabled=False,
        duration_seconds=None,
        memory_limit="64m",
        memory_swap="64m",  # == memory_limit → swap disabled → hard ceiling
    )
    # Build a ~512MB string in a shell variable (resident memory, not a stream)
    # from coreutils only — no python needed in the minimal base image.
    hog = [
        "bash", "-lc",
        "x=$(head -c 536870912 /dev/zero | tr '\\0' a); echo LEN=${#x}",
    ]
    result = _run_capped(whizzard_base_image, prof, hog)
    assert result.returncode != 0, (
        f"memory hog survived a 64m hard cap (expected OOM kill): "
        f"rc={result.returncode} stdout={result.stdout!r}"
    )
    assert "LEN=536870912" not in result.stdout, (
        "the 512MB allocation completed under a 64m cap — not enforced"
    )


def test_pids_limit_blocks_a_fork_storm(whizzard_base_image):
    """`--pids-limit 16` caps the cgroup's PID count: forking 100 background
    processes hits the ceiling, and the failed forks surface the kernel's
    EAGAIN as a fork-failure message. (Counting live PIDs after saturation is
    impossible — at the ceiling even `ls`/`grep` can't fork — so we assert on
    the fork-failure signature instead.)"""
    prof = Profile(
        name="pids-smoke",
        network_enabled=False,
        duration_seconds=None,
        pids_limit=16,
    )
    cmd = ["bash", "-lc", "for i in $(seq 1 100); do sleep 30 & done"]
    result = _run_capped(whizzard_base_image, prof, cmd)
    blob = (result.stdout + result.stderr).lower()
    assert "fork" in blob or "resource temporarily unavailable" in blob, (
        f"no fork-failure signature under --pids-limit 16 (cap not enforced): "
        f"rc={result.returncode} stdout={result.stdout!r} "
        f"stderr={result.stderr!r}"
    )
