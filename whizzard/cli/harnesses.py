"""`whiz harnesses ...` subcommands."""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.table import Table

from whizzard.cli._shared import console
from whizzard.harness_config import (
    HARNESSES_FILE,
    HarnessConfigError,
    default_harnesses,
    load_harnesses,
)

harnesses_app = typer.Typer(help="Inspect the harness registry.")


@harnesses_app.command("list")
def harnesses_list_cmd() -> None:
    """List configured harnesses (from harnesses.json or bundled defaults)."""
    try:
        harnesses = load_harnesses()
    except HarnessConfigError as e:
        console.print(f"[red]error loading harnesses.json: {e}[/red]")
        raise typer.Exit(code=2) from e

    source = "user config" if HARNESSES_FILE.exists() else "bundled defaults"
    title = f"Harnesses ({source})"
    table = Table(title=title)
    table.add_column("Name")
    table.add_column("Type")
    table.add_column("Start command")
    table.add_column("Wrap-up command")
    table.add_column("Description")

    for name in sorted(harnesses):
        spec = harnesses[name]
        table.add_row(
            name,
            spec.get("type", ""),
            spec.get("start_command", ""),
            spec.get("wrap_up_command", "—"),
            spec.get("description", ""),
        )
    console.print(table)


@harnesses_app.command("init")
def harnesses_init_cmd(
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite an existing harnesses.json."),
    ] = False,
) -> None:
    """Write the bundled default harnesses to ~/.whizzard/config/harnesses.json."""
    if HARNESSES_FILE.exists() and not force:
        console.print(
            f"[yellow]{HARNESSES_FILE} already exists.[/yellow] "
            "use [bold]--force[/bold] to overwrite."
        )
        raise typer.Exit(code=1)

    payload = {"schema_version": 1, "harnesses": default_harnesses()}
    HARNESSES_FILE.write_text(json.dumps(payload, indent=2) + "\n")
    console.print(f"[green]wrote[/green] {HARNESSES_FILE}")
    console.print(
        "edit it to add new harnesses. "
        "select one at run time with [bold]whizzard run --harness <name>[/bold]."
    )
