"""Preset registry — named bundles of profile + harness + mounts + capabilities.

A preset is a single-name shortcut for "launch with profile X, harness Y,
these mounts, these platforms, and these capability overrides." Lives in
``~/.whizzard/config/presets.json`` with the same shape as profiles.json
and harnesses.json (versioned envelope, dict of named entries).

Schema for ~/.whizzard/config/presets.json::

    {
      "schema_version": 1,
      "presets": {
        "<name>": {
          "profile": "<profile-name>",        # required
          "harness": "<harness-name>",        # required
          "mounts": ["<mount-name>", ...],    # optional, default []
          "platforms": ["<platform>", ...],   # optional, default []
                                              # subset of harness's ceiling
                                              # (per D-89 amended)
          "duration_seconds": <int|null>,     # optional, overrides profile
          "idle_timeout_seconds": <int|null>, # optional, overrides profile
          "allow_broad_mount": <bool>,        # optional, overrides profile
          "description": "...",               # optional
        },
        ...
      }
    }

Field-override semantics: top-level preset fields shadow the profile when
present. Omit the field entirely to inherit from the profile. Include it
(even as ``null`` for ``duration_seconds``) to override.

Validation timing: strict at load. ``load_presets`` errors if a preset
references a missing profile / harness / mount, or declares a platform
not in the harness's ceiling.

Bundled defaults (``_DEFAULT_PRESETS``) reflect the MVP user's daily-driver
setup per D-101. OSS-launch will revisit per the same pattern as D-157.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from whizzard.config import CONFIG_DIR

PRESETS_FILE = CONFIG_DIR / "presets.json"


@dataclass(frozen=True)
class Preset:
    """A named launch bundle. Resolution applies the profile, then overrides."""

    name: str
    profile: str
    harness: str
    mounts: tuple[str, ...] = ()
    platforms: tuple[str, ...] = ()
    duration_seconds: int | None = None
    idle_timeout_seconds: int | None = None
    allow_broad_mount: bool | None = None
    description: str = ""
    # Tracks which override fields were explicitly set so callers can apply
    # the omit-to-inherit pattern. Fields named here override the profile.
    _overrides_set: frozenset[str] = field(default_factory=frozenset)

    def overrides(self, field_name: str) -> bool:
        return field_name in self._overrides_set


class PresetConfigError(Exception):
    pass


# Bundled defaults: MVP user's daily-driver setup. Per D-101 / D-157
# pattern — opinionated for personal-MVP use, OSS-launch will revisit.
_DEFAULT_PRESETS: dict[str, dict[str, Any]] = {
    "hermes": {
        "profile": "default",
        "harness": "hermes-cell",
        "mounts": ["claude-projects", "ai-sandbox"],
        "platforms": ["discord"],
        "duration_seconds": None,
        "idle_timeout_seconds": None,
        "description": "Daily-driver Hermes (always-on, remote access via Discord)",
    },
    "shell": {
        "profile": "safe",
        "harness": "generic",
        "mounts": [],
        "platforms": [],
        "description": "Fast contained scratch shell",
    },
}


# Field names that, when present in a preset spec, override the profile.
_OVERRIDABLE_FIELDS = frozenset({
    "duration_seconds", "idle_timeout_seconds", "allow_broad_mount",
})


def _parse_preset(name: str, spec: dict) -> Preset:
    if not isinstance(spec, dict):
        raise PresetConfigError(f"preset {name!r}: spec must be an object")

    if "profile" not in spec or not isinstance(spec["profile"], str):
        raise PresetConfigError(
            f"preset {name!r}: required field 'profile' missing or non-string"
        )
    if "harness" not in spec or not isinstance(spec["harness"], str):
        raise PresetConfigError(
            f"preset {name!r}: required field 'harness' missing or non-string"
        )

    mounts_raw = spec.get("mounts", [])
    if not isinstance(mounts_raw, list) or not all(isinstance(m, str) for m in mounts_raw):
        raise PresetConfigError(
            f"preset {name!r}: 'mounts' must be a list of strings"
        )

    platforms_raw = spec.get("platforms", [])
    if not isinstance(platforms_raw, list) or not all(isinstance(p, str) for p in platforms_raw):
        raise PresetConfigError(
            f"preset {name!r}: 'platforms' must be a list of strings"
        )

    duration = spec.get("duration_seconds", 0)
    if "duration_seconds" in spec and duration is not None and not isinstance(duration, int):
        raise PresetConfigError(
            f"preset {name!r}: duration_seconds must be an integer or null"
        )

    idle = spec.get("idle_timeout_seconds", 0)
    if "idle_timeout_seconds" in spec and idle is not None and not isinstance(idle, int):
        raise PresetConfigError(
            f"preset {name!r}: idle_timeout_seconds must be an integer or null"
        )

    allow_broad = spec.get("allow_broad_mount")
    if "allow_broad_mount" in spec and not isinstance(allow_broad, bool):
        raise PresetConfigError(
            f"preset {name!r}: allow_broad_mount must be true/false"
        )

    description = spec.get("description", "")
    if not isinstance(description, str):
        raise PresetConfigError(f"preset {name!r}: description must be a string")

    overrides = frozenset(_OVERRIDABLE_FIELDS & set(spec.keys()))

    return Preset(
        name=name,
        profile=spec["profile"],
        harness=spec["harness"],
        mounts=tuple(mounts_raw),
        platforms=tuple(platforms_raw),
        duration_seconds=spec.get("duration_seconds") if "duration_seconds" in spec else None,
        idle_timeout_seconds=spec.get("idle_timeout_seconds") if "idle_timeout_seconds" in spec else None,
        allow_broad_mount=spec.get("allow_broad_mount") if "allow_broad_mount" in spec else None,
        description=description,
        _overrides_set=overrides,
    )


def load_presets(path: Path | None = None) -> dict[str, Preset]:
    """Load presets from JSON or return a fresh dict of bundled defaults."""
    target = path or PRESETS_FILE
    if not target.exists():
        return default_presets()

    try:
        data = json.loads(target.read_text())
    except json.JSONDecodeError as e:
        raise PresetConfigError(f"invalid {target}: {e}") from e

    if not isinstance(data, dict):
        raise PresetConfigError(f"{target}: top-level must be an object")
    presets_data = data.get("presets", {})
    if not isinstance(presets_data, dict):
        raise PresetConfigError(f"{target}: 'presets' must be an object")

    result: dict[str, Preset] = {}
    for name, spec in presets_data.items():
        result[name] = _parse_preset(name, spec)
    return result


def get_preset(name: str, path: Path | None = None) -> Preset:
    presets = load_presets(path)
    if name not in presets:
        available = ", ".join(sorted(presets)) or "(none registered)"
        raise PresetConfigError(
            f"unknown preset: {name!r}. Available: {available}"
        )
    return presets[name]


def list_presets(path: Path | None = None) -> list[Preset]:
    return list(load_presets(path).values())


def default_presets() -> dict[str, Preset]:
    """Fresh dict of bundled-default presets."""
    return {name: _parse_preset(name, dict(spec)) for name, spec in _DEFAULT_PRESETS.items()}


def validate_references(
    presets: dict[str, Preset],
    profile_names: set[str],
    harness_names: set[str],
    mount_names: set[str],
    harness_platforms: dict[str, set[str]] | None = None,
) -> None:
    """Strict reference validation. Raises PresetConfigError on first error.

    - Every preset's `profile` must exist in `profile_names`.
    - Every preset's `harness` must exist in `harness_names`.
    - Every mount in `preset.mounts` must exist in `mount_names`.
    - Every platform in `preset.platforms` must be in the harness's ceiling
      if `harness_platforms` is provided (per D-89 amended — presets restrict,
      never expand). If `harness_platforms` is None, the platform check is
      skipped (the caller doesn't have the harness platform info yet).
    """
    for preset in presets.values():
        if preset.profile not in profile_names:
            raise PresetConfigError(
                f"preset {preset.name!r}: references unknown profile "
                f"{preset.profile!r}. Available: {', '.join(sorted(profile_names))}"
            )
        if preset.harness not in harness_names:
            raise PresetConfigError(
                f"preset {preset.name!r}: references unknown harness "
                f"{preset.harness!r}. Available: {', '.join(sorted(harness_names))}"
            )
        for mount_name in preset.mounts:
            if mount_name not in mount_names:
                raise PresetConfigError(
                    f"preset {preset.name!r}: references unknown mount "
                    f"{mount_name!r}. Available: {', '.join(sorted(mount_names)) or '(none)'}"
                )
        if harness_platforms is not None:
            ceiling = harness_platforms.get(preset.harness, set())
            for platform in preset.platforms:
                if platform not in ceiling:
                    raise PresetConfigError(
                        f"preset {preset.name!r}: platform {platform!r} not in "
                        f"harness {preset.harness!r} ceiling. Allowed: "
                        f"{', '.join(sorted(ceiling)) or '(none)'}"
                    )
