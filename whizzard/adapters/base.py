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
from typing import Protocol, runtime_checkable


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
