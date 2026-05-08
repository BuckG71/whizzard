"""Profile and config resolution.

Stage 1 ships hardcoded profiles. Stage 3 will replace this with JSON-driven
loading from ~/.warlock/config/profiles.json.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


WARLOCK_HOME = Path(os.environ.get("WARLOCK_HOME", Path.home() / ".warlock"))
CONFIG_DIR = WARLOCK_HOME / "config"
LOGS_DIR = WARLOCK_HOME / "logs"
STATE_DIR = WARLOCK_HOME / "state"


@dataclass(frozen=True)
class Profile:
    name: str
    network_enabled: bool
    duration_seconds: int | None  # None = unlimited
    allow_broad_mount: bool = False
    description: str = ""


# Hardcoded for Stage 1. JSON-driven in Stage 3.
_BUILTIN_PROFILES: dict[str, Profile] = {
    "safe": Profile(
        name="safe",
        network_enabled=False,
        duration_seconds=30 * 60,
        description="Most restrictive. Network off, no mounts by default.",
    ),
    "default": Profile(
        name="default",
        network_enabled=True,
        duration_seconds=None,  # unlimited per design decision
        description="SAFE-NET baseline. Network on, mounts opt-in. Always-on.",
    ),
    "build": Profile(
        name="build",
        network_enabled=True,
        duration_seconds=2 * 60 * 60,
        description="Development work. Network on, rw mounts allowed.",
    ),
    "power": Profile(
        name="power",
        network_enabled=True,
        duration_seconds=60 * 60,
        allow_broad_mount=True,
        description="Capability-heavy. Shorter duration intentional.",
    ),
    "quarantine": Profile(
        name="quarantine",
        network_enabled=False,
        duration_seconds=30 * 60,
        description="Untrusted execution. Network off, ro mounts only.",
    ),
}


def get_profile(name: str) -> Profile:
    if name not in _BUILTIN_PROFILES:
        raise KeyError(
            f"Unknown profile: {name!r}. "
            f"Available: {', '.join(sorted(_BUILTIN_PROFILES))}"
        )
    return _BUILTIN_PROFILES[name]


def list_profiles() -> list[Profile]:
    return list(_BUILTIN_PROFILES.values())


def ensure_warlock_home() -> None:
    """Create ~/.warlock/ scaffold on first run."""
    for d in (WARLOCK_HOME, CONFIG_DIR, LOGS_DIR, STATE_DIR):
        d.mkdir(parents=True, exist_ok=True)
