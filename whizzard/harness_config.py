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
import re
from pathlib import Path

from whizzard.config import CONFIG_DIR, validate_schema_version

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
        # D-181: interactive terminal chat is the *default invocation*, not
        # `hermes gateway run`. The harness stays discord-capable (the
        # `platforms` ceiling), but a bare `hermes` start ignores it; gateway
        # mode is opted into by overriding start_command.
        "start_command": "hermes",
        "wrap_up_command": "/quit",
        "wrap_up_grace_seconds": 30,
        "hermes_home": "~/.hermes-whizzard-cell",
        "platforms": ["discord"],
        "description": "Whizzard-wrapped Hermes (interactive chat; gateway/Discord opt-in)",
        # D-185: model-credential mediation config (bar C). Inert until a
        # mediated profile uses it; then the broker resolves the key host-side
        # and the cell sees only a placeholder + the broker URL.
        "model_credential": {
            "provider": "anthropic",
            "secret": "ANTHROPIC_API_KEY",
            "base_url_env": "ANTHROPIC_BASE_URL",
        },
    },
}


class HarnessConfigError(Exception):
    pass


# Env keys that affect process loading or tool resolution. A harness config
# that sets any of these is almost certainly a misconfig; reject at parse
# time so the user sees a clear error instead of silently weakened cell
# behavior. Per S20.4 / the senior-engineer review.
_DENIED_ENV_KEYS: frozenset[str] = frozenset({
    "LD_PRELOAD",          # forces a shared library to load first
    "LD_LIBRARY_PATH",     # overrides shared-library search
    "LD_AUDIT",            # rtld auditing hook
    "LD_BIND_NOW",         # alters lazy-bind behavior
    "DYLD_INSERT_LIBRARIES",  # macOS LD_PRELOAD analog
    "DYLD_LIBRARY_PATH",   # macOS LD_LIBRARY_PATH analog
    "PATH",                # tool resolution
    "PYTHONPATH",          # affects Python import search
    "PYTHONSTARTUP",       # auto-runs at Python REPL launch
    "IFS",                 # shell field-separator; classic injection vector
})

# Standard env-var-name shape; a length cap keeps the argv sane.
_VALID_ENV_NAME = re.compile(r"\A[A-Za-z_][A-Za-z0-9_]{0,127}\Z")


def _validate_env_name(name: object, *, harness: str, field_label: str) -> None:
    """Reject a bad env-var NAME on any harness surface (D-133 generalized).

    Applies to every place a config can name an env var — literal `env` keys,
    `secrets`, `model_credential.secret`, `base_url_env` — so the denied-key set
    can't be bypassed by declaring a dangerous name through a surface other than
    `env` (the senior-review + Codex 2026-07-01 finding).
    """
    if not isinstance(name, str) or not _VALID_ENV_NAME.match(name):
        raise HarnessConfigError(
            f"harness {harness!r}: {field_label} {name!r} is not a valid "
            f"env-var name (expected [A-Za-z_][A-Za-z0-9_]*, ≤128 chars)"
        )
    if name in _DENIED_ENV_KEYS:
        raise HarnessConfigError(
            f"harness {harness!r}: {field_label} {name!r} is denied — this name "
            f"controls process loading or tool resolution and must not be set "
            f"via harness config"
        )


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
    # F-B-06: empty/whitespace-only start_command would shlex-split to []
    # and silently fall through to the image's CMD inside the container,
    # which is not behavior we want from a harness config.
    start_command = spec["start_command"]
    if not isinstance(start_command, str) or not start_command.strip():
        raise HarnessConfigError(
            f"harness {name!r}: start_command must be a non-empty string"
        )

    # Optional integer fields
    for int_field in ("wrap_up_grace_seconds", "startup_timeout_seconds"):
        if int_field in spec and not isinstance(spec[int_field], int):
            raise HarnessConfigError(
                f"harness {name!r}: {int_field} must be an integer"
            )

    # env must be a dict if present
    if "env" in spec:
        env = spec["env"]
        if not isinstance(env, dict):
            raise HarnessConfigError(f"harness {name!r}: env must be an object")
        # S20.4 / D-133: reject env keys that affect process loading or
        # tool resolution. The cell still has --cap-drop=ALL + non-root
        # so even a planted LD_PRELOAD .so can't escape, but accepting
        # these from harness config is a clear misconfig footgun (the
        # senior-engineer review's "No env-name denylist on
        # adapter-supplied container_env" finding).
        for env_key in env:
            _validate_env_name(env_key, harness=name, field_label="env key")

    # platforms (D-89, agent harnesses) must be a list of strings if present
    if "platforms" in spec:
        plats = spec["platforms"]
        if not isinstance(plats, list) or not all(isinstance(p, str) for p in plats):
            raise HarnessConfigError(
                f"harness {name!r}: platforms must be a list of strings"
            )

    # secrets (D-162) must be a list of env-var-name strings if present;
    # plaintext credential values are never permitted — values resolve at
    # launch from OneCLI / host env, per D-134's delivery semantics.
    if "secrets" in spec:
        secrets = spec["secrets"]
        if not isinstance(secrets, list) or not all(isinstance(s, str) for s in secrets):
            raise HarnessConfigError(
                f"harness {name!r}: secrets must be a list of env-var-name strings "
                "(plaintext credential values are not permitted per D-162)"
            )
        for sec in secrets:
            _validate_env_name(sec, harness=name, field_label="secret")

    # model_credential (D-184/D-185): optional block enabling broker mediation
    # for a mediated profile. `secret` is an env-var NAME resolved host-side by
    # the broker (never a plaintext value here).
    if "model_credential" in spec:
        mc = spec["model_credential"]
        if not isinstance(mc, dict):
            raise HarnessConfigError(
                f"harness {name!r}: model_credential must be an object"
            )
        secret = mc.get("secret")
        _validate_env_name(
            secret, harness=name, field_label="model_credential.secret",
        )
        if "base_url_env" in mc:
            _validate_env_name(
                mc["base_url_env"], harness=name,
                field_label="model_credential.base_url_env",
            )
        for opt in ("provider", "placeholder"):
            if opt in mc and not isinstance(mc[opt], str):
                raise HarnessConfigError(
                    f"harness {name!r}: model_credential.{opt} must be a string"
                )
        # The model secret must NOT also be in `secrets`: that path injects the
        # real value, while mediation replaces it with a placeholder. Listing
        # it in both would leak the real key into the cell.
        if secret in (spec.get("secrets") or []):
            raise HarnessConfigError(
                f"harness {name!r}: model_credential.secret {secret!r} must not "
                "also appear in `secrets` — mediation replaces it with a "
                "placeholder; listing it in secrets injects the real value"
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
    validate_schema_version(data, target, HarnessConfigError)

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
