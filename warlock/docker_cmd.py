"""Docker invocation for the execution cell.

Stage 1 builds the `docker run` argv with baseline restrictions and launches
an interactive shell. Later stages add mounts, image management, adapters.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass

from warlock.config import Profile


WARLOCK_IMAGE = os.environ.get("WARLOCK_IMAGE", "warlock-base:latest")
CONTAINER_USER = "warlock"  # non-root, defined in docker/Dockerfile


@dataclass
class RunResult:
    container_id: str | None
    exit_code: int


def docker_available() -> bool:
    return shutil.which("docker") is not None


def image_exists(image: str = WARLOCK_IMAGE) -> bool:
    if not docker_available():
        return False
    result = subprocess.run(
        ["docker", "image", "inspect", image],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def build_run_argv(profile: Profile, image: str = WARLOCK_IMAGE) -> list[str]:
    """Build the `docker run` argv applying baseline + profile restrictions.

    Baseline (Stage 1):
      - non-root user
      - no host home mount
      - no Docker socket
      - --rm so the container is reaped on exit
      - --init so PID 1 reaps zombies and forwards signals
      - drop all Linux capabilities; reacquire only what's strictly needed
      - read-only root filesystem with tmpfs for /tmp
      - no-new-privileges

    Profile-driven:
      - network on/off
    """
    argv = [
        "docker", "run",
        "--rm",
        "--init",
        "-it",
        "--user", CONTAINER_USER,
        "--cap-drop=ALL",
        "--security-opt", "no-new-privileges",
        "--read-only",
        "--tmpfs", "/tmp:rw,size=128m,mode=1777",
        "--tmpfs", f"/home/{CONTAINER_USER}:rw,size=64m,mode=0755,uid=1000,gid=1000",
    ]

    if not profile.network_enabled:
        argv += ["--network", "none"]

    # Container name and labels for traceability
    argv += [
        "--label", f"warlock.profile={profile.name}",
    ]

    argv += [image, "/bin/bash"]
    return argv


def run_shell(profile: Profile, image: str = WARLOCK_IMAGE) -> RunResult:
    """Launch a contained interactive shell. Blocks until shell exits."""
    if not docker_available():
        print("error: docker not found on PATH", file=sys.stderr)
        return RunResult(container_id=None, exit_code=127)

    if not image_exists(image):
        print(
            f"error: image {image!r} not found.\n"
            f"build it with:  warlock image build",
            file=sys.stderr,
        )
        return RunResult(container_id=None, exit_code=125)

    argv = build_run_argv(profile, image)
    completed = subprocess.run(argv)
    return RunResult(container_id=None, exit_code=completed.returncode)
