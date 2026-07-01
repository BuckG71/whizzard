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
          "duration_seconds": <int> | null,        # null = unlimited
          "idle_timeout_seconds": <int> | null,    # optional; null = no idle timeout
          "allow_broad_mount": true | false,       # default false
          "description": "..."                      # default ""
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


#: Valid network postures (D-184/D-187). "none" = --network none; "open" =
#: default bridge (full egress); "mediated" = cell reaches only the bar-C
#: credential-broker sidecar (model key only); "onecli" = cell egress routes
#: through the OneCLI gateway (all credentials injected host-side); "hybrid" =
#: both on one isolated net — the model call goes to the bar-C broker (which
#: handles subscription-OAuth's two headers) and everything else through
#: OneCLI, so no service/model credential lands in the cell. (The cell does
#: hold the gateway's own proxy-auth token in HTTP(S)_PROXY — an unavoidable
#: proxy-client capability scoped to driving the gateway; it is scrubbed from
#: the audit log and never exposes a raw provider secret.)
NETWORK_MODES = ("none", "open", "mediated", "onecli", "hybrid")


@dataclass(frozen=True)
class Profile:
    name: str
    network_enabled: bool
    duration_seconds: int | None  # None = unlimited
    allow_broad_mount: bool = False
    description: str = ""
    idle_timeout_seconds: int | None = None  # None = no idle timeout (Stage 15)
    #: None → derived from network_enabled (False→"none", True→"open") so the
    #: pre-existing boolean-only profiles keep their behavior. A mediated
    #: profile sets this explicitly to "mediated".
    network_mode: str | None = None

    def __post_init__(self) -> None:
        if self.network_mode is None:
            derived = "open" if self.network_enabled else "none"
            object.__setattr__(self, "network_mode", derived)


class ProfileConfigError(Exception):
    pass


SUPPORTED_SCHEMA_VERSION = 1


def validate_schema_version(
    data: dict, source: Path, error_cls: type[Exception]
) -> None:
    """Reject configs that declare an unsupported schema_version.

    Missing field is treated as v1 (the only version that has ever shipped),
    so older user configs keep working. A present-but-wrong value (e.g. a
    future v2 read by old code) raises with a clear message.
    """
    if "schema_version" not in data:
        return
    version = data["schema_version"]
    if version != SUPPORTED_SCHEMA_VERSION:
        raise error_cls(
            f"{source}: unsupported schema_version {version!r} "
            f"(this Whizzard build supports schema_version {SUPPORTED_SCHEMA_VERSION})"
        )


def validate_positive_int_or_none(
    value: object,
    *,
    field_label: str,
    error_cls: type[Exception],
) -> None:
    """Enforce 'positive int OR None' on a config value.

    Used for ``duration_seconds`` and ``idle_timeout_seconds`` in both the
    profile loader and the preset loader so the two surfaces share one rule
    (per F-A-01). ``bool`` is rejected because Python booleans are ints and
    silently slip through naive isinstance checks. ``None`` means
    "unlimited" / "no timeout" and is allowed.
    """
    if value is None:
        return
    if not isinstance(value, int) or isinstance(value, bool):
        raise error_cls(f"{field_label} must be an integer or null")
    if value <= 0:
        raise error_cls(f"{field_label} must be positive (got {value})")


# Bundled defaults. Used when the user has no profiles.json or as the
# template that ships in config/profiles.json.example.
_DEFAULT_PROFILES: dict[str, Profile] = {
    "safe": Profile(
        name="safe",
        network_enabled=False,
        duration_seconds=30 * 60,
        idle_timeout_seconds=15 * 60,
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
        idle_timeout_seconds=None,  # always-on baseline — no idle kill
        description="SAFE-NET baseline. Network on, mounts opt-in. Always-on.",
    ),
    "build": Profile(
        name="build",
        network_enabled=True,
        duration_seconds=2 * 60 * 60,
        idle_timeout_seconds=30 * 60,
        description="Development work. Network on, rw mounts allowed.",
    ),
    "power": Profile(
        name="power",
        network_enabled=True,
        duration_seconds=60 * 60,
        allow_broad_mount=True,
        idle_timeout_seconds=15 * 60,
        description="Capability-heavy. Shorter duration intentional.",
    ),
    "quarantine": Profile(
        name="quarantine",
        network_enabled=False,
        duration_seconds=30 * 60,
        idle_timeout_seconds=15 * 60,
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
    validate_positive_int_or_none(
        duration_seconds,
        field_label=f"profile {name!r}: duration_seconds",
        error_cls=ProfileConfigError,
    )

    allow_broad_mount = spec.get("allow_broad_mount", False)
    if not isinstance(allow_broad_mount, bool):
        raise ProfileConfigError(
            f"profile {name!r}: allow_broad_mount must be true/false"
        )

    description = spec.get("description", "")
    if not isinstance(description, str):
        raise ProfileConfigError(f"profile {name!r}: description must be a string")

    # idle_timeout_seconds (Stage 15): optional. Absent or null → no idle
    # timeout. Positive integer → kill the session after that many seconds
    # with no agent activity.
    idle_timeout_seconds = spec.get("idle_timeout_seconds")
    validate_positive_int_or_none(
        idle_timeout_seconds,
        field_label=f"profile {name!r}: idle_timeout_seconds",
        error_cls=ProfileConfigError,
    )

    # network_mode (D-184): optional. Absent → derived from network_enabled.
    # "mediated" routes cell egress through the credential broker and requires
    # network_enabled=True (the cell IS on a network, just a restricted one).
    network_mode = spec.get("network_mode")
    if network_mode is not None:
        if network_mode not in NETWORK_MODES:
            raise ProfileConfigError(
                f"profile {name!r}: network_mode must be one of "
                f"{', '.join(NETWORK_MODES)}"
            )
        if network_mode in ("mediated", "onecli", "hybrid") and not network_enabled:
            raise ProfileConfigError(
                f"profile {name!r}: network_mode {network_mode!r} requires "
                f"network_enabled true"
            )

    return Profile(
        name=name,
        network_enabled=network_enabled,
        duration_seconds=duration_seconds,
        allow_broad_mount=allow_broad_mount,
        description=description,
        idle_timeout_seconds=idle_timeout_seconds,
        network_mode=network_mode,
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
    validate_schema_version(data, target, ProfileConfigError)
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
