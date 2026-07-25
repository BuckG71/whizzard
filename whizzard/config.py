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
          "memory_limit": "<size>" | null,         # optional; e.g. "2g", "512m"; null = no cap
          "memory_swap": "<size>" | null,          # optional; == memory_limit disables swap; null = Docker default
          "cpus": <number> | null,                 # optional; e.g. 2 or 1.5; null = no cap
          "pids_limit": <int> | null,              # optional; fork-bomb guard; null = no cap
          "web_search": "off"|"firecrawl"|"ddgs",   # optional; default "off"
          "description": "..."                      # default ""
        },
        ...
      }
    }
"""

from __future__ import annotations

import json
import os
import re
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

#: Web-search backends a profile may enable (D-194). "off" (default) authors no
#: web config into the cell and the harness's web_search fails closed rather
#: than fabricating results. "firecrawl" is the CONTAINED rung (single
#: allowlistable endpoint routed through a broker, credential brokered host-side
#: — requires a mediated/hybrid network). "ddgs" is the OPEN rung: keyless, but
#: it fans out directly to many search-engine hosts via TLS impersonation
#: (primp) and so is un-brokerable — it requires open egress, an expanded
#: security surface the profile opts into explicitly. The set is intentionally
#: small so a profile can only name a mode Whizzard actually wires end-to-end.
WEB_SEARCH_MODES = ("off", "firecrawl", "ddgs")


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
    #: Resource caps (all optional; None = no limit → Docker default). Emitted
    #: by build_run_argv after the unconditional baseline flags. Every field is
    #: editable per-profile in profiles.json so caps fine-tune without a code
    #: change. memory_limit/memory_swap are Docker size strings ("2g", "512m");
    #: setting memory_swap == memory_limit disables swap for a hard ceiling.
    memory_limit: str | None = None
    memory_swap: str | None = None
    cpus: float | None = None      # fractional CPUs allowed (e.g. 1.5)
    pids_limit: int | None = None  # fork-bomb guard
    #: Web-search backend for this profile (D-194); one of WEB_SEARCH_MODES.
    #: "off" (default) = no web config authored into the cell, harness search
    #: fails closed. The adapter authors the matching Hermes `web.backend` into
    #: the read-only managed-scope config at launch; the credential is brokered
    #: host-side (never lands in the cell).
    web_search: str = "off"

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


#: Docker memory size: a positive integer with an optional b/k/m/g unit.
_MEMORY_RE = re.compile(r"[1-9]\d*[bkmgBKMG]?")


def validate_memory_or_none(
    value: object,
    *,
    field_label: str,
    error_cls: type[Exception],
) -> None:
    """Enforce Docker memory-string format OR None.

    Accepts a positive integer optionally suffixed with a byte unit (b/k/m/g,
    either case): e.g. ``"512m"``, ``"2g"``, ``"1073741824"``. ``None`` means
    "no limit". Shared by ``memory_limit`` and ``memory_swap``.
    """
    if value is None:
        return
    if not isinstance(value, str) or not _MEMORY_RE.fullmatch(value):
        raise error_cls(
            f"{field_label} must be a positive integer with an optional "
            f"b/k/m/g suffix (e.g. '512m', '2g'), or null; got {value!r}"
        )


def validate_positive_number_or_none(
    value: object,
    *,
    field_label: str,
    error_cls: type[Exception],
) -> None:
    """Enforce 'positive number (int or float) OR None'.

    Used for ``cpus`` (fractional CPUs allowed). ``bool`` is rejected (a
    Python bool is an int and would slip through a naive check). ``None``
    means "no cap".
    """
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise error_cls(f"{field_label} must be a number or null")
    if value <= 0:
        raise error_cls(f"{field_label} must be positive (got {value})")


_MEM_UNIT_BYTES = {"b": 1, "k": 1024, "m": 1024**2, "g": 1024**3}
#: Docker's floor for --memory. Values below this parse fine but are rejected
#: by `docker run`, so we catch them at config time.
_DOCKER_MIN_MEMORY_BYTES = 6 * 1024 * 1024


def _memory_to_bytes(value: str) -> int:
    """Convert a `_MEMORY_RE`-validated memory string to bytes.

    Assumes `value` already passed ``validate_memory_or_none`` (digits with an
    optional b/k/m/g unit); unit-less values are bytes.
    """
    unit = value[-1].lower()
    if unit in _MEM_UNIT_BYTES:
        return int(value[:-1]) * _MEM_UNIT_BYTES[unit]
    return int(value)


# Bundled defaults. Used when the user has no profiles.json or as the
# template that ships in config/profiles.json.example.
_DEFAULT_PROFILES: dict[str, Profile] = {
    "safe": Profile(
        name="safe",
        network_enabled=False,
        duration_seconds=30 * 60,
        idle_timeout_seconds=15 * 60,
        # Hard memory ceiling (swap disabled: memory_swap == memory_limit).
        memory_limit="2g",
        memory_swap="2g",
        cpus=2.0,
        pids_limit=512,
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
        # Always-on long-runner: cap memory + pids so a leak/fork-bomb can't
        # exhaust the host, but leave CPU uncapped and swap at Docker's default
        # (up to 2x the memory limit) so the productive baseline never feels
        # throttled or gets abruptly OOM-killed.
        memory_limit="4g",
        cpus=None,
        pids_limit=1024,
        description="SAFE-NET baseline. Network on, mounts opt-in. Always-on.",
    ),
    "build": Profile(
        name="build",
        network_enabled=True,
        duration_seconds=2 * 60 * 60,
        idle_timeout_seconds=30 * 60,
        # Heavy dev workloads: generous, soft caps (swap left enabled).
        memory_limit="8g",
        cpus=4.0,
        pids_limit=2048,
        description="Development work. Network on, rw mounts allowed.",
    ),
    "power": Profile(
        name="power",
        network_enabled=True,
        duration_seconds=60 * 60,
        allow_broad_mount=True,
        idle_timeout_seconds=15 * 60,
        memory_limit="8g",
        cpus=4.0,
        pids_limit=2048,
        description="Capability-heavy. Shorter duration intentional.",
    ),
    "quarantine": Profile(
        name="quarantine",
        network_enabled=False,
        duration_seconds=30 * 60,
        idle_timeout_seconds=15 * 60,
        # Untrusted: tightest caps, hard memory ceiling (swap disabled).
        memory_limit="1g",
        memory_swap="1g",
        cpus=1.0,
        pids_limit=256,
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

    # Resource caps (all optional; absent/null → no limit). Every field is
    # editable per-profile in profiles.json so caps fine-tune without a code
    # change.
    memory_limit = spec.get("memory_limit")
    validate_memory_or_none(
        memory_limit,
        field_label=f"profile {name!r}: memory_limit",
        error_cls=ProfileConfigError,
    )
    if memory_limit is not None and _memory_to_bytes(memory_limit) < _DOCKER_MIN_MEMORY_BYTES:
        raise ProfileConfigError(
            f"profile {name!r}: memory_limit must be at least 6m "
            f"(Docker's minimum), got {memory_limit!r}"
        )
    memory_swap = spec.get("memory_swap")
    validate_memory_or_none(
        memory_swap,
        field_label=f"profile {name!r}: memory_swap",
        error_cls=ProfileConfigError,
    )
    if memory_swap is not None and memory_limit is None:
        raise ProfileConfigError(
            f"profile {name!r}: memory_swap requires memory_limit "
            f"(Docker rejects --memory-swap without --memory)"
        )
    if (
        memory_swap is not None
        and memory_limit is not None
        and _memory_to_bytes(memory_swap) < _memory_to_bytes(memory_limit)
    ):
        raise ProfileConfigError(
            f"profile {name!r}: memory_swap ({memory_swap}) must be >= "
            f"memory_limit ({memory_limit}) — Docker requires swap >= memory"
        )
    cpus = spec.get("cpus")
    validate_positive_number_or_none(
        cpus,
        field_label=f"profile {name!r}: cpus",
        error_cls=ProfileConfigError,
    )
    pids_limit = spec.get("pids_limit")
    validate_positive_int_or_none(
        pids_limit,
        field_label=f"profile {name!r}: pids_limit",
        error_cls=ProfileConfigError,
    )

    # web_search (D-194): optional; absent → "off". Must name a wired backend.
    web_search = spec.get("web_search", "off")
    if web_search not in WEB_SEARCH_MODES:
        raise ProfileConfigError(
            f"profile {name!r}: web_search must be one of "
            f"{', '.join(WEB_SEARCH_MODES)} (got {web_search!r})"
        )

    return Profile(
        name=name,
        network_enabled=network_enabled,
        duration_seconds=duration_seconds,
        allow_broad_mount=allow_broad_mount,
        description=description,
        idle_timeout_seconds=idle_timeout_seconds,
        network_mode=network_mode,
        memory_limit=memory_limit,
        memory_swap=memory_swap,
        cpus=float(cpus) if cpus is not None else None,
        pids_limit=pids_limit,
        web_search=web_search,
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
