"""Whizzard CLI entry point.

This package assembles the Typer app from per-subapp modules:
  - `_shared`    — shared Console
  - `_launch`    — `_perform_launch`, the shared launch core
  - `_session`   — session-log read helpers used by status + brevity
  - `profiles`   — `whiz profiles ...`
  - `mounts`     — `whiz mounts ...`
  - `image`      — `whiz image ...`
  - `sessions`   — `whiz sessions ...`
  - `harnesses`  — `whiz harnesses ...`
  - `preset`     — `whiz preset ...` (Stage 10)
  - `hermes`     — `whiz hermes ...` (Stage 8)

This module defines top-level commands (`run`, `status`), the bootstrap
callback, and the brevity aliases (`r`, `s`, `p`, `m`, `pr`).
"""

from __future__ import annotations

from typing import Annotated

import typer
from rich.table import Table

from whizzard.cli._launch import _perform_launch
from whizzard.cli._session import (
    _active_sessions,
    _harness_from_event,
    _most_recent_preset,
    _read_session_events,
    _remaining_seconds,
)
from whizzard.cli._shared import console
from whizzard.cli.adjust import adjust_cmd
from whizzard.cli.harnesses import harnesses_app
from whizzard.cli.hermes import hermes_app
from whizzard.cli.image import image_app
from whizzard.cli.init import init_cmd
from whizzard.cli.mounts import mounts_app, mounts_list_cmd
from whizzard.cli.preset import preset_app, preset_launch_cmd, preset_list_cmd, preset_show_cmd
from whizzard.cli.profiles import profiles_app, profiles_list_cmd
from whizzard.cli.requests import requests_app
from whizzard.cli.sessions import sessions_app
from whizzard.cli.wake import wake_cmd
from whizzard.config import ensure_whizzard_home
from whizzard.docker_cmd import (  # noqa: F401 -- re-export for `patch("whizzard.cli.run_shell")` tests
    run_shell,
)
from whizzard.requests import read_all_requests

# `whiz --help` groups commands by workflow via Typer's rich_help_panel,
# so the important verbs surface and shortcuts don't interleave with them.
_PANEL_SETUP = "Setup"
_PANEL_LAUNCH = "Launch a session"
_PANEL_CONTROL = "Control a running session"
_PANEL_INSPECT = "Inspect your setup"
_PANEL_SHORTCUTS = "Shortcuts"

app = typer.Typer(
    name="whizzard",
    # Top help block (below Usage): tagline, then how to invoke a command and
    # find flags. The \n\n starts a second paragraph — Typer reflows the first
    # paragraph (the tagline) but preserves single newlines in later ones, so
    # the two hint lines stay on their own lines.
    help=(
        "Whizzard — local capability governance for AI agents.\n\n"
        "Run any command as  whiz <command>\n"
        "See its flags with  whiz <command> --help"
    ),
    no_args_is_help=False,
    add_completion=False,
)
app.add_typer(profiles_app, name="profiles", rich_help_panel=_PANEL_INSPECT)
app.add_typer(image_app, name="image", rich_help_panel=_PANEL_SETUP)
app.add_typer(mounts_app, name="mounts", rich_help_panel=_PANEL_INSPECT)
app.add_typer(sessions_app, name="sessions", rich_help_panel=_PANEL_INSPECT)
app.add_typer(harnesses_app, name="harnesses", rich_help_panel=_PANEL_INSPECT)
app.add_typer(preset_app, name="preset", rich_help_panel=_PANEL_LAUNCH)
app.add_typer(hermes_app, name="hermes", rich_help_panel=_PANEL_LAUNCH)
app.add_typer(requests_app, name="requests", rich_help_panel=_PANEL_CONTROL)
app.command("adjust", rich_help_panel=_PANEL_CONTROL)(adjust_cmd)
app.command("wake", rich_help_panel=_PANEL_CONTROL)(wake_cmd)
app.command("init", rich_help_panel=_PANEL_SETUP)(init_cmd)


