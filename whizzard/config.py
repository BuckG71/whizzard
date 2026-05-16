"""Profile and config resolution.

Stage 3: profiles are loaded from ~/.whizzard/config/profiles.json when
present, falling back to bundled defaults otherwise. The bundled defaults
match the Stage 1 set; users can copy `config/profiles.json.example` from
the repo into ~/.whizzard/config/profiles.json to start customizing.

Schema for profiles.json:

    {
      "schema_version": 1,
      "profiles": {
        "<name>": {
          "network_enabled": true | false,
          "duration_seconds": <int> | null,   # null = unlimited
          "allow_broad_mount": true | false,  # default false
          "description": "..."                 # default ""
        },
        ...
      }
    }
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


WHIZZARD_HOME = Path(os.environ.get("WHIZZARD_HOME", Path.home() / ".whizzard"))
CONFIG_DIR = WHIZZARD_HOME / "config"
LOGS_DIR = WHIZZARD_HOME / "logs"
STATE_DIR = WHIZZARD_HOME / "state"
PROFILES_FILE = CONFIG_DIR / "profiles.json"


@dataclass(frozen=True)
class Profile:
    name: str
    network_enabled: bool
    duration_seconds: int | None  # None = unlimited
    allow_broad_mount: bool = False
    description: str = ""


class ProfileConfigError(Exception):
    pass


# Bundled defaults. Used when the user has no profiles.json or as the
# template that ships in config/profiles.json.example.
_DEFAULT_PROFILES: dict[str, Profile] = {
    "safe": Profile(
        name="safe",
        network_enabled=False,
        duration_seconds=30 * 60,
        description="Most restrictive. Network off, no mounts by default.",
    ),
    "default": Profile(
        name="default",
        network_enabled=True,
        duration_seconds=None,  # unlimited — productive baseline
        allow_broad_mount=True,  # D-157: enables broad-mount overrides when
                                 # explicitly authorized at launch (CLI flag
                                 # or preset). Two-gate model preserved per
                                 # D-46. Supersedes D-38 on this field only.
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


def _parse_profile(name: str, spec: dict) -> Profile:
    """Validate and construct a Profile from a JSON dict entry."""
    if not isinstance(spec, dict):
        raise ProfileConfigError(f"profile {name!r}: spec must be an object")

    if "network_enabled" not in spec:
        raise ProfileConfigError(f"profile {name!r}: missing network_enabled")
    network_enabled = spec["network_enabled"]
    if not isinstance(network_enabled, bool):
        raise ProfileConfigError(
            f"profile {name!r}: network_enabled must be true/false"
        )

    if "duration_seconds" not in spec:
        raise ProfileConfigError(
            f"profile {name!r}: missing duration_seconds (use null for unlimited)"
        )
    duration_seconds = spec["duration_seconds"]
    if duration_seconds is not None:
        if not isinstance(duration_seconds, int) or isinstance(duration_seconds, bool):
            raise ProfileConfigError(
                f"profile {name!r}: duration_seconds must be an integer or null"
            )
        if duration_seconds <= 0:
            raise ProfileConfigError(
                f"profile {name!r}: duration_seconds must be positive (got {duration_seconds})"
            )

    allow_broad_mount = spec.get("allow_broad_mount", False)
    if not isinstance(allow_broad_mount, bool):
        raise ProfileConfigError(
            f"profile {name!r}: allow_broad_mount must be true/false"
        )

    description = spec.get("description", "")
    if not isinstance(description, str):
        raise ProfileConfigError(f"profile {name!r}: description must be a string")

    return Profile(
        name=name,
        network_enabled=network_enabled,
        duration_seconds=duration_seconds,
        allow_broad_mount=allow_broad_mount,
        description=description,
    )


def load_profiles(path: Path | None = None) -> dict[str, Profile]:
    """Load profiles from JSON, or return a copy of the bundled defaults.

    Returns a fresh dict so callers can mutate without affecting state.
    """
    target = path or PROFILES_FILE
    if not target.exists():
        return dict(_DEFAULT_PROFILES)

    try:
        data = json.loads(target.read_text())
    except json.JSONDecodeError as e:
        raise ProfileConfigError(f"invalid {target}: {e}") from e

    if not isinstance(data, dict):
        raise ProfileConfigError(f"{target}: top-level must be an object")
    profiles_data = data.get("profiles", {})
    if not isinstance(profiles_data, dict):
        raise ProfileConfigError(f"{target}: 'profiles' must be an object")
    if not profiles_data:
        raise ProfileConfigError(
            f"{target}: 'profiles' is empty — at least one profile is required"
        )

    result: dict[str, Profile] = {}
    for name, spec in profiles_data.items():
        result[name] = _parse_profile(name, spec)
    return result


def get_profile(name: str) -> Profile:
    profiles = load_profiles()
    if name not in profiles:
        raise KeyError(
            f"Unknown profile: {name!r}. "
            f"Available: {', '.join(sorted(profiles))}"
        )
    return profiles[name]


def list_profiles() -> list[Profile]:
    return list(load_profiles().values())


def default_profiles() -> dict[str, Profile]:
    """Return a copy of the bundled defaults — used by CLI seeding."""
    return dict(_DEFAULT_PROFILES)


def ensure_whizzard_home() -> None:
    """Create ~/.whizzard/ scaffold. Idempotent."""
    for d in (WHIZZARD_HOME, CONFIG_DIR, LOGS_DIR, STATE_DIR):
        d.mkdir(parents=True, exist_ok=True)
