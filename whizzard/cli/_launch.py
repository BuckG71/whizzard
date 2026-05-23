"""Shared launch core (`_perform_launch`).

Called by both `whiz run` (CLI flags) and `whiz preset launch` (preset-resolved
args). Handles profile / harness / mount resolution, pre-launch banner, dry-run,
snapshot, and container start. Errors raise typer.Exit with the appropriate
code.
"""

from __future__ import annotations

import typer

from whizzard.adapters import UnknownHarnessTypeError, build_adapter
from whizzard.cli._shared import console
from whizzard.config import ProfileConfigError, get_profile
from whizzard.docker_cmd import (
    DockerDaemonError,
    build_run_argv,
    docker_available,
    image_exists,
    run_shell,
)
from whizzard.harness_config import HarnessConfigError, get_harness_config
from whizzard.mounts import (
    Mount,
    MountMode,
    MountRegistryError,
    load_mounts,
    resolve_mount_spec,
)
from whizzard.safety import OverrideRecord, SafetyViolation, check_mount_path
from whizzard.session_log import new_session_id
from whizzard.snapshot import write_snapshot


def _perform_launch(
    *,
    profile_name: str,
    mount_specs: list[str],
    image: str,
    dry_run: bool,
    allow_broad_mount: bool,
    harness: str,
    platform_restriction: list[str] | None = None,
    preset_name: str | None = None,
    duration_override_seconds: int | None = None,
) -> None:
    """Shared launch core. Called by `run` (CLI flags) and `preset launch`
    (preset-resolved args). Handles profile / harness / mount resolution,
    pre-launch banner, dry-run, snapshot, and container start. Errors
    raise typer.Exit with the appropriate code.

    platform_restriction: optional subset of the harness's declared platforms
    (per D-89 amended) — when provided, overlays on the harness config dict
    so the adapter sees the restricted set.

    duration_override_seconds: optional override of the profile's duration
    cap (Stage 15) — an `oiq adjust --extend` relaunch passes the extended
    limit through here.
    """
    try:
        prof = get_profile(profile_name)
    except KeyError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=2) from e
    except ProfileConfigError as e:
        console.print(f"[red]error loading profiles.json: {e}[/red]")
        raise typer.Exit(code=2) from e

    # Resolve the harness adapter from harnesses.json.
    try:
        harness_cfg = dict(get_harness_config(harness))
    except HarnessConfigError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=2) from e
    if platform_restriction is not None:
        # D-89 amended: presets restrict the harness's platform ceiling,
        # never expand. Caller is responsible for validating subset relation.
        harness_cfg["platforms"] = list(platform_restriction)
    try:
        adapter = build_adapter(harness, harness_cfg)
    except UnknownHarnessTypeError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=2) from e

    resolved: list[tuple[Mount, MountMode]] = []
    overrides_used: list[OverrideRecord] = []
    if mount_specs:
        try:
            registry = load_mounts()
        except MountRegistryError as e:
            console.print(f"[red]error loading mounts.json: {e}[/red]")
            raise typer.Exit(code=2) from e
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
            raise typer.Exit(code=2) from e
        except SafetyViolation as e:
            console.print(f"[red]safety policy: {e}[/red]")
            raise typer.Exit(code=2) from e

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
    try:
        image_present = image_exists(image)
    except DockerDaemonError as e:
        console.print(f"[red]error: {e}[/red]")
        raise typer.Exit(code=125) from e
    if not image_present:
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
        preset_name=preset_name,
        duration_override_seconds=duration_override_seconds,
    )
    raise typer.Exit(code=result.exit_code)
