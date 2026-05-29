"""`whiz hermes ...` subcommands (Stages 8 + 19)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Annotated

import typer

from whizzard.adapters import (
    HermesProfileExistsError,
    HermesProfileNameError,
    HermesProfileSourceMissingError,
    create_hermes_profile,
)
from whizzard.cli._shared import console
from whizzard.docker_cmd import (
    WHIZZARD_HERMES_IMAGE,
    _docker_env,
    docker_available,
)

hermes_app = typer.Typer(help="Hermes harness operations (Stage 8).")
hermes_profile_app = typer.Typer(help="Manage Hermes profiles for use in Whizzard cells.")
hermes_image_app = typer.Typer(help="Manage the Hermes execution image.")
hermes_app.add_typer(hermes_profile_app, name="profile")
hermes_app.add_typer(hermes_image_app, name="image")


def _hermes_dockerfile_path() -> Path:
    """Path to the bundled Dockerfile.hermes (Stage 19 package data)."""
    from importlib.resources import files

    return Path(str(files("whizzard._dockerfiles") / "Dockerfile.hermes"))


def _hermes_build_context() -> Path:
    """Docker build context for Dockerfile.hermes.

    The Dockerfile.hermes does ``COPY whizzard/mcp_server.py /opt/whiz/...``,
    so the build context must be the directory that contains ``whizzard/``.
    In dev mode that's the repo root; in an installed package that's
    ``site-packages/``. Either way ``Path(whizzard.__file__).parent.parent``
    points at the right directory.
    """
    import whizzard

    return Path(whizzard.__file__).resolve().parent.parent


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


@hermes_image_app.command("build")
def hermes_image_build_cmd(
    image: Annotated[
        str, typer.Option("--image", help="Image tag to build.")
    ] = WHIZZARD_HERMES_IMAGE,
) -> None:
    """Build the Hermes execution image from the bundled Dockerfile.hermes.

    Stage 19 / D-131: Hermes is the only supported harness today; ``whiz init``
    builds this image as part of its mandatory setup. Run-it-yourself path
    for users who want to rebuild after an upstream Hermes ref bump.
    """
    if not docker_available():
        console.print("[red]error: docker not found on PATH[/red]")
        raise typer.Exit(code=127)

    dockerfile = _hermes_dockerfile_path()
    if not dockerfile.exists():
        console.print(f"[red]Dockerfile.hermes not found at {dockerfile}[/red]")
        raise typer.Exit(code=2)

    context = _hermes_build_context()
    console.print(f"building [bold]{image}[/bold] from {dockerfile} ...")
    console.print(f"  build context: {context}")
    completed = subprocess.run(
        ["docker", "build", "-t", image, "-f", str(dockerfile), str(context)],
        env=_docker_env(),
    )
    raise typer.Exit(code=completed.returncode)
