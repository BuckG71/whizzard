"""Hermes adapter.

Bridges Whizzard's contained execution cell to a Hermes installation per the
Stage 8 design decisions (D-86 through D-90). Per D-153, harness-specific
identifiers — config.yaml, gateway.lock, HERMES_HOME, platform tokens — live
inside this module and the `whiz hermes` subcommand surface. Core stays neutral.

Build-plan status: Actions 1 (skeleton) and 2 (active_capabilities Protocol)
are done. Action 3 (this commit) implements container_env() with OneCLI-mediated
credential injection. The gateway.lock pre-check and wrap_up() via
`docker exec /quit` arrive in subsequent build-plan milestones.
"""

from __future__ import annotations

import contextlib
import json
import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from whizzard.adapters._credentials import (
    fetch_secret,
)
from whizzard.adapters.base import (
    ContainerMount,
    HarnessAdapter,
    PreflightResult,
    WrapUpResult,
    WrapUpStatus,
)
from whizzard.mcp_server import (
    ENV_AUDIT_LOG_PATH,
    ENV_EVENT_LOG_PATH,
    ENV_REQUEST_DIR,
    ENV_SESSION_ID,
    ENV_SNAPSHOT_PATH,
)

# In-cell paths where Whizzard mounts per-session state for the MCP server.
# These are conventional and known by the adapter so it can wire the env
# vars; the actual `-v` docker mounts that put files at these paths come
# from core's `docker_cmd` (Stage 9 M5). The requests/ dir sits inside the
# `/run/whiz` mount, so no extra `-v` flag is needed for it (Stage 14).
_IN_CELL_WHIZ_DIR = "/run/whiz"
_IN_CELL_SNAPSHOT_PATH = f"{_IN_CELL_WHIZ_DIR}/snapshot.json"
_IN_CELL_AUDIT_LOG_PATH = f"{_IN_CELL_WHIZ_DIR}/audit.jsonl"
_IN_CELL_EVENT_LOG_PATH = f"{_IN_CELL_WHIZ_DIR}/events.jsonl"
_IN_CELL_REQUEST_DIR = f"{_IN_CELL_WHIZ_DIR}/requests"


_DEFAULT_START_COMMAND: list[str] = ["hermes", "gateway", "run"]
_GATEWAY_LOCK_FILENAME = "gateway.lock"

# In-cell HERMES_HOME path. Matches Hermes's own convention ($HOME/.hermes)
# where $HOME is the cell user's home dir from docker/Dockerfile. Mounting
# the host hermes_home here lets in-cell Hermes find its profile under its
# default lookup, no flag plumbing required.
_IN_CELL_HERMES_HOME = "/home/whizzard/.hermes"


# --- Profile creation (D-86) -----------------------------------------------

# Files/dirs excluded when cloning a Hermes profile:
#   - auth.json + auth.lock: D-80 (credentials never enter a derived profile)
#   - .env: defense-in-depth, additional secret material
#   - *.db, gateway.*, sessions/, logs/: per-instance runtime state
#   - .git, hermes-agent: irrelevant install/repo metadata
_CLONE_EXCLUDE_NAMES: set[str] = {
    "auth.json",
    "auth.lock",
    ".env",
    ".DS_Store",
    "Thumbs.db",
    "gateway.lock",
    "gateway.pid",
    "gateway_state.json",
    ".skills_prompt_snapshot.json",
    ".curator_state",
    ".usage.json",
    ".update_check",
    "context_length_cache.yaml",
    "models_dev_cache.json",
    "channel_directory.json",
    "discord_threads.json",
}
_CLONE_EXCLUDE_SUFFIXES: tuple[str, ...] = (
    ".db",
    ".db-shm",
    ".db-wal",
    ".log",
    ".pyc",
    ".pyo",
)
_CLONE_EXCLUDE_DIRS: set[str] = {
    "sessions",
    "logs",
    "cache",
    "tmp",
    "audio_cache",
    "checkpoints",
    "state-snapshots",
    "image_cache",
    "pairing",
    "hooks",
    "hermes-agent",
    "__pycache__",
    ".git",
    ".curator_backups",
}


class HermesProfileExistsError(Exception):
    """Target profile directory already exists; refuses to clobber."""


class HermesProfileSourceMissingError(Exception):
    """Explicit --clone-from target does not exist on disk."""


class HermesProfileNameError(Exception):
    """Invalid or reserved profile name."""


@dataclass(frozen=True)
class HermesProfileCreated:
    path: Path
    source: Path | None  # None when the new profile is empty


