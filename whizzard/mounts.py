"""Mount registry — named host paths agents can access.

Stage 2 scope: load mounts.json, resolve --mount <name>[:mode] specs into
docker -v arguments, and reject unregistered names. The full safety policy
(blocklist of dangerous paths, broad-mount overrides, config write-protection)
lands in Stage 6.

Schema for ~/.whizzard/config/mounts.json:

    {
      "schema_version": 1,
      "mounts": {
        "<name>": {
          "host_path": "/absolute/or/tilde/path",
          "default_mode": "ro" | "rw",
          "description": "..."
        },
        ...
      }
    }

Mounts are exposed inside the container at /mounts/<name>. The default_mode
caps the maximum permission: a mount registered "ro" cannot be requested
"rw" via the CLI.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from whizzard._platform import docker_host_path
from whizzard.config import CONFIG_DIR, validate_schema_version

MountMode = Literal["ro", "rw"]
MOUNTS_FILE = CONFIG_DIR / "mounts.json"
CONTAINER_MOUNT_ROOT = "/mounts"

# Mount names flow directly into the container path (/mounts/<name>) and the
# docker `-v host:container:mode` argument. The colon separator and the
# container-path resolver make path-shaped names dangerous: a name like
# "../etc" would resolve to /etc inside the cell, weakening the D-11
# "mount list IS the permission model" invariant. The regex below allows
# alphanumerics, dash, and underscore — what `docker run -v` reliably
# accepts as a directory segment.
_MOUNT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


@dataclass(frozen=True)
class Mount:
    name: str
    host_path: Path
    default_mode: MountMode
    description: str = ""

    def container_path(self) -> str:
        return f"{CONTAINER_MOUNT_ROOT}/{self.name}"

    def docker_volume_arg(self, mode: MountMode | None = None) -> str:
        effective_mode = mode or self.default_mode
        return f"{docker_host_path(self.host_path)}:{self.container_path()}:{effective_mode}"


# Bundled mount defaults. These reflect the MVP user's daily-driver setup
# (D-101 personal-use threshold) — Claude desktop project workspace and the
# AI-sandbox tree where Whizzard itself lives. OSS-launch will revisit per
# the same pattern as D-157 (default profile change). Until then, fresh
# installs without ~/.whizzard/config/mounts.json get these registered.
_DEFAULT_MOUNTS: dict[str, dict[str, str]] = {
    "claude-projects": {
        "host_path": "~/Documents/Claude/projects",
        "default_mode": "rw",
        "description": "Claude desktop project workspace",
    },
    "ai-sandbox": {
        "host_path": "~/ai-sandbox",
        "default_mode": "rw",
        "description": "AI-sandbox tree (Whizzard, other AI projects)",
    },
}


def _validate_mount_name(name: str) -> None:
    """Reject names that would corrupt the container path or `-v` argument.

    F-A-02: names flow into `/mounts/<name>` and the docker volume spec
    unsanitized. A name with `/`, `..`, `:` or whitespace would either
    escape the container mount root or break the colon-separated docker
    argument. The regex below is intentionally narrow.
    """
    if not isinstance(name, str) or not _MOUNT_NAME_RE.fullmatch(name):
        raise MountRegistryError(
            f"invalid mount name {name!r}: must match "
            f"^[A-Za-z0-9][A-Za-z0-9_-]{{0,63}}$ "
            "(alphanumerics, dash, underscore; ≤64 chars)"
        )


def default_mounts() -> dict[str, Mount]:
    """Return a fresh dict of bundled-default mounts.

    F-B5 (catch-up review pass 2): runs `_validate_mount_name` on every
    bundled-default name so a future maintainer adding a malformed key
    (`../etc`, etc.) to `_DEFAULT_MOUNTS` gets the same loud rejection
    user-loaded mounts get at `load_mounts`. Without this, defaults
    would silently slip past the F-A-02 invariant.
    """
    registry: dict[str, Mount] = {}
    for name, spec in _DEFAULT_MOUNTS.items():
        _validate_mount_name(name)
        registry[name] = Mount(
            name=name,
            # F-A-04: resolve() so default and user-loaded Mounts share the
            # same canonicalization. Symlinks are followed, and `==` on two
            # Mounts pointing at the same logical target works.
            host_path=Path(spec["host_path"]).expanduser().resolve(),
            default_mode=spec["default_mode"],  # type: ignore[arg-type]
            description=spec["description"],
        )
    return registry


class MountRegistryError(Exception):
    pass


def load_mounts(path: Path | None = None) -> dict[str, Mount]:
    """Load the mount registry. Returns bundled defaults if no file exists.

    Bundled defaults reflect the MVP user's setup (D-101). Users with their
    own ~/.whizzard/config/mounts.json get exactly what they declared — the
    file does not extend the bundled defaults, it replaces them.
    """
    target = path or MOUNTS_FILE
    if not target.exists():
        return default_mounts()
    try:
        data = json.loads(target.read_text())
    except json.JSONDecodeError as e:
        raise MountRegistryError(f"invalid {target}: {e}") from e

    # F-A-06: assert the top-level shape before reaching .get(), so a
    # non-dict JSON file produces a clean MountRegistryError instead of
    # AttributeError on `data.get`.
    if not isinstance(data, dict):
        raise MountRegistryError(f"{target}: top-level must be an object")
    validate_schema_version(data, target, MountRegistryError)

    mounts_data = data.get("mounts", {})
    if not isinstance(mounts_data, dict):
        raise MountRegistryError(f"{target}: 'mounts' must be an object")

    registry: dict[str, Mount] = {}
    for name, spec in mounts_data.items():
        _validate_mount_name(name)
        if not isinstance(spec, dict):
            raise MountRegistryError(f"mount {name!r}: spec must be an object")
        host_path_raw = spec.get("host_path", "")
        if not host_path_raw:
            raise MountRegistryError(f"mount {name!r}: missing host_path")
        host_path = Path(host_path_raw).expanduser().resolve()
        default_mode = spec.get("default_mode", "ro")
        if default_mode not in ("ro", "rw"):
            raise MountRegistryError(
                f"mount {name!r}: default_mode must be 'ro' or 'rw', got {default_mode!r}"
            )
        description = spec.get("description", "")
        registry[name] = Mount(
            name=name,
            host_path=host_path,
            default_mode=default_mode,
            description=description,
        )
    return registry


def resolve_mount_spec(
    spec: str, registry: dict[str, Mount]
) -> tuple[Mount, MountMode]:
    """Parse a --mount value like 'project-alpha' or 'project-alpha:ro'.

    Returns the resolved Mount and the effective mode after applying
    default_mode and the ro→rw cap.
    """
    if ":" in spec:
        name, _, mode_str = spec.partition(":")
    else:
        name, mode_str = spec, ""

    if name not in registry:
        available = ", ".join(sorted(registry)) or "(none registered)"
        raise MountRegistryError(
            f"unknown mount {name!r}. Available: {available}"
        )

    mount = registry[name]
    if mode_str and mode_str not in ("ro", "rw"):
        raise MountRegistryError(
            f"mount mode for {name!r} must be 'ro' or 'rw', got {mode_str!r}"
        )

    requested: MountMode = mode_str if mode_str else mount.default_mode  # type: ignore[assignment]

    # Registry default_mode caps requested mode. ro cannot be elevated to rw.
    if mount.default_mode == "ro" and requested == "rw":
        raise MountRegistryError(
            f"mount {name!r} is registered as 'ro'; cannot request 'rw'"
        )
    return mount, requested


def load_mount_specs(path: Path | None = None) -> dict[str, dict]:
    """Raw mount-spec dicts from the file, host_path strings **preserved** (not
    resolved). Returns ``{}`` when no file exists.

    Use this (not `load_mounts`) when adding/removing a mount and writing the
    registry back: `load_mounts` canonicalizes every host_path via
    ``expanduser().resolve()``, so a load→save cycle would silently rewrite
    other entries' stored forms (e.g. ``~/code`` → ``/Users/x/code``). This
    keeps existing entries verbatim.
    """
    target = path or MOUNTS_FILE
    if not target.exists():
        return {}
    try:
        data = json.loads(target.read_text())
    except json.JSONDecodeError as e:
        raise MountRegistryError(f"invalid {target}: {e}") from e
    if not isinstance(data, dict):
        raise MountRegistryError(f"{target}: top-level must be an object")
    specs = data.get("mounts", {})
    if not isinstance(specs, dict):
        raise MountRegistryError(f"{target}: 'mounts' must be an object")
    return specs


def write_mount_specs(specs: dict[str, dict], path: Path | None = None) -> None:
    """Atomically write raw mount specs under the standard envelope."""
    from whizzard._atomic import atomic_write_text

    target = path or MOUNTS_FILE
    payload = {"schema_version": 1, "mounts": specs}
    atomic_write_text(target, json.dumps(payload, indent=2) + "\n")


# Stage 2 had `basic_path_sanity_check` here; superseded by the full policy
# in `whizzard.safety` as of Stage 6. Path-existence and root-mount rejection
# are now part of `whizzard.safety.check_mount_path`.
