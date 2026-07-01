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
from datetime import UTC, datetime
from pathlib import Path

from whizzard._platform import (
    docker_host_path,
    is_windows,
    looks_like_daemon_error,
)
from whizzard.adapters import GenericShellAdapter, HarnessAdapter
from whizzard.config import STATE_DIR, Profile
from whizzard.enforcement import monitor_and_enforce

# Re-exported from the dependency-free images module (avoids an import cycle:
# docker_cmd imports adapters, and the adapters now reference these too).
from whizzard.images import (  # noqa: E402,F401
    WHIZZARD_BROKER_IMAGE,
    WHIZZARD_HERMES_IMAGE,
    WHIZZARD_IMAGE,
)
from whizzard.mounts import Mount, MountMode
from whizzard.session_log import (
    SESSIONS_LOG,
    log_session_end,
    log_session_start,
    merge_agent_events,
    new_session_id,
)
from whizzard.snapshot import event_log_path, request_dir, session_dir

CONTAINER_USER = "whizzard"  # non-root, defined in whizzard/_dockerfiles/Dockerfile


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


def docker_available() -> bool:
    return shutil.which("docker") is not None


def docker_daemon_status() -> tuple[str, str]:
    """Classify Docker readiness for launching a Linux-container cell.

    Returns ``(status, detail)`` where ``detail`` carries docker's stderr (or
    a short note) for the error states and is empty otherwise. ``status`` is:
      ``"missing"``            — the docker CLI is not on PATH
      ``"unreachable"``        — daemon not running (start Docker Desktop)
      ``"daemon_error"``       — docker ran but failed for another reason
                                 (e.g. permission denied / not in the docker
                                 group, a bad context); ``detail`` is the real
                                 error so the wizard doesn't misadvise
      ``"windows_containers"`` — daemon up but in Windows-container mode (our
                                 sandbox is a Linux container and won't run)
      ``"ok"``                 — daemon up, Linux-container mode

    Unlike ``docker_available`` (a PATH check only), this talks to the daemon.
    It reuses ``looks_like_daemon_error`` (the same matcher ``image_exists``
    uses) so "not running" is distinguished from other failures, and bounds
    the call with a ``timeout`` so a mid-startup or unreachable-remote daemon
    can't hang the wizard (matching adjust.py's docker-probe timeout). Used by
    the ``whiz init`` preflight to render a *verified* prerequisite state
    instead of asserting "Docker is running" after only a binary check.
    """
    if not docker_available():
        return ("missing", "")
    try:
        result = subprocess.run(
            ["docker", "info", "--format", "{{.OSType}}"],
            capture_output=True,
            text=True,
            env=_docker_env(),
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        return (
            "unreachable",
            "docker info timed out — the daemon may be starting up or a "
            "remote docker context is unreachable",
        )
    if result.returncode != 0:
        if looks_like_daemon_error(result.stderr):
            return ("unreachable", result.stderr.strip())
        return ("daemon_error", result.stderr.strip())
    ostype = result.stdout.strip().lower()
    if ostype == "windows":
        return ("windows_containers", "")
    if ostype == "linux":
        return ("ok", "")
    return ("daemon_error", f"unexpected container OSType: {ostype!r}")


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
    if looks_like_daemon_error(result.stderr):
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
        if looks_like_daemon_error(result.stderr):
            raise DockerDaemonError(
                f"Docker daemon unreachable while resolving image ID.\n"
                f"docker said: {result.stderr.strip()}"
            )
        return None
    return result.stdout.strip() or None


@dataclass
class ImageMeta:
    """Snapshot of a local image's identity and provenance (Stage 18).

    `id` is the sha256 docker assigns the built image.
    `created` is the image's build timestamp (UTC datetime).
    """

    id: str
    created: datetime


def image_inspect(image: str = WHIZZARD_IMAGE) -> ImageMeta | None:
    """Return id + creation timestamp for the image, or None if missing.

    Uses a tab-separated `--format` to fetch both fields in one daemon call.
    Stage 18 powers `whiz image status` and `whiz image check`.

    Raises ``DockerDaemonError`` if the daemon is unreachable (matches
    ``image_exists`` / ``get_image_id`` per F-B-01).
    """
    if not docker_available():
        return None
    result = subprocess.run(
        [
            "docker",
            "image",
            "inspect",
            "--format",
            "{{.Id}}\t{{.Created}}",
            image,
        ],
        capture_output=True,
        text=True,
        env=_docker_env(),
    )
    if result.returncode != 0:
        if looks_like_daemon_error(result.stderr):
            raise DockerDaemonError(
                f"Docker daemon unreachable while inspecting image.\n"
                f"docker said: {result.stderr.strip()}"
            )
        return None
    line = result.stdout.strip()
    if not line or "\t" not in line:
        return None
    raw_id, raw_created = line.split("\t", 1)
    image_id = raw_id.strip()
    if not image_id:
        return None
    # Docker emits RFC3339 with nanosecond precision (e.g.
    # `2025-09-12T18:42:11.123456789Z`). fromisoformat in 3.11+ tolerates Z
    # and fractional seconds up to microseconds; trim ns to us defensively.
    iso = raw_created.strip()
    if iso.endswith("Z"):
        iso = iso[:-1] + "+00:00"
    # Truncate sub-microsecond precision so fromisoformat doesn't reject it.
    if "." in iso:
        head, frac_and_tz = iso.split(".", 1)
        # frac may be followed by +HH:MM; split on the first sign that isn't
        # the leading digit run.
        frac = frac_and_tz
        tz = ""
        for marker in ("+", "-"):
            idx = frac_and_tz.find(marker)
            if idx > 0:
                frac = frac_and_tz[:idx]
                tz = frac_and_tz[idx:]
                break
        frac = frac[:6]  # microseconds max
        iso = f"{head}.{frac}{tz}"
    try:
        created = datetime.fromisoformat(iso)
    except ValueError:
        return None
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return ImageMeta(id=image_id, created=created)


def parse_dockerfile_base_pin(dockerfile: Path) -> str | None:
    """Return the sha256 digest pinned in the Dockerfile's first FROM, or None.

    Recognizes the `FROM image:tag@sha256:HEX` form. Returns just the
    digest string (e.g. `sha256:01...eb`). Returns None if the FROM line
    is not digest-pinned or the file is unreadable.
    """
    try:
        text = dockerfile.read_text()
    except OSError:
        return None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if not line.upper().startswith("FROM "):
            continue
        # First FROM wins; multi-stage Dockerfiles aren't in scope.
        ref = line.split(None, 1)[1].strip()
        if "@" not in ref:
            return None
        digest = ref.split("@", 1)[1]
        return digest if digest.startswith("sha256:") else None
    return None


def build_run_argv(
    profile: Profile,
    image: str = WHIZZARD_IMAGE,
    resolved_mounts: list[tuple[Mount, MountMode]] | None = None,
    session_id: str | None = None,
    cidfile: Path | None = None,
    adapter: HarnessAdapter | None = None,
    interactive: bool = True,
    mediated_network: str | None = None,
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
    # UID parity (D-56) matches the container user to the host user so
    # bind-mounted files stay writable on Linux/macOS Docker. On Windows
    # `os.getuid` does not exist (would raise AttributeError), and the
    # parity trick doesn't apply anyway — Docker Desktop's WSL2 backend
    # maps bind-mount ownership itself. So on Windows we fall back to the
    # image's default user. (`is_windows()` is the Windows guard.)
    if needs_uid_parity and not is_windows():
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

    # Network posture (D-184/D-187). "none" → no interfaces; "mediated" → the
    # cell joins ONLY the per-session --internal broker network; "onecli" → the
    # cell joins ONLY the per-session --internal network the OneCLI gateway is
    # attached to; "hybrid" → the cell joins the per-session --internal net that
    # carries BOTH the broker and the gateway. All three give egress only
    # through their proxy peer(s). "open" → default bridge (full egress),
    # unchanged. mediated_network carries the per-session isolated network name
    # for the mediated / onecli / hybrid modes. NOTE: hybrid MUST be in this
    # branch — omitting it makes the cell fall through to the default bridge
    # (full egress), which fails OPEN and defeats the mode's whole purpose.
    if profile.network_mode == "none":
        argv += ["--network", "none"]
    elif profile.network_mode in ("mediated", "onecli", "hybrid"):
        if mediated_network is None:
            raise ValueError(
                f"network_mode {profile.network_mode!r} requires an isolated "
                f"network name (mediated_network); the caller must set up the "
                f"proxy route first"
            )
        argv += ["--network", mediated_network]

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
        argv += ["-v", f"{docker_host_path(sess_dir)}:/run/whiz:rw"]
        # Touch the audit log so the bind mount has a target file even on
        # first-ever run. The host writes to it normally; the cell sees a
        # read-only overlay at /run/whiz/audit.jsonl.
        SESSIONS_LOG.parent.mkdir(parents=True, exist_ok=True)
        SESSIONS_LOG.touch(exist_ok=True)
        argv += ["-v", f"{docker_host_path(SESSIONS_LOG)}:/run/whiz/audit.jsonl:ro"]

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
            "host_path": docker_host_path(m.host_path),
            "container_path": m.container_path(),
        }
        for m, mode in (resolved_mounts or [])
    ]


