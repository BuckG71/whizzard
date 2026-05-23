"""`whiz preset ...` subcommands (Stage 10).

Preset machinery and the four user-facing commands: list, show, init, launch.
`launch` shares the launch core with `whiz run` via `whizzard.cli._launch`.
"""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.table import Table

from whizzard.cli._launch import _perform_launch
from whizzard.cli._shared import console
from whizzard.config import ProfileConfigError, list_profiles
from whizzard.docker_cmd import WHIZZARD_IMAGE
from whizzard.harness_config import HarnessConfigError, load_harnesses
from whizzard.mounts import MountRegistryError, load_mounts
from whizzard.preset_config import (
    PRESETS_FILE,
    Preset,
    PresetConfigError,
    default_presets,
    load_presets,
    validate_references,
)

preset_app = typer.Typer(help="Manage and launch presets (Stage 10).")


def _harness_platforms_map() -> dict[str, set[str]]:
    """Build {harness_name: set(platforms)} from harnesses.json for preset
    cross-reference validation per D-89 amended."""
    try:
        harnesses = load_harnesses()
    except HarnessConfigError:
        return {}
    return {
        name: set(spec.get("platforms") or [])
        for name, spec in harnesses.items()
    }


def _validate_loaded_presets(presets: dict[str, Preset]) -> None:
    """Run strict cross-reference validation. Surface PresetConfigError as
    a clean CLI error and exit. Used by preset-related commands."""
    try:
        profile_names = {p.name for p in list_profiles()}
    except ProfileConfigError as e:
        console.print(f"[red]error loading profiles.json: {e}[/red]")
        raise typer.Exit(code=2) from e
    try:
        harness_names = set(load_harnesses())
    except HarnessConfigError as e:
        console.print(f"[red]error loading harnesses.json: {e}[/red]")
        raise typer.Exit(code=2) from e
    try:
        mount_names = set(load_mounts())
    except MountRegistryError as e:
        console.print(f"[red]error loading mounts.json: {e}[/red]")
        raise typer.Exit(code=2) from e
    try:
        validate_references(
            presets,
            profile_names=profile_names,
            harness_names=harness_names,
            mount_names=mount_names,
            harness_platforms=_harness_platforms_map(),
        )
    except PresetConfigError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=2) from e


@preset_app.command("list")
def preset_list_cmd() -> None:
    """List configured presets."""
    try:
        presets = load_presets()
    except PresetConfigError as e:
        console.print(f"[red]error loading presets.json: {e}[/red]")
        raise typer.Exit(code=2) from e
    _validate_loaded_presets(presets)

    source = "user config" if PRESETS_FILE.exists() else "bundled defaults"
    title = f"Presets ({source})"
    table = Table(title=title)
    table.add_column("Name")
    table.add_column("Profile")
    table.add_column("Harness")
    table.add_column("Mounts")
    table.add_column("Platforms")
    table.add_column("Description")

    for name in sorted(presets):
        p = presets[name]
        table.add_row(
            p.name,
            p.profile,
            p.harness,
            ", ".join(p.mounts) or "(none)",
            ", ".join(p.platforms) or "(none)",
            p.description,
        )
    console.print(table)


@preset_app.command("show")
def preset_show_cmd(
    name: Annotated[str, typer.Argument(help="Preset name to inspect.")],
) -> None:
    """Show the resolved configuration for one preset."""
    try:
        presets = load_presets()
    except PresetConfigError as e:
        console.print(f"[red]error loading presets.json: {e}[/red]")
        raise typer.Exit(code=2) from e
    if name not in presets:
        available = ", ".join(sorted(presets)) or "(none)"
        console.print(f"[red]unknown preset {name!r}. Available: {available}[/red]")
        raise typer.Exit(code=2)
    _validate_loaded_presets(presets)
    p = presets[name]
    console.print(f"[bold]Preset:[/bold] {p.name}")
    console.print(f"[bold]Description:[/bold] {p.description or '(none)'}")
    console.print(f"[bold]Profile:[/bold] {p.profile}")
    console.print(f"[bold]Harness:[/bold] {p.harness}")
    console.print(f"[bold]Mounts:[/bold] {', '.join(p.mounts) or '(none)'}")
    console.print(f"[bold]Platforms:[/bold] {', '.join(p.platforms) or '(none — inherit harness ceiling)'}")
    if p.overrides("duration_seconds"):
        d = "unlimited" if p.duration_seconds is None else f"{p.duration_seconds // 60} min"
        console.print(f"[bold]Duration override:[/bold] {d}")
    if p.overrides("idle_timeout_seconds"):
        i = "unlimited" if p.idle_timeout_seconds is None else f"{p.idle_timeout_seconds // 60} min"
        console.print(f"[bold]Idle-timeout override:[/bold] {i}")
    if p.overrides("allow_broad_mount"):
        console.print(f"[bold]Broad-mount override:[/bold] {'allowed' if p.allow_broad_mount else 'blocked'}")