def _hermes_profile_path(name: str, parent: Path | None = None) -> Path:
    """Map a Hermes profile name to its on-disk path.

    Convention: `default` is `<parent>/.hermes` (Hermes's own default); any
    other name is `<parent>/.hermes-<name>`. `parent` defaults to home.
    """
    base = parent if parent is not None else Path.home()
    if name == "default":
        return base / ".hermes"
    return base / f".hermes-{name}"


def _clone_ignore(src: str, names: list[str]) -> list[str]:
    """shutil.copytree `ignore=` callable — names in `src` to skip."""
    skipped: list[str] = []
    for n in names:
        if n in _CLONE_EXCLUDE_NAMES or n in _CLONE_EXCLUDE_DIRS or n.endswith(_CLONE_EXCLUDE_SUFFIXES):
            skipped.append(n)
    return skipped


def create_profile(
    name: str,
    clone_from: str | None = None,
    no_clone: bool = False,
    parent_dir: Path | None = None,
) -> HermesProfileCreated:
    """Create a Hermes profile per D-86.

    - Bare (`clone_from=None`, `no_clone=False`): clone from `default`
      (`<parent>/.hermes`) if it exists; gracefully degrade to an empty
      profile if it doesn't.
    - `clone_from=<source>`: clone from the named profile; error if it
      does not exist on disk.
    - `no_clone=True`: create an empty profile directory.

    Clones exclude `auth.json` (D-80) and per-instance runtime state.

    Raises:
      HermesProfileNameError, HermesProfileExistsError,
      HermesProfileSourceMissingError.
    """
    if name == "default":
        raise HermesProfileNameError(
            "'default' is reserved for Hermes's default profile "
            f"({_hermes_profile_path('default', parent_dir)}); pick a different name."
        )
    if not name or "/" in name or name.startswith("."):
        raise HermesProfileNameError(
            f"invalid profile name {name!r} "
            "(must be non-empty, no slashes, no leading dot)"
        )

    target = _hermes_profile_path(name, parent_dir)
    if target.exists():
        raise HermesProfileExistsError(
            f"profile directory already exists: {target}. "
            "Pick a different name or remove the existing directory first."
        )

    if no_clone:
        target.mkdir(parents=True, exist_ok=False)
        return HermesProfileCreated(path=target, source=None)

    if clone_from is None:
        source = _hermes_profile_path("default", parent_dir)
        if not source.exists():
            target.mkdir(parents=True, exist_ok=False)
            return HermesProfileCreated(path=target, source=None)
    else:
        source = _hermes_profile_path(clone_from, parent_dir)
        if not source.exists():
            raise HermesProfileSourceMissingError(
                f"clone source not found: {source} "
                f"(expected for --clone-from {clone_from!r})"
            )

    shutil.copytree(source, target, ignore=_clone_ignore)
    return HermesProfileCreated(path=target, source=source)


# Hermes convention (per hermes_research.md L17): each platform's credential
# is consumed from an env var named `<PLATFORM>_BOT_TOKEN`. OneCLI secret
# names use the same string — one identifier across both the OneCLI surface
# and the container env. Credential fetching itself lives in `_credentials`
# (Stage 12 generalization) — this module owns only the Hermes-specific
# platform → env-var-name convention.


def _env_var_for_platform(platform: str) -> str:
    return f"{platform.upper()}_BOT_TOKEN"


def _resolve_hermes_home(config: dict) -> Path | None:
    raw = config.get("hermes_home")
    if not raw:
        return None
    return Path(raw).expanduser()


def _read_gateway_lock(hermes_home: Path) -> dict | None:
    """Return parsed gateway.lock JSON, or None if absent or unparseable.

    Per real-install inspection: gateway.lock holds JSON like
    `{"pid": <int>, "kind": "hermes-gateway", "argv": [...], "start_time": ...}`.
    Malformed lock files are treated as absent — Hermes overwrites on start.
    """
    lock_path = hermes_home / _GATEWAY_LOCK_FILENAME
    if not lock_path.exists():
        return None
    try:
        data: dict = json.loads(lock_path.read_text())
        return data
    except (OSError, json.JSONDecodeError):
        return None


def _is_pid_alive(pid: int) -> bool:
    """Probe whether `pid` exists. Signal 0 is a no-op delivery check."""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists; we just can't signal it. Still alive.
        return True


