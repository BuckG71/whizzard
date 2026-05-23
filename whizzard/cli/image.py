"""`whiz image ...` subcommands."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Annotated

import typer

from whizzard.cli._shared import console
from whizzard.docker_cmd import (
    WHIZZARD_IMAGE,
    DockerDaemonError,
    _docker_env,
    docker_available,
    image_exists,
)

image_app = typer.Typer(help="Manage the execution image.")


@image_app.command("status")
def image_status_cmd(
    image: Annotated[
        str, typer.Option("--image", help="Image name.")
    ] = WHIZZARD_IMAGE,
) -> None:
    """Show current execution image status."""
    if not docker_available():
        console.print("[red]docker not found on PATH[/red]")
        raise typer.Exit(code=127)

    try:
        present = image_exists(image)
    except DockerDaemonError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=125) from e
    if present:
        console.print(f"[green]image[/green] {image} is present")
    else:
        console.print(f"[yellow]image[/yellow] {image} is NOT present")
        console.print("build it with: [bold]whizzard image build[/bold]")


@image_app.command("build")
def image_build_cmd(
    image: Annotated[
        str, typer.Option("--image", help="Image tag to build.")
    ] = WHIZZARD_IMAGE,
) -> None:
    """Build the Whizzard execution image from docker/Dockerfile."""
    dockerfile = Path(__file__).resolve().parent.parent.parent / "docker" / "Dockerfile"
    if not dockerfile.exists():
        console.print(f"[red]Dockerfile not found at {dockerfile}[/red]")
        raise typer.Exit(code=2)

    console.print(f"building [bold]{image}[/bold] from {dockerfile} ...")
    completed = subprocess.run(
        ["docker", "build", "-t", image, "-f", str(dockerfile), str(dockerfile.parent)],
        env=_docker_env(),
    )
    raise typer.Exit(code=completed.returncode)
