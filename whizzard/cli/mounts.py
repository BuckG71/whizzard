"""`whiz mounts ...` subcommands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from whizzard.cli._shared import console
from whizzard.config import Profile
from whizzard.mounts import (
    MOUNTS_FILE,
    MountRegistryError,
    _validate_mount_name,
    load_mount_specs,
    load_mounts,
    write_mount_specs,
)
from whizzard.safety import SafetyViolation, check_mount_path, hard_block_reason

mounts_app = typer.Typer(help="Inspect the mount registry.")

# Permissive throwaway profile for the structural mount check (broad/cloud
# advisory only — per-profile gating happens at launch). Mirrors the wizard's
# _WIZARD_CHECK_PROFILE so `whiz mounts add` and the wizard apply the same model.
_ADD_CHECK_PROFILE = Profile(
    name="mounts-add-check",
    network_enabled=True,
    duration_seconds=None,
    allow_broad_mount=True,
)


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


@mounts_app.command("add")
def mounts_add_cmd(
    path: Annotated[
        str | None,
        typer.Argument(help="Host folder to register."),
    ] = None,
    name: Annotated[
        str | None,
        typer.Option("--name", "-n", help="Name to refer to it by (default: the folder's own name)."),
    ] = None,
    mode: Annotated[
        str,
        typer.Option("--mode", "-m", help="Default access mode: 'ro' or 'rw'."),
    ] = "ro",
    create: Annotated[
        bool,
        typer.Option("--create", help="Create the folder if it doesn't exist."),
    ] = False,
    pick: Annotated[
        bool,
        typer.Option("--pick", help="Choose the folder with a native file dialog instead of typing a path."),
    ] = False,
) -> None:
    """Register a host folder as a named mount.

    Applies the same safety model as the wizard: hard-blocked paths (e.g.
    ``~/.ssh``, ``/``) are refused, broad/cloud locations get an advisory, and
    the registered mode is the ceiling — a launch can narrow it, never widen it.
    """
    if pick:
        from whizzard._platform import pick_directory

        chosen = pick_directory()
        if chosen is None:
            console.print(
                "[yellow]no folder selected[/yellow] (cancelled, or no file "
                "dialog is available here). Provide a path instead."
            )
            raise typer.Exit(code=1)
        path = chosen
    if not path:
        console.print("[red]error: provide a folder path (or use --pick).[/red]")
        raise typer.Exit(code=2)
    if mode not in ("ro", "rw"):
        console.print(f"[red]error: --mode must be 'ro' or 'rw', got {mode!r}.[/red]")
        raise typer.Exit(code=2)

    resolved = Path(path).expanduser()

    # Hard-blocked paths are refused up front (no profile can override them).
    block = hard_block_reason(resolved)
    if block is not None:
        console.print(
            f"[red]can't add that folder:[/red] {resolved} is hard-blocked "
            f"({block}); no profile can mount it."
        )
        raise typer.Exit(code=2)

    if not resolved.exists():
        if not create:
            console.print(
                f"[red]error: folder does not exist:[/red] {resolved}\n"
                "pass [bold]--create[/bold] to make it."
            )
            raise typer.Exit(code=2)
        try:
            resolved.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            console.print(f"[red]couldn't create that folder:[/red] {e}")
            raise typer.Exit(code=2) from e
        console.print(f"  [green]✓[/green] created {resolved}")

    derived = (name or resolved.name).strip().lower().replace(" ", "-")
    if not derived:
        console.print(
            f"[red]error: couldn't derive a name from {path!r}; pass --name.[/red]"
        )
        raise typer.Exit(code=2)
    try:
        _validate_mount_name(derived)
    except MountRegistryError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=2) from e

    # Read the raw registry so existing entries keep their stored form (a
    # load_mounts round-trip would canonicalize every other entry's path).
    try:
        specs = load_mount_specs()
    except MountRegistryError as e:
        console.print(f"[red]error loading mounts.json: {e}[/red]")
        raise typer.Exit(code=2) from e
    if derived in specs:
        console.print(
            f"[red]error: a mount named {derived!r} already exists.[/red] "
            "pick a different --name."
        )
        raise typer.Exit(code=2)

    # Broad/cloud advisory — informational; per-profile gating is enforced at
    # launch. Hard blocks were already rejected and the path now exists, so the
    # except is only reached on a TOCTOU race (path removed mid-command).
    other = [
        Path(s["host_path"]).expanduser().resolve()
        for s in specs.values()
        if s.get("host_path")
    ]
    try:
        advisories = check_mount_path(
            resolved.resolve(),
            _ADD_CHECK_PROFILE,
            allow_broad_mount_flag=True,
            other_registered_paths=other,
        )
    except SafetyViolation as e:
        console.print(f"[red]can't add that folder:[/red] {e}")
        raise typer.Exit(code=2) from e
    if advisories:
        reasons = "; ".join(a.reason for a in advisories)
        console.print(
            f"  [yellow]note:[/yellow] broad or sensitive location ({reasons}); "
            "launching with it needs a profile that allows broad mounts."
        )

    # Store the path as the user gave it (preserving ~), matching the wizard.
    specs[derived] = {"host_path": path, "default_mode": mode, "description": ""}
    write_mount_specs(specs)
    console.print(
        f"  [green]✓[/green] registered [bold]{derived}[/bold] → {resolved} "
        f"({mode}) in {MOUNTS_FILE}"
    )