def _version_callback(value: bool) -> None:
    """Eager `--version` handler: print the installed package version and
    exit before any subcommand resolution or config scaffolding runs.
    Version comes from package metadata so it never drifts from
    pyproject.toml."""
    if not value:
        return
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _pkg_version

    try:
        v = _pkg_version("whizzard")
    except PackageNotFoundError:  # running from a source tree, not installed
        v = "0.0.0+source"
    console.print(f"whizzard {v}")
    raise typer.Exit(code=0)


@app.callback(invoke_without_command=True)
def _bootstrap(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show the Whizzard version and exit.",
        ),
    ] = False,
) -> None:
    """Runs before every subcommand. Ensures ~/.whizzard/ scaffold exists.

    Stage 10: bare `whiz` (no subcommand) defaults to `whiz status` rather
    than showing help. New users land in status mode; `whiz --help` is the
    explicit help path.
    """
    ensure_whizzard_home()
    if ctx.invoked_subcommand is None:
        status_cmd()
        raise typer.Exit(code=0)


# --- Top-level commands -----------------------------------------------------


@app.command("run", rich_help_panel=_PANEL_LAUNCH)
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
        str | None,
        typer.Option(
            "--image",
            help="Container image to use (default: the selected harness's image).",
        ),
    ] = None,
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
    allow_ephemeral: Annotated[
        bool,
        typer.Option(
            "--allow-ephemeral",
            help="Opt in to launching an agent harness without a persistent "
                 "HERMES_HOME — memories, skills, and gateway state are "
                 "ephemeral with the container. Almost never what you want.",
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
        allow_ephemeral=allow_ephemeral,
    )


def _fmt_remaining(secs: float | None) -> str:
    """Format seconds-until-duration-cap for the `whiz status` table."""
    if secs is None:
        return "—"
    if secs <= 0:
        return "[red]overdue[/red]"
    if secs >= 3600:
        return f"~{int(secs // 3600)}h{int((secs % 3600) // 60)}m"
    if secs >= 60:
        return f"~{int(secs // 60)}m"
    return f"~{int(secs)}s"


@app.command("status", rich_help_panel=_PANEL_CONTROL)
def status_cmd() -> None:
    """Show session status: active sessions and recent history."""
    events = _read_session_events()
    if not events:
        console.print("[yellow]no sessions logged yet[/yellow]")
        console.print("run [bold]whiz --help[/bold] to see available commands.")
        return

    active = _active_sessions(events)
    active_count = len(active)

    # Show counts header
    if active_count == 0:
        console.print("[bold]Active sessions:[/bold] none")
    elif active_count == 1:
        console.print("[bold green]Active sessions:[/bold green] 1")
    else:
        console.print(f"[bold green]Active sessions:[/bold green] {active_count}")

    # Stage 14: surface pending agent capability requests so the operator
    # knows a contained agent is waiting on a decision.
    pending_requests = read_all_requests(pending_only=True)
    if pending_requests:
        console.print(
            f"[bold yellow]Pending agent requests:[/bold yellow] "
            f"{len(pending_requests)} — review with [bold]whiz requests[/bold]"
        )

    # Show recent session_start events (last 10), most recent first
    starts = [e for e in events if e.get("event") == "session_start"]
    recent = list(reversed(starts))[:10]

    table = Table(title="Recent sessions")
    table.add_column("Status")
    table.add_column("Session ID")
    table.add_column("Profile")
    table.add_column("Preset")
    table.add_column("Harness")
    table.add_column("Started")

    for ev in recent:
        sid = ev.get("session_id", "")
        sid_short = sid[:8] if len(sid) >= 8 else sid
        is_active = sid in active
        if is_active:
            # Stage 15: show time left on the duration cap next to RUNNING
            # (unlimited / unparseable sessions just show RUNNING).
            remaining = _remaining_seconds(ev)
            rem = f" {_fmt_remaining(remaining)}" if remaining is not None else ""
            status = f"[green]RUNNING[/green]{rem}"
        else:
            status = "ended"
        table.add_row(
            status,
            sid_short,
            ev.get("profile", ""),
            ev.get("preset", "—"),
            # Derive harness from argv label if present, else show "?"
            _harness_from_event(ev),
            ev.get("start_time", ev.get("ts", "")),
        )
    console.print(table)


# --- Brevity aliases: r, s, p, m, pr ----------------------------------------


@app.command("r", rich_help_panel=_PANEL_SHORTCUTS)
def r_cmd(
    preset_name: Annotated[
        str | None,
        typer.Argument(
            help="Preset name to launch. Omit to launch most-recent preset. "
                 "If you pass run-style flags (--profile, --mount, --harness, "
                 "--allow-broad-mount), this becomes a `whiz run` invocation.",
        ),
    ] = None,
    profile: Annotated[
        str | None,
        typer.Option("--profile", "-p", help="Profile name (run-flag path)."),
    ] = None,
    mount: Annotated[
        list[str] | None,
        typer.Option("--mount", "-m", help="Mount spec (run-flag path)."),
    ] = None,
    image: Annotated[
        str | None,
        typer.Option(
            "--image",
            help="Container image to use (default: the selected harness's image).",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show what would happen without launching."),
    ] = False,
    allow_broad_mount: Annotated[
        bool,
        typer.Option(
            "--allow-broad-mount",
            help="Run-flag path: opt in to broad mounts.",
        ),
    ] = False,
    allow_ephemeral: Annotated[
        bool,
        typer.Option(
            "--allow-ephemeral",
            help="Run-flag path: opt in to ephemeral agent harness.",
        ),
    ] = False,
    harness: Annotated[
        str | None,
        typer.Option("--harness", help="Run-flag path: harness name."),
    ] = None,
) -> None:
    """Shortcut: `whiz r` → preset launch (positional) or run (flags).

    Dispatch:
    - `whiz r` (bare) → launch most-recent preset
    - `whiz r <name>` → launch named preset (--image and --dry-run honored)
    - `whiz r --profile X ...` → equivalent to `whiz run --profile X ...`
    - Mixing a positional preset with run-style flags is an error.
    """
    run_flag_present = bool(
        profile or mount or harness or allow_broad_mount or allow_ephemeral
    )

    if preset_name is not None and run_flag_present:
        console.print(
            "[red]cannot mix preset name with run-style flags. "
            "Use either `whiz r <preset>` or `whiz r --profile ... --harness ...`.[/red]"
        )
        raise typer.Exit(code=2)

    if run_flag_present:
        # Run-with-flags path
        _perform_launch(
            profile_name=profile or "default",
            mount_specs=mount or [],
            image=image,
            dry_run=dry_run,
            allow_broad_mount=allow_broad_mount,
            harness=harness or "generic",
            allow_ephemeral=allow_ephemeral,
        )
        return

    # Preset path: bare → most-recent, named → that preset
    if preset_name is None:
        last = _most_recent_preset()
        if last is None:
            console.print(
                "[red]no recent preset found; specify one: [bold]whiz r <name>[/bold][/red]"
            )
            raise typer.Exit(code=2)
        preset_name = last

    preset_launch_cmd(name=preset_name, dry_run=dry_run, image=image)


@app.command("s", rich_help_panel=_PANEL_SHORTCUTS)
def s_cmd() -> None:
    """Shortcut: `whiz s` → status."""
    status_cmd()


@app.command("p", rich_help_panel=_PANEL_SHORTCUTS)
def p_cmd(
    name: Annotated[
        str | None,
        typer.Argument(help="Preset name to show. Omit to list all presets."),
    ] = None,
) -> None:
    """Shortcut: `whiz p` → preset list; `whiz p <name>` → preset show."""
    if name is None:
        preset_list_cmd()
    else:
        preset_show_cmd(name)


@app.command("m", rich_help_panel=_PANEL_SHORTCUTS)
def m_cmd() -> None:
    """Shortcut: `whiz m` → mounts list."""
    mounts_list_cmd()


@app.command("pr", rich_help_panel=_PANEL_SHORTCUTS)
def pr_cmd() -> None:
    """Shortcut: `whiz pr` → profiles list."""
    profiles_list_cmd()


__all__ = ["app", "run_shell"]


if __name__ == "__main__":
    app()
