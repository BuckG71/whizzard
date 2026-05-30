"""Atomic file-write helper.

A crash mid-``write_text`` (or a SIGINT during ``whiz init``) can leave
a config file truncated; the next launch then reads invalid JSON and
fails before any recovery code runs. The fix is to write to a
sibling tempfile and ``Path.replace`` it over the target — ``replace``
is atomic on POSIX (rename(2)) so the file is either the full old
contents or the full new contents, never half.

Used by every config write (``profiles.json``, ``mounts.json``,
``harnesses.json``, ``presets.json``), the per-session ``snapshot.json``,
and the host-only request resolutions store.
"""

from __future__ import annotations

from pathlib import Path


def atomic_write_text(path: Path, content: str) -> None:
    """Atomically write ``content`` to ``path``.

    Creates the parent directory if missing. Writes to a sibling
    ``.<name>.tmp`` first and ``replace``s it over the target. If the
    write or rename raises, the original file (if any) is untouched.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(content)
    tmp.replace(path)
