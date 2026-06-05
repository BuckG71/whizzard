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
import shutil
import subprocess
import sys
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


def pick_directory(prompt: str = "Select a folder to mount") -> str | None:
    """Open the OS's native folder-picker and return the chosen path, or None.

    Shells out to the platform's own dialog so Whizzard adds **no GUI
    dependency** (no tkinter): a PowerShell folder browser on Windows,
    ``osascript`` on macOS, ``zenity``/``kdialog`` on Linux. Returns None on
    cancel, on any error, or when there's no dialog tool / no display — callers
    must fall back to text entry rather than treat None as a failure.

    ``prompt`` is a fixed caller-supplied string (never user input), so it is
    safe to interpolate into the dialog command.
    """
    try:
        if is_windows():
            ps = (
                "Add-Type -AssemblyName System.Windows.Forms;"
                "$d = New-Object System.Windows.Forms.FolderBrowserDialog;"
                f"$d.Description = '{prompt}';"
                "if ($d.ShowDialog() -eq 'OK') { [Console]::Out.Write($d.SelectedPath) }"
            )
            cmd = ["powershell", "-NoProfile", "-STA", "-Command", ps]
        elif sys.platform == "darwin":
            cmd = [
                "osascript",
                "-e",
                f'POSIX path of (choose folder with prompt "{prompt}")',
            ]
        else:
            tool = shutil.which("zenity") or shutil.which("kdialog")
            if tool is None:
                return None
            if tool.endswith("kdialog"):
                cmd = [tool, "--getexistingdirectory", str(Path.home())]
            else:
                cmd = [tool, "--file-selection", "--directory", f"--title={prompt}"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            return None  # cancelled, or the dialog couldn't open
        chosen = result.stdout.strip()
        return chosen or None
    except (OSError, subprocess.SubprocessError):
        return None


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
