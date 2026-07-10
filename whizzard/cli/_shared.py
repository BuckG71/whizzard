"""Shared CLI helpers.

`console` is the project-wide Rich Console used by every CLI module so error /
status styling is consistent. Importing one shared instance keeps all output
going through the same configuration.
"""

from __future__ import annotations

import contextlib
import sys

from rich.console import Console

# On Windows the default stdout/stderr encoding is the locale code page
# (cp1252), which can't encode the arrows (→), em-dashes (—), or box characters
# Rich and the CLI emit — so ANY non-ASCII output raises UnicodeEncodeError when
# stdout isn't a UTF-8 terminal (piped, redirected, CI, or a legacy console).
# `whiz --help` crashed this way on Windows. Force UTF-8 so output renders
# correctly on modern terminals and degrades to harmless mojibake on legacy
# ones — never a crash. No-op on POSIX (already UTF-8); guarded so a non-
# reconfigurable stream (e.g. a test capture) is left alone.
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError):
            _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

console = Console()
