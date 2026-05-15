"""Docker invocation for the execution cell.

Stage 1 baseline restrictions, Stage 2 mount handling, Stage 5 session
logging (container id capture via --cidfile, image id capture via
docker image inspect, JSONL log entries for start and end).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from whizzard.adapters import GenericShellAdapter, HarnessAdapter
from whizzard.config import Profile, STATE_DIR
from whizzard.mounts import Mount, MountMode
from whizzard.session_log import (
    SESSIONS_LOG,
    log_session_end,
    log_session_start,
    merge_agent_events,
    new_session_id,
)
from whizzard.snapshot import event_log_path, session_dir


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
    adapter: HarnessAdapter | None = None,
) -> list[str]:
    """Build the `docker run` argv applying baseline + profile + mounts + adapter.

    Stage 5 additions:
      - --cidfile writes the container ID for end-of-session logging
      - --label whizzard.session_id=<uuid> ties container metadata back to
        the JSONL session log

    Stage 7 additions:
      - adapter chooses the in-container start_command (defaults to
        GenericShellAdapter / /bin/bash)
      - adapter.container_env() vars passed via -e
      - adapter.working_dir() passed via -w
      - whizzard.harness=<name> label for traceability
    """
    if adapter is None:
        adapter = GenericShellAdapter()

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
    argv += ["--label", f"whizzard.harness={adapter.name}"]

    if session_id:
        argv += ["--label", f"whizzard.session_id={session_id}"]

    if cidfile:
        argv += ["--cidfile", str(cidfile)]

    for mount, mode in resolved_mounts or []:
        argv += ["-v", mount.docker_volume_arg(mode)]
        argv += ["--label", f"whizzard.mount.{mount.name}={mode}"]

    # Adapter-driven env injection. Combines harness-config env (`container_env`)
    # with optional Whiz MCP server env (`mcp_env`) per Stage 9 / D-156. Sorted
    # for deterministic argv (helps tests). mcp_env keys override container_env
    # keys on collision — the MCP wiring is Whizzard's, not the harness's.
    combined_env: dict[str, str] = dict(adapter.container_env())
    mcp_env: dict[str, str] = {}
    if session_id:
        mcp_env = adapter.mcp_env(session_id)
        combined_env.update(mcp_env)
    for k, v in sorted(combined_env.items()):
        argv += ["-e", f"{k}={v}"]

    # Stage 9 / D-156: when the adapter wants MCP, mount the per-session
    # state directory (snapshot + events) and the host audit log into the
    # cell so the in-cell MCP server can read/write through the conventional
    # /run/whiz/ paths declared in mcp_env. Mounts only happen when the
    # adapter opts in (non-empty mcp_env).
    if mcp_env and session_id:
        sess_dir = session_dir(session_id)
        sess_dir.mkdir(parents=True, exist_ok=True)
        argv += ["-v", f"{sess_dir}:/run/whiz:rw"]
        # Touch the audit log so the bind mount has a target file even on
        # first-ever run. The host writes to it normally; the cell sees a
        # read-only overlay at /run/whiz/audit.jsonl.
        SESSIONS_LOG.parent.mkdir(parents=True, exist_ok=True)
        SESSIONS_LOG.touch(exist_ok=True)
        argv += ["-v", f"{SESSIONS_LOG}:/run/whiz/audit.jsonl:ro"]

    wd = adapter.working_dir()
    if wd:
        argv += ["-w", wd]

    argv += [image]
    argv += adapter.start_command()
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
    overrides_used: list[dict] | None = None,
    adapter: HarnessAdapter | None = None,
) -> RunResult:
    """Launch a contained interactive shell. Blocks until the shell exits.

    Stage 5: writes session_start and session_end events to the JSONL log
    around the subprocess call. Container ID is captured via --cidfile;
    image ID via `docker image inspect`.

    Stage 6: any safety overrides the user opted into (--allow-broad-mount)
    are recorded in the session_start event so audits can see what was
    overridden.
    """
    # Defensive: callers (cli.py) should pre-flight these and surface red
    # errors. If we land here without docker or the image, return an error
    # exit code silently — no stderr writes — so we don't double-report.
    if not docker_available():
        return RunResult(container_id=None, exit_code=127)
    if not image_exists(image):
        return RunResult(container_id=None, exit_code=125)

    if session_id is None:
        session_id = new_session_id()

    # cidfile must NOT exist when docker starts; docker refuses to overwrite.
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    cidfile = STATE_DIR / f"cid-{session_id}.txt"
    if cidfile.exists():
        cidfile.unlink()

    if adapter is None:
        adapter = GenericShellAdapter()

    argv = build_run_argv(
        profile,
        image,
        resolved_mounts=resolved_mounts,
        session_id=session_id,
        cidfile=cidfile,
        adapter=adapter,
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
        overrides_used=overrides_used or [],
    )

    completed = subprocess.run(argv, env=_docker_env())

    end_time = time.time()
    container_id: str | None = None
    if cidfile.exists():
        try:
            container_id = cidfile.read_text().strip() or None
        finally:
            cidfile.unlink(missing_ok=True)

    # Stage 9 / D-156: merge any agent-emitted events from this session's
    # event file into the main audit log BEFORE writing session_end. Agent
    # events are timestamped during the session, so they belong between
    # session_start and session_end in temporal order.
    merge_agent_events(
        session_id=session_id,
        event_log_path=event_log_path(session_id),
    )

    log_session_end(
        session_id=session_id,
        container_id=container_id,
        exit_status=completed.returncode,
        end_time=end_time,
        duration_seconds=end_time - start_time,
    )

    return RunResult(container_id=container_id, exit_code=completed.returncode)
