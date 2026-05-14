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

import json
import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from whizzard.adapters.base import (
    HarnessAdapter,
    PreflightResult,
    WrapUpResult,
    WrapUpStatus,
)


_DEFAULT_START_COMMAND: list[str] = ["hermes", "gateway", "run"]
_GATEWAY_LOCK_FILENAME = "gateway.lock"


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
        if n in _CLONE_EXCLUDE_NAMES or n in _CLONE_EXCLUDE_DIRS:
            skipped.append(n)
        elif n.endswith(_CLONE_EXCLUDE_SUFFIXES):
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


# --- OneCLI credential plumbing (D-89, D-134) ------------------------------

# Hermes convention (per hermes_research.md L17): each platform's credential
# is consumed from an env var named `<PLATFORM>_BOT_TOKEN`. OneCLI secret
# names use the same string — one identifier across both surfaces.
_ONECLI_TIMEOUT_SECONDS = 30


class OneCLINotInstalledError(Exception):
    """`onecli` is not on PATH. The Hermes adapter requires it for D-134."""


class OneCLISecretMissingError(Exception):
    """OneCLI returned non-zero fetching a secret — usually not-registered."""


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
        return json.loads(lock_path.read_text())
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


def _fetch_secret_via_onecli(name: str) -> str:
    """Fetch `name` from OneCLI's vault. Raises on missing-binary or non-zero.

    Tests monkeypatch this function (or `subprocess.run`) to avoid invoking
    a real OneCLI install.
    """
    try:
        result = subprocess.run(
            ["onecli", "secrets", "get", name],
            capture_output=True,
            text=True,
            timeout=_ONECLI_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError as e:
        raise OneCLINotInstalledError(
            "`onecli` not found on PATH. The Hermes adapter requires OneCLI "
            "for credential injection (per D-134). Install OneCLI and retry."
        ) from e

    if result.returncode != 0:
        raise OneCLISecretMissingError(
            f"OneCLI failed to fetch secret {name!r} "
            f"(exit code {result.returncode}). "
            f"stderr: {result.stderr.strip() or '(empty)'}. "
            f"Register via: onecli secrets create {name}"
        )

    return result.stdout.rstrip("\n")


@dataclass
class HermesAdapter:
    """Adapter for the Hermes agent harness.

    Gateway mode is the default invocation (D-88); interactive mode is opted
    into via harness config or the `--interactive` CLI flag (handled in the
    `whiz hermes` subcommand surface, not here).
    """

    name: str = "hermes"
    config: dict = field(default_factory=dict)

    def start_command(self) -> list[str]:
        cmd = self.config.get("start_command")
        if cmd is None:
            return list(_DEFAULT_START_COMMAND)
        if isinstance(cmd, list):
            return list(cmd)
        return shlex.split(cmd)

    def container_env(self) -> dict[str, str]:
        # Platforms come from `harnesses.json["platforms"]` (D-89 amended).
        # Each platform's credential is fetched on-demand from OneCLI (D-134)
        # — no long-lived host env vars. Non-platform `env` from harness
        # config is passed through alongside.
        env: dict[str, str] = {}
        for platform in self.config.get("platforms", []) or []:
            var = _env_var_for_platform(platform)
            env[var] = _fetch_secret_via_onecli(var)
        extra = self.config.get("env", {}) or {}
        for k, v in extra.items():
            env[str(k)] = str(v)
        return env

    def working_dir(self) -> str | None:
        wd = self.config.get("working_dir")
        return wd if wd else None

    def wrap_up(self, container_id: str, grace_seconds: int) -> WrapUpResult:
        # Real implementation lands in milestone 6: `docker exec <id> /quit`
        # with grace_seconds bound. Until then, calling wrap_up fails loudly
        # rather than silently returning NO_OP, which would misrepresent
        # Hermes (unlike generic shell, Hermes has a real wrap-up channel).
        raise NotImplementedError(
            "HermesAdapter.wrap_up is not yet implemented "
            "(Stage 8 build plan milestone 6)"
        )

    def health_check_command(self) -> list[str] | None:
        return None

    def active_capabilities(self) -> list[str]:
        # Skeleton: returns []. A later milestone fills this with the
        # declared platform list plus the approval-mode warning string (D-90).
        return []

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
        try:
            (hermes_home / _GATEWAY_LOCK_FILENAME).unlink()
        except OSError:
            pass
        return PreflightResult(
            ok=True,
            cleanup_note=f"Cleared stale gateway.lock (pid {pid} no longer alive).",
        )


# Sanity check the Protocol contract at import time.
_: HarnessAdapter = HermesAdapter()
