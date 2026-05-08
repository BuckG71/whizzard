"""Harness adapter registry and factory."""

from __future__ import annotations

from whizzard.adapters.base import (
    HarnessAdapter,
    WrapUpResult,
    WrapUpStatus,
)
from whizzard.adapters.generic import GenericShellAdapter


__all__ = [
    "HarnessAdapter",
    "WrapUpResult",
    "WrapUpStatus",
    "GenericShellAdapter",
    "build_adapter",
]


class UnknownHarnessTypeError(Exception):
    pass


def build_adapter(name: str, config: dict) -> HarnessAdapter:
    """Construct an adapter for the named harness from its config dict.

    Stage 7 supports `type: "shell"`. Stage 8 will add `type: "agent"`
    for the Hermes adapter and beyond. Unknown types raise so the user
    sees a clear error rather than silently getting a generic shell.
    """
    harness_type = config.get("type", "shell")

    if harness_type == "shell":
        return GenericShellAdapter(name=name, config=config)

    if harness_type == "agent":
        raise UnknownHarnessTypeError(
            f"harness {name!r} has type 'agent' but no agent adapter is "
            f"implemented yet (lands in Stage 8 with the Hermes adapter)"
        )

    raise UnknownHarnessTypeError(
        f"harness {name!r} has unknown type {harness_type!r}; "
        f"supported types: shell, agent"
    )
