"""Hermes adapter.

Bridges Whizzard's contained execution cell to a Hermes installation per the
Stage 8 design decisions (D-86 through D-90). Per D-153, harness-specific
identifiers — config.yaml, gateway.lock, HERMES_HOME, platform tokens — live
inside this module and the `whiz hermes` subcommand surface. Core stays neutral.

The adapter owns:
  - Profile creation (D-86) with the D-80 auth.json exclusion list.
  - Credential delivery via the shared `_credentials` utility (D-91, D-134).
  - HERMES_HOME mount (D-79, D-56 uid_parity).
  - Mount-time auth.json check (D-80 enforcement at launch, not just at
    profile creation — closes the Chunk C F-C-01 finding).
  - `gateway.lock` preflight (D-87) and graceful `wrap_up` via `docker stop`
    (D-29 / D-30 SIGTERM contract, D-88 supersedes the original `/quit`).
"""

from __future__ import annotations

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
# where $HOME is the cell user's home dir from whizzard/_dockerfiles/Dockerfile.
# Mounting
# the host hermes_home here lets in-cell Hermes find its profile under its
# default lookup, no flag plumbing required.
_IN_CELL_HERMES_HOME = "/home/whizzard/.hermes"


# --- Profile creation (D-86) -----------------------------------------------

