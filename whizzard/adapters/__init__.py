"""Harness adapter registry and factory."""

from __future__ import annotations

from whizzard.adapters.base import (
    HarnessAdapter,
    WrapUpResult,
    WrapUpStatus,
)
from whizzard.adapters.generic import GenericShellAdapter
from whizzard.adapters.hermes import HermesAdapter


__all__ = [
    "HarnessAdapter",
    "WrapUpResult",
    "WrapUpStatus",
    "GenericShellAdapter",
    "HermesAdapter",
    "build_adapter",
]


class UnknownHarnessTypeError(Exception):
    pass


def build_adapter(name: str, config: dict) -> HarnessAdapter:
    """Construct an adapter for the named harness from its config dict.

    `type: "shell"` returns the generic shell adapter (Stage 7).
    `type: "agent"` returns the Hermes adapter (Stage 8). When future
    agent adapters land (OpenClaw, NanoClaw), a sub-discriminator will
    be needed; for MVP, agent-type maps to Hermes.
    """
    harness_type = config.get("type", "shell")

    if harness_type == "shell":
        return GenericShellAdapter(name=name, config=config)

    if harness_type == "agent":
        return HermesAdapter(name=name, config=config)

    raise UnknownHarnessTypeError(
        f"harness {name!r} has unknown type {harness_type!r}; "
        f"supported types: shell, agent"
    )
