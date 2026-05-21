"""`whiz hermes ...` subcommands (Stage 8)."""

from __future__ import annotations

from typing import Annotated

import typer

from whizzard.adapters import (
    HermesProfileExistsError,
    HermesProfileNameError,
    HermesProfileSourceMissingError,
    create_hermes_profile,
)
from whizzard.cli._shared import console

hermes_app = typer.Typer(help="Hermes harness operations (Stage 8).")
hermes_profile_app = typer.Typer(help="Manage Hermes profiles for use in Whizzard cells.")
hermes_app.add_typer(hermes_profile_app, name="profile")


@hermes_profile_app.command("create")
def hermes_profile_create_cmd(
    name: Annotated[
        str,
        typer.Argument(help="Profile name. Creates ~/.hermes-<name>/."),
    ],
    clone_from: Annotated[
        str | None,
        typer.Option(
            "--clone-from",
            help="Source profile to clone (e.g. 'default' = ~/.hermes). "
                 "Mutually exclusive with --no-clone.",
        ),
    ] = None,
    no_clone: Annotated[
        bool,
        typer.Option(
            "--no-clone",
            help="Create an empty profile (skip cloning).",
        ),
    ] = False,
) -> None:
    """Create a Hermes profile for use in a Whizzard cell.

    Bare command clones from `default` (~/.hermes) if it exists; degrades to
    an empty profile otherwise. Explicit --clone-from selects a different
    source; --no-clone forces an empty profile. auth.json and per-instance
    runtime state are always excluded from clones (D-80, D-86).
    """
    if clone_from is not None and no_clone:
        console.print("[red]--clone-from and --no-clone are mutually exclusive[/red]")
        raise typer.Exit(code=2)

    try:
        result = create_hermes_profile(name, clone_from=clone_from, no_clone=no_clone)
    except HermesProfileNameError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=2) from e
    except HermesProfileExistsError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1) from e
    except HermesProfileSourceMissingError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=2) from e

    if result.source is None:
        console.print(f"[green]created[/green] empty profile at {result.path}")
    else:
        console.print(f"[green]created[/green] profile at {result.path}")
        console.print(f"  cloned from {result.source} (auth.json and runtime state excluded)")
    console.print(
        "Add a harness entry in ~/.whizzard/config/harnesses.json referencing "
        f"hermes_home: {result.path} to use it."
    )
