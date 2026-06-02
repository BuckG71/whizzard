"""Safety policy enforcement for mount paths.

Implements the three-tier policy from architecture.md:

1. Hard block (no override possible): the filesystem root, the user's home
   directory, sensitive subdirs (~/.ssh, ~/.gnupg, ~/.aws, ~/Library,
   ~/.docker), the Docker socket, and the Whizzard config directory.

2. Hard block with explicit override: broad folders (~/Documents, ~/Desktop,
   ~/Downloads, ~/Projects, ~/Movies, ~/Music, ~/Pictures), cloud sync
   roots (iCloud Drive, Dropbox, OneDrive, Google Drive), and parent
   directories of any registered mount target. Allowed only when BOTH
   profile.allow_broad_mount is true AND --allow-broad-mount is passed
   on the CLI. Either gate alone is insufficient.

3. Allowed: anything not matching the above.

Path containment semantics:

  Two-way intersection check via Path.relative_to. A mount path is rejected
  if it equals a blocked path, is inside a blocked path, or contains a
  blocked path. Mounting / is rejected because it contains ~/.ssh, mounting
  ~/.ssh is rejected by exact match, and mounting ~/.ssh/keys is rejected
  because it is inside ~/.ssh.

  Exception: the filesystem root and $HOME are blocked only at exact match.
  Otherwise no path inside $HOME could ever be mounted, since every such
  path is "inside" $HOME by definition.

macOS is the primary target; the HOME-relative blocks also cover Linux and
Windows by construction. Windows-specific exclusions (AppData, system dirs,
OneDrive, etc.) are merged via `_windows_exclusions` when `os.name == "nt"`.
Linux desktop paths (~/.config/google-chrome, ~/.mozilla) can be added in a
later pass.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from whizzard.config import WHIZZARD_HOME, Profile

HOME = Path.home()


# Tier 1a: exact-match-only hard blocks. Mounting these paths themselves is
# blocked, but mounting paths inside them is fine (subject to other rules).
_EXACT_HARD_BLOCKS: list[Path] = [
    Path("/"),
    HOME,
]

# Tier 1b: deep hard blocks. Mounting these paths, anything inside them, or
# anything containing them is blocked. No override.
_DEEP_HARD_BLOCKS: list[Path] = [
    HOME / ".ssh",
    HOME / ".gnupg",
    HOME / ".aws",
    HOME / "Library",         # macOS: app data, keychains, browser profiles
    HOME / ".docker",         # Docker Desktop config / socket symlink
    Path("/var/run/docker.sock"),
    WHIZZARD_HOME,            # config write-protection invariant
]

# Tier 2: override-required broad folders.
_BROAD_FOLDERS: list[Path] = [
    HOME / "Documents",
    HOME / "Desktop",
    HOME / "Downloads",
    HOME / "Projects",
    HOME / "Movies",
    HOME / "Music",
    HOME / "Pictures",
]

# Tier 2: override-required cloud sync roots.
_CLOUD_SYNC_ROOTS: list[Path] = [
    HOME / "Library/Mobile Documents/com~apple~CloudDocs",  # iCloud Drive
    HOME / "Dropbox",
    HOME / "OneDrive",
    HOME / "Google Drive",
    HOME / "iCloud Drive",  # some users have this as a symlink
]


def _windows_exclusions(home: Path) -> dict[str, list[Path]]:
    """Windows-specific path exclusions, validated 2026-06 (research in
    `docs/known_issues.md` "Windows support is unverified").

    Returned as a dict so the set is unit-testable on any platform; the
    import-time guard below merges it into the live block lists only when
    ``os.name == "nt"``, so macOS/Linux behavior is unchanged.

    The HOME-relative dotfile/folder blocks (.ssh, .aws, .docker,
    Documents…) already resolve correctly on Windows via ``Path.home()``;
    this fills the gaps that are Windows-specific.
    """
    # Windows env-var lookups are case-insensitive; uppercase names keep
    # the linter happy and still resolve %SystemRoot% etc. on Windows.
    windir = Path(os.environ.get("SYSTEMROOT", r"C:\Windows"))
    programdata = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
    system_drive = os.environ.get("SYSTEMDRIVE", "C:")
    return {
        # exact-match hard blocks
        "exact": [Path(system_drive + os.sep)],  # e.g. C:\ (drive root)
        # deep hard blocks (no override)
        "deep": [
            # AppData (Roaming + Local + LocalLow) is the Windows analog of
            # macOS ~/Library: browser password stores + keys (Chrome/Edge
            # Login Data, Firefox profiles), the Credential Manager file
            # store, DPAPI master keys, gnupg, gcloud, PowerShell history.
            home / "AppData",
            # Cloud/k8s creds — also relevant on POSIX; Windows-scoped for
            # now (candidate to promote to the shared list).
            home / ".azure",
            home / ".kube",
            windir,        # C:\Windows — OS tree
            programdata,   # C:\ProgramData — system-wide app data
        ],
        # override-required broad folders
        "broad": [home / "Videos"],  # Windows' name for macOS "Movies"
        # override-required cloud sync roots (business OneDrive handled by
        # the OneDrive-prefix check in check_mount_path)
        "cloud": [
            home / "OneDrive",     # personal — built into Windows
            home / "iCloudDrive",  # iCloud for Windows
        ],
    }


# On Windows, extend the block lists with the validated Windows set. On
# macOS/Linux this branch never runs, so those platforms are untouched.
if os.name == "nt":
    _win = _windows_exclusions(HOME)
    _EXACT_HARD_BLOCKS += _win["exact"]
    _DEEP_HARD_BLOCKS += _win["deep"]
    _BROAD_FOLDERS += _win["broad"]
    _CLOUD_SYNC_ROOTS += _win["cloud"]


@dataclass(frozen=True)
class OverrideRecord:
    """One override the user activated to permit a mount.

    Logged in the session_start record so audits can show what was
    overridden, when, and why it was deemed broad.
    """
    path: str
    reason: str


class SafetyViolation(Exception):
    """Raised when a mount path is blocked by safety policy."""


def _resolve_safe(p: Path) -> Path | None:
    """Resolve a path tolerantly. Returns None if resolution fails."""
    try:
        return p.resolve()
    except (OSError, RuntimeError):
        return None


def _intersects(a: Path, b: Path) -> bool:
    """True if a equals b, a is inside b, or b is inside a."""
    if a == b:
        return True
    try:
        a.relative_to(b)
        return True
    except ValueError:
        pass
    try:
        b.relative_to(a)
        return True
    except ValueError:
        pass
    return False


def _is_inside_or_eq(needle: Path, root: Path) -> bool:
    """True if needle equals root or needle is inside root."""
    if needle == root:
        return True
    try:
        needle.relative_to(root)
        return True
    except ValueError:
        return False


def check_mount_path(
    host_path: Path,
    profile: Profile,
    allow_broad_mount_flag: bool,
    other_registered_paths: Iterable[Path] = (),
) -> list[OverrideRecord]:
    """Enforce safety policy on a single mount path.

    Returns a list of overrides applied (empty when no override was
    needed). Raises SafetyViolation on hard-block hits, on missing paths,
    or on override-required paths when either gate is closed.
    """
    p = _resolve_safe(host_path)
    if p is None:
        raise SafetyViolation(f"path could not be resolved: {host_path}")
    if not p.exists():
        raise SafetyViolation(f"mount source does not exist: {p}")

    # Tier 1a: exact-match hard blocks
    for blocked in _EXACT_HARD_BLOCKS:
        b = _resolve_safe(blocked)
        if b is not None and p == b:
            raise SafetyViolation(
                f"path {p} is hard-blocked (exact match: {b}); no override available"
            )

    # Tier 1b: deep hard blocks (intersection)
    for blocked in _DEEP_HARD_BLOCKS:
        b = _resolve_safe(blocked)
        if b is None:
            continue
        if _intersects(p, b):
            raise SafetyViolation(
                f"path {p} is hard-blocked (intersects {b}); no override available"
            )

    # Tier 2: override-required reasons accumulate
    overrides: list[OverrideRecord] = []

    for broad in _BROAD_FOLDERS:
        b = _resolve_safe(broad)
        if b is None:
            continue
        # Flag exact match or being inside a broad folder umbrella.
        # Mounting a specific subproject (~/Documents/foo) is broad enough
        # to deserve the override prompt; the override list says so.
        if _is_inside_or_eq(p, b):
            overrides.append(OverrideRecord(
                path=str(p),
                reason=f"broad folder ({b})",
            ))
            break  # one broad-folder reason is enough

    cloud_flagged = False
    for cloud in _CLOUD_SYNC_ROOTS:
        c = _resolve_safe(cloud)
        if c is None:
            continue
        if _is_inside_or_eq(p, c):
            overrides.append(OverrideRecord(
                path=str(p),
                reason=f"cloud sync root ({c})",
            ))
            cloud_flagged = True
            break

    # Business OneDrive uses an org-suffixed folder name (e.g.
    # "OneDrive - Acme"), which the exact-name entry above misses. Treat any
    # HOME-direct-child whose name is "OneDrive" or starts with "OneDrive -"
    # as a cloud sync root. Cross-platform safe — it only adds override
    # gating for a genuinely cloud-synced location.
    if not cloud_flagged:
        home_resolved = _resolve_safe(HOME)
        if home_resolved is not None:
            try:
                first = p.relative_to(home_resolved).parts[0]
            except (ValueError, IndexError):
                first = ""
            if first == "OneDrive" or first.startswith("OneDrive -"):
                overrides.append(OverrideRecord(
                    path=str(p),
                    reason="cloud sync root (OneDrive)",
                ))

    # Parent of any registered mount target
    for registered in other_registered_paths:
        r = _resolve_safe(Path(registered))
        if r is None or r == p:
            continue
        try:
            r.relative_to(p)
            overrides.append(OverrideRecord(
                path=str(p),
                reason=f"parent of registered mount ({r})",
            ))
        except ValueError:
            pass

    if overrides:
        if not profile.allow_broad_mount:
            reasons = "; ".join(o.reason for o in overrides)
            raise SafetyViolation(
                f"path {p} requires broad-mount override but profile "
                f"{profile.name!r} blocks it. Reasons: {reasons}"
            )
        if not allow_broad_mount_flag:
            reasons = "; ".join(o.reason for o in overrides)
            raise SafetyViolation(
                f"path {p} requires broad-mount override; pass "
                f"--allow-broad-mount to opt in. Reasons: {reasons}"
            )

    return overrides
