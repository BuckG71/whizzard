"""`whiz image ...` subcommands.

Stage 18: image build (Stage 1), enriched status (id / created / base
digest / drift), and `image check` against a 30-day staleness threshold
(D-75 superseded — pulled into MVP).
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
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
    image_inspect,
    parse_dockerfile_base_pin,
)

image_app = typer.Typer(help="Manage the execution image.")

# Staleness threshold for `whiz image check`. Hardcoded for MVP per
# D-75-amended; a per-profile override + auto-rebuild policy lands in v1.0.
IMAGE_STALENESS_DAYS = 30


def _dockerfile_path() -> Path:
    """Path to the bundled Dockerfile (Stage 19: package data location)."""
    from importlib.resources import files

    return Path(str(files("whizzard._dockerfiles") / "Dockerfile"))


def _format_age(delta_days: float) -> str:
    if delta_days < 1:
        hours = max(int(delta_days * 24), 0)
        return f"{hours}h"
    return f"{int(delta_days)}d"


@image_app.command("status")
def image_status_cmd(
    image: Annotated[
        str, typer.Option("--image", help="Image name.")
    ] = WHIZZARD_IMAGE,
) -> None:
    """Show current execution image status: id, build date, base digest."""
    if not docker_available():
        console.print("[red]docker not found on PATH[/red]")
        raise typer.Exit(code=127)

    try:
        present = image_exists(image)
    except DockerDaemonError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=125) from e

    if not present:
        console.print(f"[yellow]image[/yellow] {image} is NOT present")
        console.print("build it with: [bold]whiz image build[/bold]")
        return

    try:
        meta = image_inspect(image)
    except DockerDaemonError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=125) from e

    pinned_base = parse_dockerfile_base_pin(_dockerfile_path())

    console.print(f"[green]image[/green] {image} is present")
    if meta is not None:
        now = datetime.now(UTC)
        age_days = (now - meta.created).total_seconds() / 86400.0
        console.print(f"  id:         {meta.id}")
        console.print(
            f"  built:      {meta.created.isoformat()} "
            f"([bold]{_format_age(age_days)}[/bold] ago)"
        )
    if pinned_base is not None:
        console.print(f"  base (pin): {pinned_base}")
    else:
        console.print(
            "  [yellow]base (pin): Dockerfile FROM is not digest-pinned[/yellow]"
        )


@image_app.command("build")
def image_build_cmd(
    image: Annotated[
        str, typer.Option("--image", help="Image tag to build.")
    ] = WHIZZARD_IMAGE,
) -> None:
    """Build the Whizzard execution image from the bundled Dockerfile."""
    # F-H-02: preflight docker availability before invoking the subprocess.
    # Without this, `whiz image build` on a host with no docker CLI raises
    # a raw `FileNotFoundError` traceback at `subprocess.run` instead of
    # the clean exit-127 red-error path every other docker-touching verb
    # uses (image status, run, preset launch, ...).
    if not docker_available():
        console.print("[red]error: docker not found on PATH[/red]")
        raise typer.Exit(code=127)

    dockerfile = _dockerfile_path()
    if not dockerfile.exists():
        console.print(f"[red]Dockerfile not found at {dockerfile}[/red]")
        raise typer.Exit(code=2)

    console.print(f"building [bold]{image}[/bold] from {dockerfile} ...")
    completed = subprocess.run(
        ["docker", "build", "-t", image, "-f", str(dockerfile), str(dockerfile.parent)],
        env=_docker_env(),
    )
    raise typer.Exit(code=completed.returncode)


@image_app.command("check")
def image_check_cmd(
    image: Annotated[
        str, typer.Option("--image", help="Image name.")
    ] = WHIZZARD_IMAGE,
    threshold_days: Annotated[
        int,
        typer.Option(
            "--threshold-days",
            help="Days past build before the image is reported stale.",
        ),
    ] = IMAGE_STALENESS_DAYS,
) -> None:
    """Check whether the image is stale (built >threshold days ago).

    Exit codes: 0 = fresh, 1 = stale, 2 = image not built,
    125 = docker daemon unreachable, 127 = docker CLI missing.
    """
    if not docker_available():
        console.print("[red]error: docker not found on PATH[/red]")
        raise typer.Exit(code=127)

    try:
        meta = image_inspect(image)
    except DockerDaemonError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=125) from e

    if meta is None:
        console.print(f"[yellow]image[/yellow] {image} is NOT built")
        console.print("build it with: [bold]whiz image build[/bold]")
        raise typer.Exit(code=2)

    now = datetime.now(UTC)
    age_days = (now - meta.created).total_seconds() / 86400.0

    if age_days > threshold_days:
        console.print(
            f"[red]stale[/red] {image} built {_format_age(age_days)} ago "
            f"(threshold {threshold_days}d)"
        )
        console.print("rebuild with: [bold]whiz image build[/bold]")
        raise typer.Exit(code=1)

    console.print(
        f"[green]fresh[/green] {image} built {_format_age(age_days)} ago "
        f"(threshold {threshold_days}d)"
    )
