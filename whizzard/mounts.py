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
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from whizzard.config import CONFIG_DIR


MountMode = Literal["ro", "rw"]
MOUNTS_FILE = CONFIG_DIR / "mounts.json"
CONTAINER_MOUNT_ROOT = "/mounts"


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
        return f"{self.host_path}:{self.container_path()}:{effective_mode}"


class MountRegistryError(Exception):
    pass


def load_mounts(path: Path | None = None) -> dict[str, Mount]:
    """Load the mount registry. Returns empty dict if no file exists."""
    target = path or MOUNTS_FILE
    if not target.exists():
        return {}
    try:
        data = json.loads(target.read_text())
    except json.JSONDecodeError as e:
        raise MountRegistryError(f"invalid {target}: {e}") from e

    mounts_data = data.get("mounts", {})
    if not isinstance(mounts_data, dict):
        raise MountRegistryError(f"{target}: 'mounts' must be an object")

    registry: dict[str, Mount] = {}
    for name, spec in mounts_data.items():
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


# Stage 2 had `basic_path_sanity_check` here; superseded by the full policy
# in `whizzard.safety` as of Stage 6. Path-existence and root-mount rejection
# are now part of `whizzard.safety.check_mount_path`.
