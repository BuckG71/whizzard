"""Shared CLI helpers.

`console` is the project-wide Rich Console used by every CLI module so error /
status styling is consistent. Importing one shared instance keeps all output
going through the same configuration.
"""

from __future__ import annotations

from rich.console import Console

console = Console()