_SCRUBBED_VALUE = "***"


def _argv_for_log(argv: list[str], credential_env_keys: set[str]) -> list[str]:
    """Scrub credential values from a launch argv before it lands in the
    audit log (S20.5 / D-134).

    The host's argv has ``-e KEY=VALUE`` pairs for every env var injected
    into the cell. When KEY is a credential the adapter resolved (via
    OneCLI or host-env fallback per D-134), VALUE is the plaintext
    secret. Logging it verbatim to ``~/.whizzard/logs/sessions.jsonl``
    persists the secret on disk in a place the user may not realize
    contains credentials (backups, log-sharing, support snippets).

    Walk argv looking for ``-e`` followed by ``KEY=VALUE`` where KEY
    matches ``credential_env_keys``; replace VALUE with ``***``. The
    original argv handed to ``docker run`` is untouched — only the
    logged copy is scrubbed.
    """
    if not credential_env_keys:
        return argv
    scrubbed: list[str] = []
    i = 0
    while i < len(argv):
        token = argv[i]
        scrubbed.append(token)
        if token == "-e" and i + 1 < len(argv):
            pair = argv[i + 1]
            if "=" in pair:
                key, _ = pair.split("=", 1)
                if key in credential_env_keys:
                    scrubbed.append(f"{key}={_SCRUBBED_VALUE}")
                else:
                    scrubbed.append(pair)
            else:
                scrubbed.append(pair)
            i += 2
            continue
        i += 1
    return scrubbed


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
    mediated_network: str | None = None,
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
    set (a `whiz adjust --extend` relaunch passes it) else the profile's
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
        mediated_network=mediated_network,
    )

    image_id = get_image_id(image)
    # Stage 15: the effective duration limit is the --extend override when
    # present (a `whiz adjust --extend` relaunch supplies it), else the
    # profile's duration. The session_start event logs the *effective*
    # limit so chained extends accumulate correctly.
    duration_limit = (
        duration_override_seconds if duration_override_seconds is not None
        else profile.duration_seconds
    )
    idle_limit = profile.idle_timeout_seconds
    # F-F-01: split wall-clock from monotonic clock. The audit log needs
    # wall-clock timestamps (humans + log consumers expect real dates);
    # the enforcement loop needs monotonic time (immune to laptop
    # sleep/wake jumps and NTP adjustments — those would fire spurious
    # duration/idle expiry on the next poll).
    wall_start_time = time.time()
    mono_start_time = time.monotonic()
    log_session_start(
        session_id=session_id,
        profile_name=profile.name,
        network_enabled=profile.network_enabled,
        duration_limit_seconds=duration_limit,
        allow_broad_mount=profile.allow_broad_mount,
        image_tag=image,
        image_id=image_id,
        mounts=_mounts_for_log(resolved_mounts),
        # S20.5 / D-134: scrub credential -e KEY=VALUE pairs so secrets
        # don't persist plaintext in ~/.whizzard/logs/sessions.jsonl.
        # The container still receives the real values; only the
        # logged copy is sanitized.
        argv=_argv_for_log(argv, adapter.credential_env_keys()),
        start_time=wall_start_time,
        overrides_used=overrides_used or [],
        preset_name=preset_name,
        # A1+A2: pull --allow-ephemeral off the adapter (set by
        # _perform_launch via F-C-04) so adjust + wake can rehydrate it.
        allow_ephemeral=bool(getattr(adapter, "allow_ephemeral", False)),
    )

    # Stage 15: launch via Popen so a duration / idle limit can interrupt
    # the session. monitor_and_enforce blocks until the container exits or
    # a limit is hit, gracefully stopping the container in the latter case.
    proc = subprocess.Popen(argv, env=_docker_env())

    def _read_container_id() -> str | None:
        if cidfile.exists():
            return cidfile.read_text().strip() or None
        return None

    # F-B-09 (Stage 18): the cidfile lives in STATE_DIR for the duration of
    # the session and must be unlinked before we return — including paths
    # that exit via exception (KeyboardInterrupt during monitor_and_enforce,
    # docker-CLI errors raised by merge_agent_events / log_session_end, ...).
    # Without a try/finally, those orphans accumulate as STATE_DIR debris.
    try:
        expiry_reason = monitor_and_enforce(
            proc,
            container_id_reader=_read_container_id,
            adapter=adapter,
            session_id=session_id,
            start_time=mono_start_time,
            duration_limit=duration_limit,
            idle_limit=idle_limit,
        )

        end_time = time.time()
        container_id = _read_container_id()
        exit_code = proc.returncode if proc.returncode is not None else 0

        # Stage 9 / D-156: merge any agent-emitted events from this session's
        # event file into the main audit log BEFORE writing session_end.
        # Agent events are timestamped during the session, so they belong
        # between session_start and session_end in temporal order.
        merge_agent_events(
            session_id=session_id,
            event_log_path=event_log_path(session_id),
        )

        log_session_end(
            session_id=session_id,
            container_id=container_id,
            exit_status=exit_code,
            end_time=end_time,
            duration_seconds=end_time - wall_start_time,
            expiry_reason=expiry_reason,
        )

        return RunResult(container_id=container_id, exit_code=exit_code)
    finally:
        cidfile.unlink(missing_ok=True)
