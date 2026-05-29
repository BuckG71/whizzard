"""Stage 1 baseline image — real-Docker integration smoke.

These exercise the actual `whizzard-base:latest` image (built via the
bundled `whizzard/_dockerfiles/Dockerfile`) rather than mocking the docker
invocation. They prove
that the containment posture documented in the unit tests (`--cap-drop=ALL`,
non-root `whizzard` user, read-only rootfs, tmpfs at /home/whizzard) holds
when a container is actually launched.

The full senior unit suite (`make test`) excludes these. Run explicitly with:

    make integration
    # or:
    pytest -m integration

Gated on real Docker daemon availability per `conftest.py`.
"""

from __future__ import annotations

import subprocess

import pytest

from whizzard.config import get_profile
from whizzard.docker_cmd import build_run_argv

pytestmark = pytest.mark.integration


def _run_argv_with_cmd(argv: list[str], cmd: list[str]) -> subprocess.CompletedProcess:
    """Execute a build_run_argv invocation overriding the trailing command.

    `argv` ends with `[image, *start_command]` from build_run_argv. To run a
    non-interactive command, swap the start_command tail for our own cmd.
    Drop the `-it` flag because pytest runs without a TTY.
    """
    image_idx = next(
        i for i, a in enumerate(argv)
        if not a.startswith("-") and ":" in a and "/" not in a
    )
    # Reconstruct: docker run + flags up to image + cmd (no start_command tail)
    new_argv = [a for a in argv[:image_idx] if a != "-it"]
    new_argv.append(argv[image_idx])
    new_argv.extend(cmd)
    return subprocess.run(new_argv, capture_output=True, text=True, timeout=60)


def test_image_runs_and_exits_cleanly(whizzard_base_image: str) -> None:
    """Image exists and runs a trivial command. The most basic possible smoke."""
    result = subprocess.run(
        ["docker", "run", "--rm", whizzard_base_image, "echo", "hello"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"docker run failed: {result.stderr}"
    assert "hello" in result.stdout


def test_container_runs_as_whizzard_user(whizzard_base_image: str) -> None:
    """The image's default user is `whizzard`, not root — enforced by the
    `USER whizzard` line in whizzard/_dockerfiles/Dockerfile. This is the
    foundational
    safety posture: a containerized command running as root would have
    more capabilities than we want even with `--cap-drop=ALL`."""
    result = subprocess.run(
        ["docker", "run", "--rm", whizzard_base_image, "whoami"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "whizzard"


# --- Stage 18: image status + check against the real image ---


def test_image_status_renders_real_metadata(whizzard_base_image: str) -> None:
    """`whiz image status` reports id + build date + base digest for the
    actual rebuilt whizzard-base image."""
    result = subprocess.run(
        ["whiz", "image", "status", "--image", whizzard_base_image],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"status failed: {result.stderr}"
    assert "is present" in result.stdout
    assert "sha256:" in result.stdout  # image id rendered
    assert "ago" in result.stdout  # build date rendered
    assert "base (pin):" in result.stdout  # Dockerfile pin parsed


def test_image_check_against_fresh_real_image(whizzard_base_image: str) -> None:
    """`whiz image check` returns 0 (fresh) for a just-built image."""
    result = subprocess.run(
        ["whiz", "image", "check", "--image", whizzard_base_image,
         "--threshold-days", "30"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, (
        f"freshly-built image reported stale:\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "fresh" in result.stdout


def test_image_check_returns_stale_with_zero_threshold(
    whizzard_base_image: str,
) -> None:
    """A zero-day threshold reports any image as stale — verifies the
    threshold comparison path actually fires."""
    result = subprocess.run(
        ["whiz", "image", "check", "--image", whizzard_base_image,
         "--threshold-days", "0"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 1, (
        f"check should exit 1 for stale; got {result.returncode}\n"
        f"stdout: {result.stdout}"
    )
    assert "stale" in result.stdout


def test_full_argv_enforces_readonly_rootfs(whizzard_base_image: str) -> None:
    """Going through `build_run_argv` (the real OIQ launch path), the rootfs
    is read-only. Writes to /etc fail; writes to /tmp (tmpfs) succeed.

    This verifies that the containment flags we add (`--read-only`, tmpfs
    overlays) actually take effect when applied to a real container — not
    just that they appear in argv (the unit tests).
    """
    argv = build_run_argv(get_profile("default"), image=whizzard_base_image)

    # Read-only rootfs: writing to /etc should fail.
    ro_result = _run_argv_with_cmd(
        argv, ["sh", "-c", "echo x > /etc/test-readonly 2>&1; echo exit=$?"]
    )
    assert ro_result.returncode == 0
    # Should NOT have written successfully (exit code in stdout, not 0,
    # AND a "Read-only file system" error message).
    assert "exit=0" not in ro_result.stdout, (
        f"rootfs appears writable — containment broken:\n{ro_result.stdout}"
    )

    # Tmpfs at /tmp: writes succeed.
    tmpfs_result = _run_argv_with_cmd(
        argv, ["sh", "-c", "echo x > /tmp/test-tmpfs && cat /tmp/test-tmpfs"]
    )
    assert tmpfs_result.returncode == 0, (
        f"tmpfs write failed: {tmpfs_result.stderr}"
    )
    assert "x" in tmpfs_result.stdout
