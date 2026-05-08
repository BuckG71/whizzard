"""Airlock/Whizzard CLI entry point."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from whizzard.config import (
    PROFILES_FILE,
    ProfileConfigError,
    default_profiles,
    ensure_whizzard_home,
    get_profile,
    list_profiles,
)
from whizzard.docker_cmd import (
    WHIZZARD_IMAGE,
    _docker_env,
    build_run_argv,
    docker_available,
    image_exists,
    run_shell,
)
from whizzard.mounts import (
    MOUNTS_FILE,
    Mount,
    MountMode,
    MountRegistryError,
    basic_path_sanity_check,
    load_mounts,
    resolve_mount_spec,
)


app = typer.Typer(
    name="whizzard",
    help="Airlock/Whizzard — local capability governance for AI agents.",
    no_args_is_help=True,
    add_completion=False,
)
profiles_app = typer.Typer(help="Inspect available profiles.")
image_app = typer.Typer(help="Manage the execution image.")
mounts_app = typer.Typer(help="Inspect the mount registry.")
app.add_typer(profiles_app, name="profiles")
app.add_typer(image_app, name="image")
app.add_typer(mounts_app, name="mounts")

console = Console()


@app.callback()
def _bootstrap() -> None:
    """Runs before every subcommand. Ensures ~/.whizzard/ scaffold exists."""
    ensure_whizzard_home()


@app.command("run")
def run_cmd(
    profile: Annotated[
        str,
        typer.Option("--profile", "-p", help="Profile name (e.g. default, build)."),
    ] = "default",
    mount: Annotated[
        list[str] | None,
        typer.Option(
            "--mount", "-m",
            help="Registered mount name, optionally with mode "
                 "(e.g. project-alpha or project-alpha:ro). Repeatable.",
        ),
    ] = None,
    image: Annotated[
        str,
        typer.Option("--image", help="Container image to use."),
    ] = WHIZZARD_IMAGE,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Show what would happen without launching the container.",
        ),
    ] = False,
) -> None:
    """Launch a contained shell session under the given profile."""
    try:
        prof = get_profile(profile)
    except KeyError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=2)
    except ProfileConfigError as e:
        console.print(f"[red]error loading profiles.json: {e}[/red]")
        raise typer.Exit(code=2)

    resolved: list[tuple[Mount, MountMode]] = []
    if mount:
        try:
            registry = load_mounts()
        except MountRegistryError as e:
            console.print(f"[red]error loading mounts.json: {e}[/red]")
            raise typer.Exit(code=2)
        try:
            for spec in mount:
                m, mode = resolve_mount_spec(spec, registry)
                basic_path_sanity_check(m.host_path)
                resolved.append((m, mode))
        except MountRegistryError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(code=2)

    duration = "unlimited" if prof.duration_seconds is None else f"{prof.duration_seconds // 60} min"
    if dry_run:
        console.print("[yellow]DRY RUN[/yellow] — no container will be launched.\n")
    console.print(f"[bold]Airlock Profile:[/bold] {prof.name.upper()}")
    console.print(f"[bold]Network:[/bold] {'enabled' if prof.network_enabled else 'disabled'}")
    console.print(f"[bold]Duration:[/bold] {duration}")
    console.print(f"[bold]Broad-mount override:[/bold] {'allowed' if prof.allow_broad_mount else 'blocked'}")
    console.print(f"[bold]Image:[/bold] {image}")
    if resolved:
        console.print("[bold]Mounts:[/bold]")
        for m, mode in resolved:
            console.print(f"  {m.name} ({mode}): {m.host_path} → {m.container_path()}")
    else:
        console.print("[bold]Mounts:[/bold] none")
    console.print()

    if dry_run:
        import shlex
        argv = build_run_argv(prof, image=image, resolved_mounts=resolved)
        console.print("[bold]docker invocation that would run:[/bold]")
        console.print("  " + " ".join(shlex.quote(a) for a in argv))
        # Note: image existence is NOT checked here — dry-run reports intent.
        # If the image is missing, an actual `whizzard run` would surface that.
        raise typer.Exit(code=0)

    result = run_shell(prof, image=image, resolved_mounts=resolved)
    raise typer.Exit(code=result.exit_code)


@profiles_app.command("list")
def profiles_list_cmd() -> None:
    """List available profiles."""
    try:
        profiles = list_profiles()
    except ProfileConfigError as e:
        console.print(f"[red]error loading profiles.json: {e}[/red]")
        raise typer.Exit(code=2)

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
    import json

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


@mounts_app.command("list")
def mounts_list_cmd() -> None:
    """List registered mounts."""
    try:
        registry = load_mounts()
    except MountRegistryError as e:
        console.print(f"[red]error loading mounts.json: {e}[/red]")
        raise typer.Exit(code=2)

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

    if image_exists(image):
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
    import subprocess
    from pathlib import Path

    dockerfile = Path(__file__).resolve().parent.parent / "docker" / "Dockerfile"
    if not dockerfile.exists():
        console.print(f"[red]Dockerfile not found at {dockerfile}[/red]")
        raise typer.Exit(code=2)

    console.print(f"building [bold]{image}[/bold] from {dockerfile} ...")
    completed = subprocess.run(
        ["docker", "build", "-t", image, "-f", str(dockerfile), str(dockerfile.parent)],
        env=_docker_env(),
    )
    raise typer.Exit(code=completed.returncode)


if __name__ == "__main__":
    app()