# Files/dirs excluded when cloning a Hermes profile:
#   - auth.json + auth.lock: D-80 (credentials never enter a derived profile)
#   - .env: defense-in-depth, additional secret material
#   - *.db, gateway.*, sessions/, logs/: per-instance runtime state
#   - .git, hermes-agent: irrelevant install/repo metadata
#
# F-C-02: matched case-insensitively (lowercased at lookup) because macOS's
# default APFS is case-insensitive — a source file named `Auth.json` would
# slip past an exact-match check and get copied verbatim.
_CLONE_EXCLUDE_NAMES: set[str] = {
    "auth.json",
    "auth.lock",
    ".env",
    ".ds_store",
    "thumbs.db",
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

# Substrings matched case-insensitively against any file name at any depth
# inside a candidate HERMES_HOME directory. Any match → refuse to mount
# (F-C-01). Distinct from `_CLONE_EXCLUDE_NAMES` because (a) it must catch
# the file regardless of profile-creation lineage and (b) `auth.lock` is
# included so a half-written auth.json (file briefly absent, lock present)
# also fails closed.
_MOUNT_REFUSE_NAMES: frozenset[str] = frozenset({"auth.json", "auth.lock"})
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


class HermesAuthJsonPresentError(Exception):
    """auth.json (or auth.lock) found inside the candidate HERMES_HOME.

    Raised at mount time, not just profile-creation time, so that any path
    leading to an auth-bearing profile (manual copy, cell write-back, user
    pointing hermes_home at the real ~/.hermes) fails closed. D-80 — the
    project's #1 security invariant — must never be bypassable (F-C-01).
    """


class HermesHomeRequiredError(Exception):
    """hermes_home not configured for an agent-type harness, and the user
    has not opted into ephemeral state via --allow-ephemeral.

    F-C-04: agent harness without persistent state is almost never what
    the user wants — memories, skills, gateway state all disappear on
    container exit. Default is fail-loud; --allow-ephemeral is the
    documented escape hatch for the rare opposite case.
    """


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
    """shutil.copytree `ignore=` callable — names in `src` to skip.

    F-C-02: name matches are case-insensitive so macOS APFS variants
    (`Auth.json`, `AUTH.JSON`) are also excluded.
    """
    skipped: list[str] = []
    for n in names:
        lower = n.lower()
        if (
            lower in _CLONE_EXCLUDE_NAMES
            or lower in _CLONE_EXCLUDE_DIRS
            or lower.endswith(_CLONE_EXCLUDE_SUFFIXES)
        ):
            skipped.append(n)
    return skipped


def _check_no_auth_json(profile_dir: Path) -> None:
    """Walk profile_dir; raise HermesAuthJsonPresentError on auth.json/lock.

    Closes F-C-01. Called from `container_mounts` before declaring the
    HERMES_HOME mount, so every launch path (manual copy, write-back from
    cell, user pointing at real ~/.hermes, fresh dir seeded outside the
    profile-create flow) fails closed if a credential file is present.

    Matches case-insensitively and at any depth — Hermes nests its
    configuration so the file could legitimately live under `default/` or
    a numeric subdir. We refuse them all.

    F-A5 (catch-up review pass 2, 2026-05-24): the original implementation
    used ``Path.rglob`` which does NOT descend into directory symlinks AND
    yields symlinks-to-files by the symlink's own name (not the target's).
    Both gaps could bypass the D-80 check:

      (a) Symlink to a directory containing auth.json — rglob skips →
          MISS. Docker bind-mounts follow the symlink at access time
          inside the cell, exposing the target.
      (b) Symlink named ``credentials`` that points at ``~/.hermes/auth.json``
          — rglob yields it with ``entry.name`` == "credentials"; the
          lowercase-name check is against the symlink name, not the
          target. MISS.

    Fix: refuse to launch if ANY symlink lives inside ``profile_dir``.
    Profiles created via the standard ``whiz hermes profile create`` flow
    have no symlinks (``shutil.copytree(symlinks=True)`` preserves source
    symlinks but the F-C-02/F-C-03 fixes mean no auth-bearing symlinks
    can survive the clone filter). A maintainer who needs a legitimate
    symlink can be loud about it — the error is explicit and the
    rationale here documents the trade.
    """
    if not profile_dir.exists():
        return
    # Manual walk so we can detect symlinks ourselves; rglob's default
    # behavior (don't follow directory symlinks, skip them silently)
    # is what created the bypass.
    stack = [profile_dir]
    while stack:
        current = stack.pop()
        try:
            children = list(current.iterdir())
        except OSError:
            continue
        for entry in children:
            try:
                is_symlink = entry.is_symlink()
            except OSError:
                # Broken inode; treat as suspect and refuse.
                is_symlink = True
            if is_symlink:
                raise HermesAuthJsonPresentError(
                    f"Refusing to mount {profile_dir} into the cell: found "
                    f"symlink at {entry.relative_to(profile_dir)} (D-80 "
                    "forbids mounting symlinks inside HERMES_HOME because a "
                    "symlink may point at auth.json / auth.lock with a "
                    "different name, or at a directory containing them — "
                    "in either case the bind mount would expose the target "
                    "to the cell. Replace the symlink with the real "
                    "content, or remove it."
                )
            try:
                if entry.is_file():
                    if entry.name.lower() in _MOUNT_REFUSE_NAMES:
                        raise HermesAuthJsonPresentError(
                            f"Refusing to mount {profile_dir} into the "
                            f"cell: found {entry.relative_to(profile_dir)} "
                            "(D-80 forbids mounting auth.json / auth.lock "
                            "— credentials must reach the cell via env "
                            "vars per D-134, never via the mounted "
                            "profile). Remove the file from the host "
                            "profile, or point hermes_home at a profile "
                            "created via `whiz hermes profile create`."
                        )
                elif entry.is_dir():
                    stack.append(entry)
            except OSError:
                continue


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

    # F-C-03: symlinks=True preserves symlinks in the destination instead of
    # following them. The destination then carries broken symlinks (the host
    # paths they point at are not visible inside the cell), which surfaces
    # as a visible launch failure — rather than silently copying credential
    # content into the new profile under a non-excluded symlink name.
    shutil.copytree(source, target, ignore=_clone_ignore, symlinks=True)
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
    # F-C-04 escape hatch. CLI sets this True when the user passed
    # `--allow-ephemeral`, opting into running an agent harness without a
    # persistent HERMES_HOME (memories/skills/gateway state ephemeral with
    # the container). Default fails loud — almost never what the user wants.
    allow_ephemeral: bool = False

    def start_command(self) -> list[str]:
        cmd = self.config.get("start_command")
        if cmd is None:
            return list(_DEFAULT_START_COMMAND)
        if isinstance(cmd, list):
            return list(cmd)
        return shlex.split(cmd)

    def _populate_credential_sources(self) -> dict[str, str]:
        """Fetch all platform + secret credentials and record their source.

        F-C-07: `_credential_sources` used to be a side effect of
        `container_env`, making `active_capabilities()` order-dependent —
        a pre-launch capability banner would silently drop the D-134
        host-env-fallback warning. Now both methods call this helper, and
        the first call populates the cache (idempotent within an adapter
        instance because secret fetching is deterministic).
        """
        if self._credential_sources:
            return self._credential_sources
        env: dict[str, str] = {}
        for platform in self.config.get("platforms", []) or []:
            var = _env_var_for_platform(platform)
            result = fetch_secret(var)
            env[var] = result.value
            # S20.7 bug-fix: key on the env-var NAME (the same string
            # that lands in ``-e KEY=VALUE`` argv), not the platform
            # name. credential_env_keys() returns this dict's keys to
            # the audit-log scrubber; a mismatch (e.g. {"discord"} vs
            # argv "DISCORD_BOT_TOKEN") silently bypasses the scrub.
            self._credential_sources[var] = result.source
        for secret_name in self.config.get("secrets", []) or []:
            result = fetch_secret(secret_name)
            env[secret_name] = result.value
            self._credential_sources[secret_name] = result.source
        # Stash the resolved env on the instance so container_env can read
        # it without re-fetching. Not part of the public Protocol.
        self._cached_credential_env = env
        return self._credential_sources

    def container_env(self) -> dict[str, str]:
        hermes_home = _resolve_hermes_home(self.config)
        # F-C-04: the hermes_home-required check lives in preflight(), so
        # by the time we get here either hermes_home is set OR
        # --allow-ephemeral was opted into. We don't re-check here because
        # _perform_launch enforces preflight before any adapter env work.
        # Platforms come from `harnesses.json["platforms"]` (D-89 amended).
        # Each platform's credential is fetched via the shared utility
        # (Stage 12): OneCLI first, host env as fallback per D-134's
        # "OneCLI not installed" failure-mode note.
        self._credential_sources.clear()
        self._populate_credential_sources()
        env = dict(getattr(self, "_cached_credential_env", {}))
        # HERMES_HOME points at the in-cell mount target where the host
        # profile is mounted (Stage 8 M6, D-79). Only set when hermes_home
        # is configured; --allow-ephemeral leaves Hermes to discover its
        # default (ephemeral tmpfs home).
        if hermes_home is not None:
            env["HERMES_HOME"] = _IN_CELL_HERMES_HOME
        extra = self.config.get("env", {}) or {}
        for k, v in extra.items():
            env[str(k)] = str(v)
        return env

    def credential_env_keys(self) -> set[str]:
        """S20.5 / D-134: env keys whose values were resolved from a
        credential source (OneCLI or host-env fallback). Whizzard scrubs
        these from the argv recorded in the audit log so secrets don't
        persist in plaintext on disk."""
        # _credential_sources is populated by _populate_credential_sources()
        # which container_env() / active_capabilities() / preflight() all
        # trigger before launch. By the time the audit-log writer asks,
        # the set is canonical for this session.
        return set(self._credential_sources.keys())

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
        # F-C-05: shorter timeout so the inspect probe doesn't materially
        # extend the documented grace window (was 5s; now 2s — plenty for a
        # local-daemon metadata read, much smaller tail when Docker Desktop
        # is under load).
        try:
            inspect_result = subprocess.run(
                [
                    "docker", "inspect",
                    "--format", "{{.State.ExitCode}}",
                    container_id,
                ],
                capture_output=True,
                text=True,
                timeout=2,
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
        # credential-source breakdown, and Whiz MCP server availability.
        # Approval-mode warning per D-90 is added by a later build step
        # (it requires reading `approvals.mode` from `config.yaml`).
        #
        # F-C-07: this method now populates `_credential_sources` itself
        # if it hasn't been computed yet, so a pre-launch banner caller
        # doesn't silently miss the D-134 host-env-fallback warning. The
        # populate helper is idempotent — `container_env` reuses the same
        # cache on its turn.
        caps: list[str] = []
        platforms = self.config.get("platforms", []) or []
        if platforms:
            caps.append(f"platforms: {', '.join(platforms)}")
        caps.append(
            "Whiz MCP server: read tools (whiz_status, whiz_audit_self, "
            "whiz_emit_event) + request tools (whiz_request_mount, "
            "whiz_request_extend) — requests need host approval per D-165"
        )
        self._populate_credential_sources()
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
        # F-C-04: agent-type Hermes without hermes_home raises in
        # container_env(); by the time we get here either hermes_home is
        # set OR --allow-ephemeral was opted into. Empty list = ephemeral.
        #
        # F-C-01: before declaring the mount, walk the profile and refuse
        # if auth.json / auth.lock is present anywhere. D-80 says these
        # never enter the cell — and the only enforcement before this fix
        # lived in `create_profile`'s clone-ignore filter, which doesn't
        # cover (a) user pointing hermes_home at the real ~/.hermes,
        # (b) manual copy into the cell profile, (c) the cell's Hermes
        # writing an auth.json back via the rw mount, (d) seeding the dir
        # outside `whiz hermes profile create`. The walk catches all four.
        #
        # uid_parity=True per D-56: gateway.lock and state writes need to
        # land with the host UID on raw Linux. On macOS Docker Desktop
        # the translation is transparent, but the parity wiring is the
        # same code path.
        hermes_home = _resolve_hermes_home(self.config)
        if hermes_home is None:
            return []
        hermes_home.mkdir(parents=True, exist_ok=True)
        _check_no_auth_json(hermes_home)
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
        # launch proceeds.
        #
        # F-C-04 / F-C-10: preflight is also where the hermes_home-required
        # check lives (fail loud for agent harness with no persistence)
        # and where the D-80 auth.json mount-time check (F-C-01) is
        # surfaced — both bubble through PreflightResult.reason so the
        # CLI can print a single clean refusal.
        hermes_home = _resolve_hermes_home(self.config)
        if hermes_home is None:
            if self.allow_ephemeral:
                return PreflightResult(ok=True)
            return PreflightResult(
                ok=False,
                reason=(
                    "Hermes harness has no hermes_home configured. Without "
                    "it, memories, skills, and gateway state are ephemeral "
                    "with the container — almost never what you want.\n\n"
                    "Options:\n"
                    "  • Add `--allow-ephemeral` to this launch (opt-in "
                    "escape hatch for the rare opposite case).\n"
                    "  • Run `whiz hermes profile create <name>` to make a "
                    "Hermes profile, then set `hermes_home` to its path in "
                    "`~/.whizzard/config/harnesses.json`.\n"
                    "  • Edit `~/.whizzard/config/harnesses.json` and set "
                    "`hermes_home` directly."
                ),
            )

        # F-C-01: D-80 mount-time auth.json check. Walks the candidate
        # HERMES_HOME for any case-variant of auth.json / auth.lock and
        # refuses launch if any is found. Failure-closed by design.
        try:
            _check_no_auth_json(hermes_home)
        except HermesAuthJsonPresentError as e:
            return PreflightResult(ok=False, reason=str(e))

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
        # F-C-08: if the unlink fails (read-only fs, owner mismatch on the
        # lock file, etc.), the message must reflect reality — saying
        # "cleared" when the lock is still there mis-leads the next launch
        # into the same probe → same misleading message cycle.
        lock_path = hermes_home / _GATEWAY_LOCK_FILENAME
        try:
            lock_path.unlink()
        except FileNotFoundError:
            # Race: lock disappeared between read and unlink. Fine.
            cleanup_note = f"Cleared stale gateway.lock (pid {pid} no longer alive)."
        except OSError as e:
            cleanup_note = (
                f"Stale gateway.lock (pid {pid} no longer alive) but could "
                f"not unlink {lock_path}: {e}. The next launch will re-probe; "
                f"resolve manually if this persists."
            )
        else:
            cleanup_note = f"Cleared stale gateway.lock (pid {pid} no longer alive)."
        return PreflightResult(ok=True, cleanup_note=cleanup_note)


# Protocol-conformance check is enforced statically by mypy via the
# HarnessAdapter signature declared on `build_adapter` and the registry —
# no runtime allocation needed (F-C-09).