@dataclass
class HermesAdapter:
    """Adapter for the Hermes agent harness.

    Gateway mode is the default invocation (D-88); interactive mode is opted
    into via harness config or the `--interactive` CLI flag (handled in the
    `whiz hermes` subcommand surface, not here).
    """

    name: str = "hermes"
    config: dict = field(default_factory=dict)
    # Records the credential source per platform after `container_env` runs,
    # so `active_capabilities` can surface which platforms came via OneCLI
    # vs the host-env fallback (Stage 12, D-134 visibility piece).
    _credential_sources: dict[str, str] = field(default_factory=dict)

    def start_command(self) -> list[str]:
        cmd = self.config.get("start_command")
        if cmd is None:
            return list(_DEFAULT_START_COMMAND)
        if isinstance(cmd, list):
            return list(cmd)
        return shlex.split(cmd)

    def container_env(self) -> dict[str, str]:
        # Platforms come from `harnesses.json["platforms"]` (D-89 amended).
        # Each platform's credential is fetched via the shared utility
        # (Stage 12): OneCLI first, host env as fallback per D-134's
        # "OneCLI not installed" failure-mode note.
        env: dict[str, str] = {}
        self._credential_sources.clear()
        for platform in self.config.get("platforms", []) or []:
            var = _env_var_for_platform(platform)
            result = fetch_secret(var)
            env[var] = result.value
            self._credential_sources[platform] = result.source
        # secrets (D-162): generic env-var-name list for LLM-provider keys,
        # additional bot tokens, and any other long-lived credentials the
        # harness needs inside the cell. Same delivery as platforms (OneCLI
        # first, env-var fallback). Plaintext values never live in the
        # harness config; only names. Auth.json mounting remains prohibited
        # by D-80.
        for secret_name in self.config.get("secrets", []) or []:
            result = fetch_secret(secret_name)
            env[secret_name] = result.value
            self._credential_sources[secret_name] = result.source
        # HERMES_HOME points at the in-cell mount target where the host
        # profile is mounted (Stage 8 M6, D-79). Only set when hermes_home
        # is configured; otherwise leave Hermes to discover its default
        # (ephemeral tmpfs home) — a misconfiguration the user should fix.
        if _resolve_hermes_home(self.config) is not None:
            env["HERMES_HOME"] = _IN_CELL_HERMES_HOME
        extra = self.config.get("env", {}) or {}
        for k, v in extra.items():
            env[str(k)] = str(v)
        return env

    def working_dir(self) -> str | None:
        wd = self.config.get("working_dir")
        return wd if wd else None

    def wrap_up(self, container_id: str, grace_seconds: int) -> WrapUpResult:
        # `/quit` from the original D-88 framing is a chat-mode slash command
        # (hermes_research.md L208–209). For gateway mode, Hermes's SIGTERM
        # handler is the canonical graceful-shutdown channel: drain active
        # turns, write final state, exit. `docker stop --time=<grace>` sends
        # SIGTERM and falls back to SIGKILL after the grace window — the
        # exact contract D-29 / D-30 want from wrap_up.
        try:
            stop_result = subprocess.run(
                ["docker", "stop", "--time", str(grace_seconds), container_id],
                capture_output=True,
                text=True,
                timeout=grace_seconds + 5,  # subprocess overhead slack
                check=False,
            )
        except FileNotFoundError:
            return WrapUpResult(
                status=WrapUpStatus.ERROR,
                detail="`docker` not on PATH",
            )
        except subprocess.TimeoutExpired:
            return WrapUpResult(
                status=WrapUpStatus.TIMEOUT,
                detail=f"`docker stop` did not return within {grace_seconds + 5}s",
            )

        if stop_result.returncode != 0:
            return WrapUpResult(
                status=WrapUpStatus.ERROR,
                detail=(
                    f"`docker stop` exit {stop_result.returncode}: "
                    f"{stop_result.stderr.strip() or '(no stderr)'}"
                ),
            )

        # docker stop returned 0; inspect the container's actual exit code
        # to distinguish a clean SIGTERM exit from a SIGKILL forced after grace.
        try:
            inspect_result = subprocess.run(
                [
                    "docker", "inspect",
                    "--format", "{{.State.ExitCode}}",
                    container_id,
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return WrapUpResult(
                status=WrapUpStatus.SUCCESS,
                detail="container stopped (exit-code probe unavailable)",
            )

        if inspect_result.returncode != 0:
            return WrapUpResult(
                status=WrapUpStatus.SUCCESS,
                detail="container stopped (exit-code probe failed)",
            )

        try:
            container_exit = int(inspect_result.stdout.strip())
        except ValueError:
            return WrapUpResult(
                status=WrapUpStatus.SUCCESS,
                detail="container stopped (unparseable exit code)",
            )

        if container_exit == 137:
            # 128 + 9 (SIGKILL) — docker had to force-kill after the grace window.
            return WrapUpResult(
                status=WrapUpStatus.TIMEOUT,
                detail=f"container required SIGKILL after {grace_seconds}s grace",
            )

        return WrapUpResult(
            status=WrapUpStatus.SUCCESS,
            detail=f"container stopped cleanly (exit {container_exit})",
        )

    def health_check_command(self) -> list[str] | None:
        return None

    def active_capabilities(self) -> list[str]:
        # Surfaces what the cell is about to do: declared platforms,
        # credential-source breakdown when `container_env` has run, and
        # Whiz MCP server availability. Approval-mode warning per D-90 is
        # added by a later build step (it requires reading `approvals.mode`
        # from `config.yaml`).
        caps: list[str] = []
        platforms = self.config.get("platforms", []) or []
        if platforms:
            caps.append(f"platforms: {', '.join(platforms)}")
        caps.append(
            "Whiz MCP server: read tools (whiz_status, whiz_audit_self, "
            "whiz_emit_event) + request tools (whiz_request_mount, "
            "whiz_request_extend) — requests need host approval per D-165"
        )
        if self._credential_sources:
            # Covers both platforms (D-89) and secrets (D-162) — same dict.
            host_env_creds = [
                name for name, src in self._credential_sources.items() if src == "host-env"
            ]
            if host_env_creds:
                caps.append(
                    "WARNING: credentials for "
                    f"{', '.join(host_env_creds)} came from host env "
                    "(OneCLI fallback per D-134)"
                )
        return caps

    def mcp_env(self, session_id: str) -> dict[str, str]:
        # Per D-156: the Whiz MCP server runs in-cell, reading state from
        # mounted paths and writing agent-emitted events to a per-session
        # file (merged into the host audit log at session_end). Adapter
        # tells the cell where to find each path via env vars; core mounts
        # the host paths into the cell at the conventional /run/whiz/
        # locations (Stage 9 M5).
        return {
            ENV_SNAPSHOT_PATH: _IN_CELL_SNAPSHOT_PATH,
            ENV_AUDIT_LOG_PATH: _IN_CELL_AUDIT_LOG_PATH,
            ENV_EVENT_LOG_PATH: _IN_CELL_EVENT_LOG_PATH,
            ENV_REQUEST_DIR: _IN_CELL_REQUEST_DIR,
            ENV_SESSION_ID: session_id,
        }

    def container_mounts(self) -> list[ContainerMount]:
        # Stage 8 M6 / D-79: mount the host hermes_home into the cell at
        # the conventional in-cell HERMES_HOME path. Without this mount the
        # cell's Hermes process has no profile, so memories/skills/state
        # would be ephemeral with the container.
        #
        # Auto-create the host dir if missing. The bundled `hermes-cell`
        # harness declares `~/.hermes-whizzard-cell`; on the first launch
        # that path won't exist. Requiring a separate `init` verb is
        # friction the MVP doesn't need — the dir is empty until Hermes
        # populates it.
        #
        # uid_parity=True per D-56: gateway.lock and state writes need to
        # land with the host UID on raw Linux. On macOS Docker Desktop
        # the translation is transparent, but the parity wiring is the
        # same code path.
        hermes_home = _resolve_hermes_home(self.config)
        if hermes_home is None:
            return []
        hermes_home.mkdir(parents=True, exist_ok=True)
        return [
            ContainerMount(
                host_path=hermes_home,
                container_path=_IN_CELL_HERMES_HOME,
                mode="rw",
                uid_parity=True,
            )
        ]

    def preflight(self) -> PreflightResult:
        # D-87: refuse to launch when a live gateway already holds the lock
        # on this profile. Stale locks (pid not alive) are cleared and the
        # launch proceeds. Missing HERMES_HOME → no lock to check; let
        # downstream code surface that configuration gap if it matters.
        hermes_home = _resolve_hermes_home(self.config)
        if hermes_home is None:
            return PreflightResult(ok=True)

        lock = _read_gateway_lock(hermes_home)
        if lock is None:
            return PreflightResult(ok=True)

        pid = lock.get("pid")
        if not isinstance(pid, int):
            return PreflightResult(ok=True)

        if _is_pid_alive(pid):
            return PreflightResult(
                ok=False,
                reason=(
                    f"Hermes gateway already running on this profile "
                    f"(pid {pid}, HERMES_HOME={hermes_home}). "
                    f"Stop the running gateway, or create a sibling profile "
                    f"via `whiz hermes profile create <name> --clone-from default`."
                ),
            )

        # Stale lock — best-effort cleanup so we don't re-announce next launch.
        with contextlib.suppress(OSError):
            (hermes_home / _GATEWAY_LOCK_FILENAME).unlink()
        return PreflightResult(
            ok=True,
            cleanup_note=f"Cleared stale gateway.lock (pid {pid} no longer alive).",
        )


# Sanity check the Protocol contract at import time.
_: HarnessAdapter = HermesAdapter()
