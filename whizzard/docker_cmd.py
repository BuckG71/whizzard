"""Docker invocation for the execution cell.

Stage 1 baseline restrictions plus Stage 2 mount handling.
Later stages add image management, adapters, full safety validation.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass

from whizzard.config import Profile
from whizzard.mounts import Mount, MountMode


WHIZZARD_IMAGE = os.environ.get("WHIZZARD_IMAGE", "whizzard-base:latest")
CONTAINER_USER = "whizzard"  # non-root, defined in docker/Dockerfile


@dataclass
class RunResult:
    container_id: str | None
    exit_code: int


def _docker_env() -> dict[str, str]:
    """Environment for docker subprocess calls.

    DOCKER_CLI_HINTS=false suppresses Docker Desktop's "Gordon" suggestion
    banner that prints a misleading 'container error' message after every
    run. Disabling external AI suggestions is also on-brand for a tool
    whose entire purpose is constraining what AI agents can see.
    """
    env = os.environ.copy()
    env["DOCKER_CLI_HINTS"] = "false"
    return env


def docker_available() -> bool:
    return shutil.which("docker") is not None


def image_exists(image: str = WHIZZARD_IMAGE) -> bool:
    if not docker_available():
        return False
    result = subprocess.run(
        ["docker", "image", "inspect", image],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=_docker_env(),
    )
    return result.returncode == 0


def build_run_argv(
    profile: Profile,
    image: str = WHIZZARD_IMAGE,
    resolved_mounts: list[tuple[Mount, MountMode]] | None = None,
) -> list[str]:
    """Build the `docker run` argv applying baseline + profile + mounts.

    Baseline:
      - non-root user
      - no host home mount
      - no Docker socket
      - --rm so the container is reaped on exit
      - --init so PID 1 reaps zombies and forwards signals
      - --cap-drop=ALL; nothing reacquired by default
      - --read-only root with tmpfs for /tmp and /home/whizzard
      - no-new-privileges

    Profile-driven:
      - network on/off

    Stage 2:
      - registered named mounts via -v, with mode capped by registry default
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

    argv += ["--label", f"whizzard.profile={profile.name}"]

    for mount, mode in resolved_mounts or []:
        argv += ["-v", mount.docker_volume_arg(mode)]
        argv += ["--label", f"whizzard.mount.{mount.name}={mode}"]

    argv += [image, "/bin/bash"]
    return argv


def run_shell(
    profile: Profile,
    image: str = WHIZZARD_IMAGE,
    resolved_mounts: list[tuple[Mount, MountMode]] | None = None,
) -> RunResult:
    """Launch a contained interactive shell.

    On success this function does NOT return: the current Python process is
    replaced by docker via os.execvpe(). When docker exits, control passes
    directly to the parent shell with no Python intermediary to mishandle
    TTY release or SIGHUP propagation — sidesteps a known macOS Terminal.app
    issue where `subprocess.run` + `docker run -it` leaves the parent shell
    wedged ("[Process completed]") after container exit.

    Pre-flight failures (docker missing, image missing) still return a
    RunResult so the caller can render an error and exit cleanly.
    """
    if not docker_available():
        print("error: docker not found on PATH", file=sys.stderr)
        return RunResult(container_id=None, exit_code=127)

    if not image_exists(image):
        print(
            f"error: image {image!r} not found.\n"
            f"build it with:  whizzard image build",
            file=sys.stderr,
        )
        return RunResult(container_id=None, exit_code=125)

    argv = build_run_argv(profile, image, resolved_mounts=resolved_mounts)
    # Replace this process with docker. Unreachable past this line on success.
    os.execvpe(argv[0], argv, _docker_env())
    # Defensive: should never get here. If exec fails, fall back to subprocess.
    completed = subprocess.run(argv, env=_docker_env())
    return RunResult(container_id=None, exit_code=completed.returncode)
