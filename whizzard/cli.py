"""Whizzard CLI entry point."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from whizzard.adapters import (
    HarnessAdapter,
    HermesProfileExistsError,
    HermesProfileNameError,
    HermesProfileSourceMissingError,
    UnknownHarnessTypeError,
    build_adapter,
    create_hermes_profile,
)
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
from whizzard.harness_config import (
    HARNESSES_FILE,
    HarnessConfigError,
    default_harnesses,
    get_harness_config,
    load_harnesses,
)
from whizzard.mounts import (
    MOUNTS_FILE,
    Mount,
    MountMode,
    MountRegistryError,
    load_mounts,
    resolve_mount_spec,
)
from whizzard.preset_config import (
    PRESETS_FILE,
    Preset,
    PresetConfigError,
    default_presets,
    get_preset,
    list_presets,
    load_presets,
    validate_references,
)
from whizzard.safety import OverrideRecord, SafetyViolation, check_mount_path
from whizzard.session_log import SESSIONS_LOG, new_session_id
from whizzard.snapshot import write_snapshot


app = typer.Typer(
    name="whizzard",
    help="Whizzard — local capability governance for AI agents.",
    no_args_is_help=True,
    add_completion=False,
)
profiles_app = typer.Typer(help="Inspect available profiles.")
image_app = typer.Typer(help="Manage the execution image.")
mounts_app = typer.Typer(help="Inspect the mount registry.")
sessions_app = typer.Typer(help="Inspect the session log.")
harnesses_app = typer.Typer(help="Inspect the harness registry.")
preset_app = typer.Typer(help="Manage and launch presets (Stage 10).")
hermes_app = typer.Typer(help="Hermes harness operations (Stage 8).")
hermes_profile_app = typer.Typer(help="Manage Hermes profiles for use in Whizzard cells.")
hermes_app.add_typer(hermes_profile_app, name="profile")
app.add_typer(profiles_app, name="profiles")
app.add_typer(image_app, name="image")
app.add_typer(mounts_app, name="mounts")
app.add_typer(sessions_app, name="sessions")
app.add_typer(harnesses_app, name="harnesses")
app.add_typer(preset_app, name="preset")
app.add_typer(hermes_app, name="hermes")

console = Console()


@app.callback()
def _bootstrap() -> None:
    """Runs before every subcommand. Ensures ~/.whizzard/ scaffold exists."""
    ensure_whizzard_home()


def _perform_launch(
    *,
    profile_name: str,
    mount_specs: list[str],
    image: str,
    dry_run: bool,
    allow_broad_mount: bool,
    harness: str,
    platform_restriction: list[str] | None = None,
) -> None:
    """Shared launch core. Called by `run` (CLI flags) and `preset launch`
    (preset-resolved args). Handles profile / harness / mount resolution,
    pre-launch banner, dry-run, snapshot, and container start. Errors
    raise typer.Exit with the appropriate code.

    platform_restriction: optional subset of the harness's declared platforms
    (per D-89 amended) — when provided, overlays on the harness config dict
    so the adapter sees the restricted set.
    """
    try:
        prof = get_profile(profile_name)
    except KeyError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=2)
    except ProfileConfigError as e:
        console.print(f"[red]error loading profiles.json: {e}[/red]")
        raise typer.Exit(code=2)

    # Resolve the harness adapter from harnesses.json.
    try:
        harness_cfg = dict(get_harness_config(harness))
    except HarnessConfigError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=2)
    if platform_restriction is not None:
        # D-89 amended: presets restrict the harness's platform ceiling,
        # never expand. Caller is responsible for validating subset relation.
        harness_cfg["platforms"] = list(platform_restriction)
    try:
        adapter = build_adapter(harness, harness_cfg)
    except UnknownHarnessTypeError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=2)

    resolved: list[tuple[Mount, MountMode]] = []
    overrides_used: list[OverrideRecord] = []
    if mount_specs:
        try:
            registry = load_mounts()
        except MountRegistryError as e:
            console.print(f"[red]error loading mounts.json: {e}[/red]")
            raise typer.Exit(code=2)
        try:
            for spec in mount_specs:
                m, mode = resolve_mount_spec(spec, registry)
                # Other registered mounts (excluding the one being checked)
                # supply the "parent of registered mount" rule context.
                other_paths = [
                    other.host_path for name, other in registry.items()
                    if name != m.name
                ]
                overrides = check_mount_path(
                    m.host_path,
                    prof,
                    allow_broad_mount,
                    other_registered_paths=other_paths,
                )
                overrides_used.extend(overrides)
                resolved.append((m, mode))
        except MountRegistryError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(code=2)
        except SafetyViolation as e:
            console.print(f"[red]safety policy: {e}[/red]")
            raise typer.Exit(code=2)

    duration = "unlimited" if prof.duration_seconds is None else f"{prof.duration_seconds // 60} min"
    session_id = new_session_id()
    if dry_run:
        console.print("[yellow]DRY RUN[/yellow] — no container will be launched.\n")
    console.print(f"[bold]Whizzard Profile:[/bold] {prof.name.upper()}")
    console.print(f"[bold]Network:[/bold] {'enabled' if prof.network_enabled else 'disabled'}")
    console.print(f"[bold]Duration:[/bold] {duration}")
    console.print(f"[bold]Broad-mount override:[/bold] {'allowed' if prof.allow_broad_mount else 'blocked'}")
    console.print(f"[bold]Image:[/bold] {image}")
    console.print(f"[bold]Harness:[/bold] {adapter.name}")
    console.print(f"[bold]Session ID:[/bold] {session_id}")
    if resolved:
        console.print("[bold]Mounts:[/bold]")
        for m, mode in resolved:
            console.print(f"  {m.name} ({mode}): {m.host_path} → {m.container_path()}")
    else:
        console.print("[bold]Mounts:[/bold] none")
    if overrides_used:
        console.print("[bold yellow]Broad-mount overrides applied:[/bold yellow]")
        for o in overrides_used:
            console.print(f"  - {o.path} ({o.reason})")
    console.print()

    if dry_run:
        import shlex
        argv = build_run_argv(
            prof,
            image=image,
            resolved_mounts=resolved,
            session_id=session_id,
            adapter=adapter,
        )
        console.print("[bold]docker invocation that would run:[/bold]")
        console.print("  " + " ".join(shlex.quote(a) for a in argv))
        # Note: image existence is NOT checked here — dry-run reports intent.
        # If the image is missing, an actual `whizzard run` would surface that.
        # Dry-run does NOT write to the session log.
        raise typer.Exit(code=0)

    # Pre-flight checks before launch — surfaced via the same red-error path
    # the rest of the CLI uses, so the error styling is consistent.
    if not docker_available():
        console.print("[red]error: docker not found on PATH[/red]")
        raise typer.Exit(code=127)
    if not image_exists(image):
        console.print(
            f"[red]error: image {image!r} not found.[/red]\n"
            f"build it with: [bold]whizzard image build[/bold]"
        )
        raise typer.Exit(code=125)

    # Stage 9 / D-156: write the per-session state snapshot before launch.
    # The in-cell MCP server reads this via WHIZ_SNAPSHOT_PATH (set by the
    # adapter's mcp_env). The same per-session directory holds the agent's
    # event file, which the cell writes and Whizzard merges into the audit
    # log at session_end (D-156 event-merge pattern, see docker_cmd).
    write_snapshot(
        session_id=session_id,
        profile=prof,
        resolved_mounts=resolved,
        harness_name=adapter.name,
    )

    result = run_shell(
        prof,
        image=image,
        resolved_mounts=resolved,
        session_id=session_id,
        overrides_used=[{"path": o.path, "reason": o.reason} for o in overrides_used],
        adapter=adapter,
    )
    raise typer.Exit(code=result.exit_code)


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
    allow_broad_mount: Annotated[
        bool,
        typer.Option(
            "--allow-broad-mount",
            help="Opt in to mounting broad folders / cloud sync / parents of "
                 "registered mounts. Requires a profile that permits this.",
        ),
    ] = False,
    harness: Annotated[
        str,
        typer.Option(
            "--harness",
            help="Named harness from harnesses.json (default: generic shell).",
        ),
    ] = "generic",
) -> None:
    """Launch a contained shell session under the given profile."""
    _perform_launch(
        profile_name=profile,
        mount_specs=mount or [],
        image=image,
        dry_run=dry_run,
        allow_broad_mount=allow_broad_mount,
        harness=harness,
    )


# --- Preset CLI (Stage 10) --------------------------------------------------


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
        raise typer.Exit(code=2)
    try:
        harness_names = set(load_harnesses())
    except HarnessConfigError as e:
        console.print(f"[red]error loading harnesses.json: {e}[/red]")
        raise typer.Exit(code=2)
    try:
        mount_names = set(load_mounts())
    except MountRegistryError as e:
        console.print(f"[red]error loading mounts.json: {e}[/red]")
        raise typer.Exit(code=2)
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
        raise typer.Exit(code=2)


@preset_app.command("list")
def preset_list_cmd() -> None:
    """List configured presets."""
    try:
        presets = load_presets()
    except PresetConfigError as e:
        console.print(f"[red]error loading presets.json: {e}[/red]")
        raise typer.Exit(code=2)
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
        raise typer.Exit(code=2)
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
    import json as _json

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
    PRESETS_FILE.write_text(_json.dumps(payload, indent=2) + "\n")
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
) -> None:
    """Launch a session using the named preset."""
    try:
        presets = load_presets()
    except PresetConfigError as e:
        console.print(f"[red]error loading presets.json: {e}[/red]")
        raise typer.Exit(code=2)
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
    )


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


@sessions_app.command("tail")
def sessions_tail_cmd(
    n: Annotated[
        int,
        typer.Option("-n", help="Number of recent log lines to show."),
    ] = 10,
) -> None:
    """Show the last N lines of the session log."""
    if not SESSIONS_LOG.exists():
        console.print(f"[yellow]no session log yet[/yellow] at {SESSIONS_LOG}")
        return

    lines = SESSIONS_LOG.read_text().splitlines()
    for line in lines[-n:]:
        console.print(line)


@sessions_app.command("path")
def sessions_path_cmd() -> None:
    """Print the path to the session log."""
    console.print(str(SESSIONS_LOG))


@harnesses_app.command("list")
def harnesses_list_cmd() -> None:
    """List configured harnesses (from harnesses.json or bundled defaults)."""
    try:
        harnesses = load_harnesses()
    except HarnessConfigError as e:
        console.print(f"[red]error loading harnesses.json: {e}[/red]")
        raise typer.Exit(code=2)

    source = "user config" if HARNESSES_FILE.exists() else "bundled defaults"
    title = f"Harnesses ({source})"
    table = Table(title=title)
    table.add_column("Name")
    table.add_column("Type")
    table.add_column("Start command")
    table.add_column("Wrap-up command")
    table.add_column("Description")

    for name in sorted(harnesses):
        spec = harnesses[name]
        table.add_row(
            name,
            spec.get("type", ""),
            spec.get("start_command", ""),
            spec.get("wrap_up_command", "—"),
            spec.get("description", ""),
        )
    console.print(table)


@harnesses_app.command("init")
def harnesses_init_cmd(
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite an existing harnesses.json."),
    ] = False,
) -> None:
    """Write the bundled default harnesses to ~/.whizzard/config/harnesses.json."""
    import json

    if HARNESSES_FILE.exists() and not force:
        console.print(
            f"[yellow]{HARNESSES_FILE} already exists.[/yellow] "
            "use [bold]--force[/bold] to overwrite."
        )
        raise typer.Exit(code=1)

    payload = {"schema_version": 1, "harnesses": default_harnesses()}
    HARNESSES_FILE.write_text(json.dumps(payload, indent=2) + "\n")
    console.print(f"[green]wrote[/green] {HARNESSES_FILE}")
    console.print(
        "edit it to add new harnesses. "
        "select one at run time with [bold]whizzard run --harness <name>[/bold]."
    )


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
        raise typer.Exit(code=2)
    except HermesProfileExistsError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1)
    except HermesProfileSourceMissingError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=2)

    if result.source is None:
        console.print(f"[green]created[/green] empty profile at {result.path}")
    else:
        console.print(f"[green]created[/green] profile at {result.path}")
        console.print(f"  cloned from {result.source} (auth.json and runtime state excluded)")
    console.print(
        "Add a harness entry in ~/.whizzard/config/harnesses.json referencing "
        f"hermes_home: {result.path} to use it."
    )


if __name__ == "__main__":
    app()
