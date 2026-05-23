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
from whizzard.config import STATE_DIR, Profile
from whizzard.enforcement import monitor_and_enforce
from whizzard.mounts import Mount, MountMode
from whizzard.session_log import (
    SESSIONS_LOG,
    log_session_end,
    log_session_start,
    merge_agent_events,
    new_session_id,
)
from whizzard.snapshot import event_log_path, request_dir, session_dir

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


class DockerDaemonError(Exception):
    """The Docker CLI is installed but couldn't talk to the daemon.

    Distinct from "image missing" so callers can show "is Docker Desktop
    running?" instead of "did you build the image?" (F-B-01).
    """


# Substrings docker emits when the daemon is unreachable. Stable across
# Docker for Mac, Docker Desktop on Windows, and Linux daemons. Matched
# case-sensitively because docker emits these verbatim.
_DAEMON_DOWN_INDICATORS = (
    "Cannot connect to the Docker daemon",
    "Is the docker daemon running",
    "error during connect",  # Windows named-pipe variant
)


def _looks_like_daemon_error(stderr: str) -> bool:
    return any(token in stderr for token in _DAEMON_DOWN_INDICATORS)


def docker_available() -> bool:
    return shutil.which("docker") is not None


def image_exists(image: str = WHIZZARD_IMAGE) -> bool:
    """True if the local daemon has the image, False if it doesn't.

    Raises ``DockerDaemonError`` if the CLI is present but the daemon is
    unreachable — previously this silently returned False, sending the
    user to ``docker pull`` when the real problem was Docker Desktop not
    running (F-B-01).
    """
    if not docker_available():
        return False
    result = subprocess.run(
        ["docker", "image", "inspect", image],
        capture_output=True,
        text=True,
        env=_docker_env(),
    )
    if result.returncode == 0:
        return True
    if _looks_like_daemon_error(result.stderr):
        raise DockerDaemonError(
            f"Docker CLI is installed but the daemon is not reachable.\n"
            f"On macOS / Windows, start Docker Desktop. On Linux, check "
            f"`systemctl status docker`.\n"
            f"docker said: {result.stderr.strip()}"
        )
    return False


def get_image_id(image: str = WHIZZARD_IMAGE) -> str | None:
    """Return the sha256 image ID for traceability, or None if not found.

    Raises ``DockerDaemonError`` if the daemon is unreachable, matching
    ``image_exists`` (F-B-01). None still means "image not registered."
    """
    if not docker_available():
        return None
    result = subprocess.run(
        ["docker", "image", "inspect", "--format", "{{.Id}}", image],
        capture_output=True,
        text=True,
        env=_docker_env(),
    )
    if result.returncode != 0:
        if _looks_like_daemon_error(result.stderr):
            raise DockerDaemonError(
                f"Docker daemon unreachable while resolving image ID.\n"
                f"docker said: {result.stderr.strip()}"
            )
        return None
    return result.stdout.strip() or None


