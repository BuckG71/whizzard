"""Generic shell adapter.

The simplest possible adapter: launches an interactive shell inside the
container, no harness-specific behavior. Used as the default when the
user doesn't specify a harness, and as a reference implementation for
the adapter interface.

Generic shell has no native wrap-up mechanism — bash exits cleanly on
SIGTERM, so wrap_up() is a no-op. The Hermes adapter (Stage 8) is the
first one with a meaningful wrap_up implementation (sends `/quit`).
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field

from whizzard.adapters.base import (
    HarnessAdapter,
    WrapUpResult,
    WrapUpStatus,
)


@dataclass
class GenericShellAdapter:
    """Adapter for a plain shell — bash by default, configurable per harness.

    Reads start_command, env, and working_dir from harness config.
    Implements WrapUpStatus.NO_OP because bash has nothing to flush.
    """

    name: str = "generic"
    config: dict = field(default_factory=dict)

    def start_command(self) -> list[str]:
        cmd = self.config.get("start_command", "/bin/bash")
        if isinstance(cmd, list):
            return list(cmd)
        # Single string: split with shlex so something like "bash -l" works.
        return shlex.split(cmd)

    def container_env(self) -> dict[str, str]:
        env = self.config.get("env", {}) or {}
        return {str(k): str(v) for k, v in env.items()}

    def working_dir(self) -> str | None:
        wd = self.config.get("working_dir")
        return wd if wd else None

    def wrap_up(self, container_id: str, grace_seconds: int) -> WrapUpResult:
        # Generic shell has no native command channel; SIGTERM is the
        # cleanest available shutdown for bash.
        return WrapUpResult(
            status=WrapUpStatus.NO_OP,
            detail="generic shell has no wrap-up mechanism; SIGTERM will be sent",
        )

    def health_check_command(self) -> list[str] | None:
        # Bash is "ready" the moment the container is running; no probe.
        return None

    def active_capabilities(self) -> list[str]:
        return []


# Sanity check the Protocol contract at import time.
_: HarnessAdapter = GenericShellAdapter()
