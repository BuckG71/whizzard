"""`whiz mounts ...` subcommands."""

from __future__ import annotations

import typer
from rich.table import Table

from whizzard.cli._shared import console
from whizzard.mounts import MOUNTS_FILE, MountRegistryError, load_mounts

mounts_app = typer.Typer(help="Inspect the mount registry.")


@mounts_app.command("list")
def mounts_list_cmd() -> None:
    """List registered mounts."""
    try:
        registry = load_mounts()
    except MountRegistryError as e:
        console.print(f"[red]error loading mounts.json: {e}[/red]")
        raise typer.Exit(code=2) from e

    if not registry:
        console.print(
            "[yellow]no mounts registered[/yellow]\n"
            f"create [bold]{MOUNTS_FILE}[/bold] to register named host paths.\n"
            "see [bold]config/mounts.json.example[/bold] in the repo for the schema."
        )
        return

    table = Table(title="Registered Mounts")
    table.add_column("Name")
    table.add_column("Host path")
    table.add_column("Default mode")
    table.add_column("Description")

    for m in sorted(registry.values(), key=lambda x: x.name):
        table.add_row(m.name, str(m.host_path), m.default_mode, m.description)
    console.print(table)