def build_run_argv(
    profile: Profile,
    image: str = WHIZZARD_IMAGE,
    resolved_mounts: list[tuple[Mount, MountMode]] | None = None,
    session_id: str | None = None,
    cidfile: Path | None = None,
    adapter: HarnessAdapter | None = None,
    interactive: bool = True,
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

    `interactive` (default True) controls the `-it` flag. True is the normal
    launch — a user at a terminal. False omits `-it` for a non-TTY launch
    (the integration smoke harness; also a future non-interactive/daemon
    launch mode). It changes only the TTY allocation, never the containment
    flags.
    """
    if adapter is None:
        adapter = GenericShellAdapter()

    # Stage 8 M6: harness-driven mounts (HERMES_HOME, etc). Resolved up
    # front because a uid_parity=True entry rewrites the --user flag and
    # the home-dir tmpfs ownership for the whole container (D-56).
    harness_mounts = adapter.container_mounts()
    needs_uid_parity = any(cm.uid_parity for cm in harness_mounts)
    if needs_uid_parity:
        user_uid = os.getuid()
        user_gid = os.getgid()
        user_arg = f"{user_uid}:{user_gid}"
        home_tmpfs_owner = f"uid={user_uid},gid={user_gid}"
    else:
        user_arg = CONTAINER_USER
        home_tmpfs_owner = "uid=1000,gid=1000"

    argv = ["docker", "run", "--rm", "--init"]
    if interactive:
        argv.append("-it")
    argv += [
        "--user", user_arg,
        "--cap-drop=ALL",
        "--security-opt", "no-new-privileges",
        "--read-only",
        "--tmpfs", "/tmp:rw,size=128m,mode=1777",
        "--tmpfs", f"/home/{CONTAINER_USER}:rw,size=64m,mode=0755,{home_tmpfs_owner}",
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

    # Stage 8 M6: harness-driven mounts (resolved above for uid_parity).
    # Emitted after user mounts so user paths can't shadow harness paths.
    for cm in harness_mounts:
        argv += ["-v", cm.docker_volume_arg()]
        argv += ["--label", f"whizzard.harness_mount={cm.container_path}={cm.mode}"]

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
        # Pre-create the audit.jsonl target inside sess_dir before the bind
        # mount lands. Docker Desktop on macOS (virtiofs) requires the nested
        # mountpoint to exist on the host before the second `-v` resolves;
        # otherwise runc reports "mountpoint outside of rootfs" because the
        # first bind mount (sess_dir → /run/whiz) provides the parent dir but
        # the file at /run/whiz/audit.jsonl is created by the second mount.
        # M7 smoke surfaced this 2026-05-19.
        (sess_dir / "audit.jsonl").touch(exist_ok=True)
        # Stage 14: pre-create the agent request channel. It lives inside
        # sess_dir, so the /run/whiz mount below exposes it to the cell with
        # no extra `-v`; pre-creating it means `whiz requests` finds an empty
        # dir rather than a missing one before the agent writes anything.
        request_dir(session_id).mkdir(parents=True, exist_ok=True)
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
    preset_name: str | None = None,
    duration_override_seconds: int | None = None,
    interactive: bool = True,
) -> RunResult:
    """Launch a contained shell. Blocks until the session exits.

    `interactive` (default True) passes through to `build_run_argv`'s `-it`
    flag. False is the non-TTY launch the integration smoke harness uses.

    Stage 5: writes session_start and session_end events to the JSONL log
    around the subprocess call. Container ID is captured via --cidfile;
    image ID via `docker image inspect`.

    Stage 6: any safety overrides the user opted into (--allow-broad-mount)
    are recorded in the session_start event so audits can see what was
    overridden.

    Stage 15: the container is launched via `subprocess.Popen` and handed to
    `monitor_and_enforce`, which blocks until the container exits or a limit
    is hit. The effective duration limit is `duration_override_seconds` when
    set (an `oiq adjust --extend` relaunch passes it) else the profile's
    `duration_seconds`; the idle limit is the profile's `idle_timeout_seconds`.
    The session_end event records `expiry_reason` (clean / duration / idle).
    """
    # Defensive: callers (cli.py) should pre-flight these and surface red
    # errors. If we land here without docker or the image, return an error
    # exit code silently — no stderr writes — so we don't double-report.
    # F-B-01: image_exists now raises DockerDaemonError on a missing daemon.
    # The CLI preflight catches and prints; here we treat it identically to
    # "no docker" (exit 127) so a defensive direct caller still exits cleanly.
    if not docker_available():
        return RunResult(container_id=None, exit_code=127)
    try:
        if not image_exists(image):
            return RunResult(container_id=None, exit_code=125)
    except DockerDaemonError:
        return RunResult(container_id=None, exit_code=127)

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
        interactive=interactive,
    )

    image_id = get_image_id(image)
    # Stage 15: the effective duration limit is the --extend override when
    # present (an `oiq adjust --extend` relaunch supplies it), else the
    # profile's duration. The session_start event logs the *effective*
    # limit so chained extends accumulate correctly.
    duration_limit = (
        duration_override_seconds if duration_override_seconds is not None
        else profile.duration_seconds
    )
    idle_limit = profile.idle_timeout_seconds
    start_time = time.time()
    log_session_start(
        session_id=session_id,
        profile_name=profile.name,
        network_enabled=profile.network_enabled,
        duration_limit_seconds=duration_limit,
        allow_broad_mount=profile.allow_broad_mount,
        image_tag=image,
        image_id=image_id,
        mounts=_mounts_for_log(resolved_mounts),
        argv=argv,
        start_time=start_time,
        overrides_used=overrides_used or [],
        preset_name=preset_name,
    )

    # Stage 15: launch via Popen so a duration / idle limit can interrupt
    # the session. monitor_and_enforce blocks until the container exits or
    # a limit is hit, gracefully stopping the container in the latter case.
    proc = subprocess.Popen(argv, env=_docker_env())

    def _read_container_id() -> str | None:
        if cidfile.exists():
            return cidfile.read_text().strip() or None
        return None

    expiry_reason = monitor_and_enforce(
        proc,
        container_id_reader=_read_container_id,
        adapter=adapter,
        session_id=session_id,
        start_time=start_time,
        duration_limit=duration_limit,
        idle_limit=idle_limit,
    )

    end_time = time.time()
    container_id = _read_container_id()
    cidfile.unlink(missing_ok=True)
    exit_code = proc.returncode if proc.returncode is not None else 0

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
        exit_status=exit_code,
        end_time=end_time,
        duration_seconds=end_time - start_time,
        expiry_reason=expiry_reason,
    )

    return RunResult(container_id=container_id, exit_code=exit_code)
