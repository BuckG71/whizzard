"""`whiz adjust <session-id> [flags]` — mid-session capability adjustment.

Stage 13 / D-163. Thin CLI wrapper around `whizzard.adjust.adjust_session`;
this module owns the user-facing surface (flag parsing + TTY prompt) and
delegates the orchestration to the library.
"""

from __future__ import annotations

from typing import Annotated

import typer

from whizzard.adjust import (
    Changes,
    MountAddition,
    adjust_session,
    parse_duration,
)
from whizzard.cli._shared import console


def tty_approver(diff: str) -> bool:
    """Interactive `[y/N]` approval. Renders the diff, reads stdin, returns
    True iff the user types `y` or `yes` (case-insensitive). Empty input or
    anything else defaults to deny — fail-safe."""
    console.print()
    console.print("[bold]Adjust will apply the following changes:[/bold]")
    console.print(diff)
    console.print()
    raw = typer.prompt("Approve? [y/N]", default="n", show_default=False)
    return raw.strip().lower() in {"y", "yes"}


def adjust_cmd(
    session_id: Annotated[
        str,
        typer.Argument(help="Session ID (full UUID or 8+ char prefix)."),
    ],
    add_mount: Annotated[
        list[str] | None,
        typer.Option(
            "--add-mount",
            help="Add a registered mount to the session. "
                 "Format: `name` or `name:mode` (`ro`/`rw`). Repeatable.",
        ),
    ] = None,
    remove_mount: Annotated[
        list[str] | None,
        typer.Option(
            "--remove-mount",
            help="Remove a mount from the session (always-safe, no approval prompt). Repeatable.",
        ),
    ] = None,
    extend: Annotated[
        str | None,
        typer.Option(
            "--extend",
            help="Extend the session's duration limit (e.g. `30m`, `2h`, `90s`). "
                 "No-op for unlimited-duration sessions.",
        ),
    ] = None,
    allow_broad_mount: Annotated[
        bool,
        typer.Option(
            "--allow-broad-mount",
            help="Permit broad-mount overrides for `--add-mount` paths that "
                 "would otherwise hit the safety policy. Requires the profile "
                 "to permit broad mounts.",
        ),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option(
            "--yes", "-y",
            help="Skip the TTY approval prompt (auto-approve). Use only when "
                 "scripting; interactive use should let the prompt fire.",
        ),
    ] = False,
) -> None:
    """Adjust a running session: add or remove mounts, extend duration,
    permit broad mounts. Stops the existing container and re-launches with
    the new capabilities; the cell's HERMES_HOME (or equivalent) bind mount
    preserves the harness's on-disk state across the restart.

    Approval: a `[y/N]` prompt shows what's about to change unless `--yes`
    is passed or every change is unambiguously narrowing (`--remove-mount`
    only).
    """
    # Parse --add-mount specs into MountAddition records.
    additions: list[MountAddition] = []
    for spec in add_mount or []:
        if ":" in spec:
            name, _, mode = spec.partition(":")
            if mode not in ("ro", "rw"):
                console.print(
                    f"[red]invalid mount mode {mode!r} in {spec!r}; use 'ro' or 'rw'[/red]"
                )
                raise typer.Exit(code=2)
            additions.append(MountAddition(name=name, mode=mode))
        else:
            additions.append(MountAddition(name=spec, mode=None))

    # Parse --extend.
    extend_seconds: int | None = None
    if extend is not None:
        try:
            extend_seconds = parse_duration(extend)
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(code=2) from e

    changes = Changes(
        add_mounts=tuple(additions),
        remove_mounts=tuple(remove_mount or []),
        extend_seconds=extend_seconds,
        allow_broad_mount=allow_broad_mount,
    )

    approver = (lambda _diff: True) if yes else tty_approver
    result = adjust_session(session_id, changes, approver)

    if result.detail:
        if result.exit_code == 0:
            console.print(f"[green]{result.detail}[/green]")
        elif result.exit_code == 1:
            console.print(f"[yellow]{result.detail}[/yellow]")
        else:
            console.print(f"[red]{result.detail}[/red]")
    raise typer.Exit(code=result.exit_code)
