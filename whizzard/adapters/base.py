"""Adapter interface for harness integration.

The adapter is the seam between Whizzard (which provides containment and
policy enforcement) and Whizzard (which orchestrates an agent harness
inside the contained execution cell). Whizzard core stays harness-neutral
per architecture.md; harness-specific behavior lives behind this interface.

Stage 7 lands the interface and the trivial GenericShellAdapter.
Stage 8 adds the Hermes adapter using the same contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from whizzard._platform import docker_host_path


@dataclass(frozen=True)
class ContainerMount:
    """A host→container mount the adapter declares for its own state needs.

    Distinct from the user-named mount registry (`whizzard.mounts.Mount`):
    these are harness-driven mounts that the user doesn't reason about
    individually (e.g., Hermes's profile directory needed at HERMES_HOME).
    Wired by core's `docker_cmd` at launch.

    `uid_parity=True` (D-56): the container UID is overridden to match the
    host UID so writes through this mount land owned by the host user on
    raw Linux. Docker's `--user` flag is container-wide, so any uid_parity
    request applies to the whole container — but only the harness mount
    needs it to function, hence the per-mount flag.
    """
    host_path: Path
    container_path: str
    mode: Literal["ro", "rw"] = "rw"
    uid_parity: bool = False

    def docker_volume_arg(self) -> str:
        return f"{docker_host_path(self.host_path)}:{self.container_path}:{self.mode}"


class WrapUpStatus(Enum):
    """Outcome of an adapter's wrap_up() call."""
    SUCCESS = "success"     # harness acknowledged shutdown within grace
    TIMEOUT = "timeout"     # grace period expired without acknowledgment
    NO_OP = "no_op"         # adapter has no native wrap-up mechanism
    ERROR = "error"         # send failed for some other reason


@dataclass(frozen=True)
class WrapUpResult:
    status: WrapUpStatus
    detail: str = ""


@dataclass(frozen=True)
class PreflightResult:
    """Outcome of an adapter's pre-launch checks.

    `ok=True` means launch may proceed. `reason` is the human-readable
    explanation when blocking. `cleanup_note` is set when the adapter
    took a recovery action during preflight (e.g., cleared a stale lock)
    and the launch is proceeding.
    """
    ok: bool
    reason: str = ""
    cleanup_note: str = ""


@runtime_checkable
class HarnessAdapter(Protocol):
    """Contract for harness adapters.

    Implementations describe how to launch a specific harness inside the
    contained execution cell, and how to gracefully wrap it up before
    container termination.

    Whizzard decides WHAT capabilities the cell has (mounts, network,
    duration). The adapter decides WHAT runs inside the cell.
    """

    name: str

    # The container image this harness needs (its binary must live there).
    # The launch path uses it when no explicit `--image` override is passed,
    # so selecting a harness selects the right image (e.g. Hermes → the
    # Hermes image) instead of silently keeping the base image.
    default_image: str

    def start_command(self) -> list[str]:
        """Argv to run inside the container as the user-facing entrypoint.

        For generic shell, this is `["/bin/bash"]`. For Hermes, it would
        be the Hermes CLI invocation that drops the user into the
        Hermes interactive session.
        """
        ...

    def container_env(self) -> dict[str, str]:
        """Environment variables to inject into the container.

        Whizzard applies these on top of its own baseline. The adapter
        is responsible for any harness-specific config injection here
        (e.g., Hermes might set HERMES_HOME or override terminal.backend).
        """
        ...

    def credential_env_keys(self) -> set[str]:
        """Names of env vars in ``container_env()`` that hold secret
        values. Whizzard scrubs the matching ``-e KEY=VALUE`` pairs
        from the argv recorded in the audit log so secrets don't
        persist in plaintext on disk (S20.5 / D-134).

        Adapters with no secrets (generic shell) return ``set()``.
        Adapters that resolve credentials (Hermes) return the set of
        env-var names whose values came from a credential source.
        """
        ...

    def working_dir(self) -> str | None:
        """Container working directory, or None for the image default."""
        ...

    def wrap_up(self, container_id: str, grace_seconds: int) -> WrapUpResult:
        """Send the harness's native graceful-shutdown signal.

        Called by Whizzard before SIGTERM when a session is about to end
        (duration expiry, user-initiated stop, safety termination).
        Bounded by grace_seconds; if the harness doesn't acknowledge in
        that window, the caller proceeds to SIGTERM regardless.

        Implementations should NOT sleep beyond grace_seconds. Return
        promptly with TIMEOUT if the harness hasn't responded.

        For adapters with no native wrap-up mechanism (generic shell),
        return WrapUpResult(NO_OP, ...).
        """
        ...

    def health_check_command(self) -> list[str] | None:
        """Argv to verify the harness is ready, or None if not applicable.

        Run on the host (via `docker exec` or equivalent) by the orchestrator
        after launch. Adapters that don't need a health check return None.
        """
        ...

    def active_capabilities(self) -> list[str]:
        """Human-readable capability strings for the pre-launch banner.

        Whizzard prints these before container start so the user sees what
        the harness is about to do — connected platforms, approval mode,
        etc. (D-89, D-90). Content is adapter-specific; the surface is
        generic. Adapters with no capability surface (generic shell) return
        an empty list.
        """
        ...

    def preflight(self) -> PreflightResult:
        """Run harness-specific pre-launch checks.

        Called by Whizzard core before container start. Adapters return
        a PreflightResult; if `ok` is False, core blocks the launch and
        surfaces `reason` to the user. If `ok` is True with a non-empty
        `cleanup_note`, core prints it so the user sees what the adapter
        recovered from before proceeding (e.g., a stale lock that was
        cleared per D-87).
        """
        ...

    def mcp_env(self, session_id: str) -> dict[str, str]:
        """Env vars for the in-cell Whiz MCP server (Stage 9, D-156).

        Called by Whizzard core at launch with the session id. Adapters
        that want the Whiz MCP server running inside their cell return
        env vars naming the in-cell paths the server reads (snapshot,
        audit log, event file) plus the session id. Adapters that don't
        use MCP return an empty dict; core combines this with
        `container_env()` for the actual `-e` flags.
        """
        ...

    def container_mounts(self) -> list[ContainerMount]:
        """Harness-required host→container mounts (Stage 8 M6).

        Distinct from the user-named mount registry: these are state dirs
        the harness itself needs (e.g., Hermes profile → HERMES_HOME).
        `GenericShellAdapter` returns `[]`; `HermesAdapter` returns one
        entry mapping `hermes_home` from the harness config to the
        in-cell HERMES_HOME path. Core wires the `-v` flags at launch
        and applies UID parity for any entry with `uid_parity=True` (D-56).
        """
        ...
