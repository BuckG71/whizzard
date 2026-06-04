"""Low-level platform and Docker-plumbing primitives.

Dependency-free (stdlib only) so any module — heavy (``docker_cmd``, which
pulls in adapters/enforcement/images) or light (``adjust``) — can import these
without dragging in the rest of the package or risking an import cycle. That
"importable everywhere" property is exactly why ``adjust`` previously kept its
own copy of the daemon-down strings; centralizing here removes the duplication
without the heavy import.

Three small concerns live together because they share that property and the
same Windows-quirk origin:

- :func:`is_windows` — the host-OS seam.
- the daemon-down stderr matcher — shared by ``docker_cmd`` and ``adjust``.
- (added alongside the mount-spec work) the forward-slash host-path helper.
"""

from __future__ import annotations

import os
from pathlib import Path


def is_windows() -> bool:
    """Whether the host running Whizzard is Windows.

    Wrapped in a function (rather than inlining ``os.name == "nt"``) so the
    UID-parity fallback and the safety block-lists can be exercised on
    Linux/macOS CI without monkeypatching the global ``os.name`` — which would
    leak into pytest's own path handling and crash failure reporting
    (``WindowsPath`` can't be instantiated on POSIX).
    """
    return os.name == "nt"


def docker_host_path(p: Path) -> str:
    """Host side of a Docker ``-v`` spec (or a recorded mount): forward-slash.

    Docker on Windows needs forward-slash host paths — a raw ``Path``
    stringifies with backslashes (``C:\\Users\\…``) which Docker's ``-v``
    parser mishandles alongside the drive-letter colon. ``as_posix()`` is a
    no-op on POSIX. Centralized so the rule and its reason live in one place.
    """
    return p.as_posix()


# Substrings docker emits when the daemon is unreachable. Stable across
# Docker for Mac, Docker Desktop on Windows, and Linux daemons. Matched
# case-sensitively because docker emits these verbatim.
DAEMON_DOWN_INDICATORS = (
    "Cannot connect to the Docker daemon",
    "Is the docker daemon running",
    "error during connect",  # Windows named-pipe variant
)


def looks_like_daemon_error(stderr: str) -> bool:
    """True if docker stderr indicates the daemon is unreachable.

    Distinct from "image missing" so callers can show "is Docker Desktop
    running?" instead of "did you build the image?".
    """
    return any(token in stderr for token in DAEMON_DOWN_INDICATORS)