@preset_app.command("init")
def preset_init_cmd(
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite an existing presets.json."),
    ] = False,
) -> None:
    """Write the bundled default presets to ~/.whizzard/config/presets.json."""
    if PRESETS_FILE.exists() and not force:
        console.print(
            f"[yellow]{PRESETS_FILE} already exists.[/yellow] "
            "use [bold]--force[/bold] to overwrite."
        )
        raise typer.Exit(code=1)

    # Render bundled defaults as a JSON-serializable dict (Preset → dict).
    presets_dict = {}
    for name, preset in default_presets().items():
        entry: dict = {
            "profile": preset.profile,
            "harness": preset.harness,
            "mounts": list(preset.mounts),
            "platforms": list(preset.platforms),
            "description": preset.description,
        }
        # Only include override fields when explicitly set; preserves the
        # omit-to-inherit semantic.
        if preset.overrides("duration_seconds"):
            entry["duration_seconds"] = preset.duration_seconds
        if preset.overrides("idle_timeout_seconds"):
            entry["idle_timeout_seconds"] = preset.idle_timeout_seconds
        if preset.overrides("allow_broad_mount"):
            entry["allow_broad_mount"] = preset.allow_broad_mount
        presets_dict[name] = entry

    payload = {"schema_version": 1, "presets": presets_dict}
    PRESETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PRESETS_FILE.write_text(json.dumps(payload, indent=2) + "\n")
    console.print(f"[green]wrote[/green] {PRESETS_FILE}")
    console.print(
        "edit it to customize. launch any registered preset with "
        "[bold]whizzard preset launch <name>[/bold]."
    )


@preset_app.command("launch")
def preset_launch_cmd(
    name: Annotated[str, typer.Argument(help="Preset name to launch.")],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview without launching."),
    ] = False,
    image: Annotated[
        str,
        typer.Option("--image", help="Container image to use."),
    ] = WHIZZARD_IMAGE,
    allow_ephemeral: Annotated[
        bool,
        typer.Option(
            "--allow-ephemeral",
            help="Opt in to launching an agent harness without HERMES_HOME "
                 "(memories/skills ephemeral with the container).",
        ),
    ] = False,
) -> None:
    """Launch a session using the named preset."""
    try:
        presets = load_presets()
    except PresetConfigError as e:
        console.print(f"[red]error loading presets.json: {e}[/red]")
        raise typer.Exit(code=2) from e
    if name not in presets:
        available = ", ".join(sorted(presets)) or "(none)"
        console.print(f"[red]unknown preset {name!r}. Available: {available}[/red]")
        raise typer.Exit(code=2)
    _validate_loaded_presets(presets)
    preset = presets[name]

    # Preset launch always implicitly authorizes the second gate of D-46
    # (the CLI --allow-broad-mount equivalent). The preset itself is the
    # user's persistent declaration of intent — morally the same as typing
    # the flag every launch. Profile gate (first gate) is whatever the
    # referenced profile declares.
    _perform_launch(
        profile_name=preset.profile,
        mount_specs=list(preset.mounts),
        image=image,
        dry_run=dry_run,
        allow_broad_mount=True,
        harness=preset.harness,
        platform_restriction=list(preset.platforms) if preset.platforms else None,
        preset_name=preset.name,
        allow_ephemeral=allow_ephemeral,
    )
