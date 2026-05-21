"""`whiz profiles ...` subcommands."""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.table import Table

from whizzard.cli._shared import console
from whizzard.config import (
    PROFILES_FILE,
    ProfileConfigError,
    default_profiles,
    list_profiles,
)

profiles_app = typer.Typer(help="Inspect available profiles.")


@profiles_app.command("list")
def profiles_list_cmd() -> None:
    """List available profiles."""
    try:
        profiles = list_profiles()
    except ProfileConfigError as e:
        console.print(f"[red]error loading profiles.json: {e}[/red]")
        raise typer.Exit(code=2) from e

    source = "user config" if PROFILES_FILE.exists() else "bundled defaults"
    title = f"Profiles ({source}: {PROFILES_FILE if PROFILES_FILE.exists() else 'whizzard.config._DEFAULT_PROFILES'})"
    table = Table(title=title)
    table.add_column("Name")
    table.add_column("Network")
    table.add_column("Duration")
    table.add_column("Broad-mount override")
    table.add_column("Description")

    for p in profiles:
        duration = "unlimited" if p.duration_seconds is None else f"{p.duration_seconds // 60} min"
        table.add_row(
            p.name,
            "on" if p.network_enabled else "off",
            duration,
            "allowed" if p.allow_broad_mount else "blocked",
            p.description,
        )
    console.print(table)


@profiles_app.command("init")
def profiles_init_cmd(
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite an existing profiles.json."),
    ] = False,
) -> None:
    """Write the bundled default profiles to ~/.whizzard/config/profiles.json.

    Useful for starting customization — copy the defaults, then edit.
    """
    if PROFILES_FILE.exists() and not force:
        console.print(
            f"[yellow]{PROFILES_FILE} already exists.[/yellow] "
            "use [bold]--force[/bold] to overwrite."
        )
        raise typer.Exit(code=1)

    payload = {
        "schema_version": 1,
        "profiles": {
            p.name: {
                "network_enabled": p.network_enabled,
                "duration_seconds": p.duration_seconds,
                "allow_broad_mount": p.allow_broad_mount,
                "description": p.description,
            }
            for p in default_profiles().values()
        },
    }
    PROFILES_FILE.write_text(json.dumps(payload, indent=2) + "\n")
    console.print(f"[green]wrote[/green] {PROFILES_FILE}")
    console.print("edit it to customize. existing profile names are recognized by `whizzard run --profile <name>`.")
