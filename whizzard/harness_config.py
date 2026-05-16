"""harnesses.json loader.

Stage 7 scope: load the harness registry from ~/.whizzard/config/harnesses.json
or fall back to bundled defaults. Validate the schema (per architecture.md):

    {
      "schema_version": 1,
      "harnesses": {
        "<name>": {
          "type": "shell" | "agent",       # required
          "start_command": "...",          # required
          "stop_command": "...",           # optional
          "wrap_up_command": "...",        # optional (Stage 8 / Hermes)
          "wrap_up_grace_seconds": 30,     # optional
          "working_dir": "/path/in/c",     # optional
          "health_check": "...",           # optional
          "startup_timeout_seconds": 30,   # optional
          "env": { "K": "V", ... },        # optional
          "platforms": ["discord", ...]    # optional (Stage 8 / agent harnesses)
        },
        ...
      }
    }
"""

from __future__ import annotations

import json
from pathlib import Path

from whizzard.config import CONFIG_DIR


HARNESSES_FILE = CONFIG_DIR / "harnesses.json"


_DEFAULT_HARNESSES: dict[str, dict] = {
    "generic": {
        "type": "shell",
        "start_command": "/bin/bash",
        "description": "plain interactive bash shell — the default harness",
    },
    # Stage 10 / D-101 personal-MVP defaults. The hermes-cell harness ships
    # so the bundled `hermes` preset validates out of the box. Reflects the
    # MVP user's Migrate-from-host setup (D-86). OSS-launch will revisit
    # per the same pattern as D-157.
    "hermes-cell": {
        "type": "agent",
        "start_command": "hermes gateway run",
        "wrap_up_command": "/quit",
        "wrap_up_grace_seconds": 30,
        "hermes_home": "~/.hermes-whizzard-cell",
        "platforms": ["discord"],
        "description": "Whizzard-wrapped Hermes (gateway mode, Discord active)",
    },
}


class HarnessConfigError(Exception):
    pass


def _validate_spec(name: str, spec: dict) -> None:
    if not isinstance(spec, dict):
        raise HarnessConfigError(f"harness {name!r}: spec must be an object")
    if "type" not in spec:
        raise HarnessConfigError(f"harness {name!r}: missing required field 'type'")
    if spec["type"] not in ("shell", "agent"):
        raise HarnessConfigError(
            f"harness {name!r}: type must be 'shell' or 'agent', got {spec['type']!r}"
        )
    if "start_command" not in spec:
        raise HarnessConfigError(f"harness {name!r}: missing required field 'start_command'")

    # Optional integer fields
    for int_field in ("wrap_up_grace_seconds", "startup_timeout_seconds"):
        if int_field in spec and not isinstance(spec[int_field], int):
            raise HarnessConfigError(
                f"harness {name!r}: {int_field} must be an integer"
            )

    # env must be a dict if present
    if "env" in spec and not isinstance(spec["env"], dict):
        raise HarnessConfigError(f"harness {name!r}: env must be an object")

    # platforms (D-89, agent harnesses) must be a list of strings if present
    if "platforms" in spec:
        plats = spec["platforms"]
        if not isinstance(plats, list) or not all(isinstance(p, str) for p in plats):
            raise HarnessConfigError(
                f"harness {name!r}: platforms must be a list of strings"
            )


def load_harnesses(path: Path | None = None) -> dict[str, dict]:
    """Return a dict of harness_name → config_dict.

    Falls back to a copy of the bundled defaults if no file exists.
    """
    target = path or HARNESSES_FILE
    if not target.exists():
        return {k: dict(v) for k, v in _DEFAULT_HARNESSES.items()}

    try:
        data = json.loads(target.read_text())
    except json.JSONDecodeError as e:
        raise HarnessConfigError(f"invalid {target}: {e}") from e

    if not isinstance(data, dict):
        raise HarnessConfigError(f"{target}: top-level must be an object")

    harnesses = data.get("harnesses", {})
    if not isinstance(harnesses, dict):
        raise HarnessConfigError(f"{target}: 'harnesses' must be an object")
    if not harnesses:
        raise HarnessConfigError(
            f"{target}: 'harnesses' is empty — at least one harness is required"
        )

    for name, spec in harnesses.items():
        _validate_spec(name, spec)

    return harnesses


def get_harness_config(name: str, path: Path | None = None) -> dict:
    """Return the config dict for one harness, or raise if unknown."""
    harnesses = load_harnesses(path)
    if name not in harnesses:
        available = ", ".join(sorted(harnesses)) or "(none registered)"
        raise HarnessConfigError(
            f"unknown harness: {name!r}. Available: {available}"
        )
    return harnesses[name]


def default_harnesses() -> dict[str, dict]:
    """Return a copy of the bundled defaults — used by CLI seeding."""
    return {k: dict(v) for k, v in _DEFAULT_HARNESSES.items()}
