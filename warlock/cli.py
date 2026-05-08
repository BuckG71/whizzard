"""Airlock/Warlock CLI entry point."""

from __future__ import annotations

import sys
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from warlock.config import (
    ensure_warlock_home,
    get_profile,
    list_profiles,
)
from warlock.docker_cmd import (
    WARLOCK_IMAGE,
    docker_available,
    image_exists,
    run_shell,
)


app = typer.Typer(
    name="warlock",
    help="Airlock/Warlock — local capability governance for AI agents.",
    no_args_is_help=True,
    add_completion=False,
)
profiles_app = typer.Typer(help="Inspect available profiles.")
image_app = typer.Typer(help="Manage the execution image.")
app.add_typer(profiles_app, name="profiles")
app.add_typer(image_app, name="image")

console = Console()


@app.command("run")
def run_cmd(
    profile: Annotated[
        str,
        typer.Option("--profile", "-p", help="Profile name (e.g. default, build)."),
    ] = "default",
    image: Annotated[
        str,
        typer.Option("--image", help="Container image to use."),
    ] = WARLOCK_IMAGE,
) -> None:
    """Launch a contained shell session under the given profile."""
    ensure_warlock_home()

    try:
        prof = get_profile(profile)
    except KeyError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=2)

    duration = "unlimited" if prof.duration_seconds is None else f"{prof.duration_seconds // 60} min"
    console.print(f"[bold]Airlock Profile:[/bold] {prof.name.upper()}")
    console.print(f"[bold]Network:[/bold] {'enabled' if prof.network_enabled else 'disabled'}")
    console.print(f"[bold]Duration:[/bold] {duration}")
    console.print(f"[bold]Image:[/bold] {image}")
    console.print()

    result = run_shell(prof, image=image)
    raise typer.Exit(code=result.exit_code)


@profiles_app.command("list")
def profiles_list_cmd() -> None:
    """List available profiles."""
    table = Table(title="Profiles")
    table.add_column("Name")
    table.add_column("Network")
    table.add_column("Duration")
    table.add_column("Broad-mount override")
    table.add_column("Description")

    for p in list_profiles():
        duration = "unlimited" if p.duration_seconds is None else f"{p.duration_seconds // 60} min"
        table.add_row(
            p.name,
            "on" if p.network_enabled else "off",
            duration,
            "allowed" if p.allow_broad_mount else "blocked",
            p.description,
        )
    console.print(table)


@image_app.command("status")
def image_status_cmd(
    image: Annotated[
        str, typer.Option("--image", help="Image name.")
    ] = WARLOCK_IMAGE,
) -> None:
    """Show current execution image status."""
    if not docker_available():
        console.print("[red]docker not found on PATH[/red]")
        raise typer.Exit(code=127)

    if image_exists(image):
        console.print(f"[green]image[/green] {image} is present")
    else:
        console.print(f"[yellow]image[/yellow] {image} is NOT present")
        console.print("build it with: [bold]warlock image build[/bold]")


@image_app.command("build")
def image_build_cmd(
    image: Annotated[
        str, typer.Option("--image", help="Image tag to build.")
    ] = WARLOCK_IMAGE,
) -> None:
    """Build the Warlock execution image from docker/Dockerfile."""
    import subprocess
    from pathlib import Path

    dockerfile = Path(__file__).resolve().parent.parent / "docker" / "Dockerfile"
    if not dockerfile.exists():
        console.print(f"[red]Dockerfile not found at {dockerfile}[/red]")
        raise typer.Exit(code=2)

    console.print(f"building [bold]{image}[/bold] from {dockerfile} ...")
    completed = subprocess.run(
        ["docker", "build", "-t", image, "-f", str(dockerfile), str(dockerfile.parent)],
    )
    raise typer.Exit(code=completed.returncode)


if __name__ == "__main__":
    app()
