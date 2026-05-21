"""`whiz sessions ...` subcommands."""

from __future__ import annotations

from typing import Annotated

import typer

from whizzard.cli._shared import console
from whizzard.session_log import SESSIONS_LOG

sessions_app = typer.Typer(help="Inspect the session log.")


@sessions_app.command("tail")
def sessions_tail_cmd(
    n: Annotated[
        int,
        typer.Option("-n", help="Number of recent log lines to show."),
    ] = 10,
) -> None:
    """Show the last N lines of the session log."""
    if not SESSIONS_LOG.exists():
        console.print(f"[yellow]no session log yet[/yellow] at {SESSIONS_LOG}")
        return

    lines = SESSIONS_LOG.read_text().splitlines()
    for line in lines[-n:]:
        console.print(line)


@sessions_app.command("path")
def sessions_path_cmd() -> None:
    """Print the path to the session log."""
    console.print(str(SESSIONS_LOG))
