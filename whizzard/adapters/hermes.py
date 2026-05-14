"""Hermes adapter.

Bridges Whizzard's contained execution cell to a Hermes installation per the
Stage 8 design decisions (D-86 through D-90). Per D-153, harness-specific
identifiers — config.yaml, gateway.lock, HERMES_HOME, platform tokens — live
inside this module and the `whiz hermes` subcommand surface. Core stays neutral.

This module currently lands as a skeleton (Action 1 of the Stage 8 build plan):
Protocol-shape implementations exist, but container_env() reading config.yaml,
the gateway.lock pre-launch check, and wrap_up() via `docker exec /quit` are
filled in by subsequent build-plan actions.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field

from whizzard.adapters.base import (
    HarnessAdapter,
    WrapUpResult,
    WrapUpStatus,
)


_DEFAULT_START_COMMAND: list[str] = ["hermes", "gateway", "run"]


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
        # Skeleton: passes through config-declared env only. Action 3 replaces
        # this with config.yaml reading + platform-token injection (D-89).
        env = self.config.get("env", {}) or {}
        return {str(k): str(v) for k, v in env.items()}

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
        # Skeleton: returns []. Action 3 fills this with the config.yaml-derived
        # platform list ("platforms: discord, slack") plus the approval-mode
        # warning string from D-90.
        return []


# Sanity check the Protocol contract at import time.
_: HarnessAdapter = HermesAdapter()
