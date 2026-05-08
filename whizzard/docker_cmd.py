"""Docker invocation for the execution cell.

Stage 1 baseline restrictions, Stage 2 mount handling, Stage 5 session
logging (container id capture via --cidfile, image id capture via
docker image inspect, JSONL log entries for start and end).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from whizzard.config import Profile, STATE_DIR
from whizzard.mounts import Mount, MountMode
from whizzard.session_log import (
    log_session_end,
    log_session_start,
    new_session_id,
)


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


def get_image_id(image: str = WHIZZARD_IMAGE) -> str | None:
    """Return the sha256 image ID for traceability, or None if not found."""
    if not docker_available():
        return None
    result = subprocess.run(
        ["docker", "image", "inspect", "--format", "{{.Id}}", image],
        capture_output=True,
        text=True,
        env=_docker_env(),
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def build_run_argv(
    profile: Profile,
    image: str = WHIZZARD_IMAGE,
    resolved_mounts: list[tuple[Mount, MountMode]] | None = None,
    session_id: str | None = None,
    cidfile: Path | None = None,
) -> list[str]:
    """Build the `docker run` argv applying baseline + profile + mounts.

    Stage 5 additions:
      - --cidfile writes the container ID for end-of-session logging
      - --label whizzard.session_id=<uuid> ties container metadata back to
        the JSONL session log
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

    if session_id:
        argv += ["--label", f"whizzard.session_id={session_id}"]

    if cidfile:
        argv += ["--cidfile", str(cidfile)]

    for mount, mode in resolved_mounts or []:
        argv += ["-v", mount.docker_volume_arg(mode)]
        argv += ["--label", f"whizzard.mount.{mount.name}={mode}"]

    argv += [image, "/bin/bash"]
    return argv


def _mounts_for_log(
    resolved_mounts: list[tuple[Mount, MountMode]] | None,
) -> list[dict]:
    return [
        {
            "name": m.name,
            "mode": mode,
            "host_path": str(m.host_path),
            "container_path": m.container_path(),
        }
        for m, mode in (resolved_mounts or [])
    ]


def run_shell(
    profile: Profile,
    image: str = WHIZZARD_IMAGE,
    resolved_mounts: list[tuple[Mount, MountMode]] | None = None,
    session_id: str | None = None,
) -> RunResult:
    """Launch a contained interactive shell. Blocks until the shell exits.

    Stage 5: writes session_start and session_end events to the JSONL log
    around the subprocess call. Container ID is captured via --cidfile;
    image ID via `docker image inspect`.
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

    if session_id is None:
        session_id = new_session_id()

    # cidfile must NOT exist when docker starts; docker refuses to overwrite.
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    cidfile = STATE_DIR / f"cid-{session_id}.txt"
    if cidfile.exists():
        cidfile.unlink()

    argv = build_run_argv(
        profile,
        image,
        resolved_mounts=resolved_mounts,
        session_id=session_id,
        cidfile=cidfile,
    )

    image_id = get_image_id(image)
    start_time = time.time()
    log_session_start(
        session_id=session_id,
        profile_name=profile.name,
        network_enabled=profile.network_enabled,
        duration_limit_seconds=profile.duration_seconds,
        allow_broad_mount=profile.allow_broad_mount,
        image_tag=image,
        image_id=image_id,
        mounts=_mounts_for_log(resolved_mounts),
        argv=argv,
        start_time=start_time,
    )

    completed = subprocess.run(argv, env=_docker_env())

    end_time = time.time()
    container_id: str | None = None
    if cidfile.exists():
        try:
            container_id = cidfile.read_text().strip() or None
        finally:
            cidfile.unlink(missing_ok=True)

    log_session_end(
        session_id=session_id,
        container_id=container_id,
        exit_status=completed.returncode,
        end_time=end_time,
        duration_seconds=end_time - start_time,
    )

    return RunResult(container_id=container_id, exit_code=completed.returncode)
