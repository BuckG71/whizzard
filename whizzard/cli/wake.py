"""`whiz wake [<session-id>] [--allow-missing-mounts]` — hot-restart of idle-ended sessions.

Stage 15.5 / D-168 + D-169. Thin CLI wrapper around `whizzard.wake`:
this module owns the user-facing surface (flag parsing, error rendering,
the friendly "Use `whiz launch` ..." next-verb pointer) and delegates the
lookup + relaunch orchestration to the library.

Bare `whiz wake` resumes the most-recent eligible session; `whiz wake
<sid>` resumes by exact / prefix match. Per D-168, both paths preserve
the prior permission set verbatim (including any `--allow-broad-mount`
override) — these are user-initiated restarts and the user is right
there acting.
"""

from __future__ import annotations

from typing import Annotated

import typer

from whizzard.cli._launch import _perform_launch
from whizzard.cli._shared import console
from whizzard.wake import (
    WakeStatus,
    check_mounts_exist,
    find_wakeable,
    log_wake_event,
    missing_mount_names,
    reconstruct_launch_params,
)

_LAUNCH_HINT = "Use [bold]whiz launch[/bold] (or [bold]whiz run --profile ...[/bold]) to start a new session."


def _render_error(status: WakeStatus, detail: str) -> None:
    """Print the user-facing error + next-verb pointer (D-169)."""
    console.print(f"[red]{detail}[/red]")
    if status in (
        WakeStatus.NO_ELIGIBLE,
        WakeStatus.NOT_FOUND,
        WakeStatus.NOT_IDLE,
        WakeStatus.NOT_ENDED,
        WakeStatus.ALREADY_WOKEN,
        WakeStatus.EMPTY_PREFIX,
    ):
        console.print(_LAUNCH_HINT)
    elif status == WakeStatus.STILL_ACTIVE:
        console.print(
            "To restart an active session with new perms, use [bold]whiz adjust[/bold] instead."
        )
    elif status == WakeStatus.AMBIGUOUS_PREFIX:
        console.print("Use a longer prefix to disambiguate.")


def wake_cmd(
    session_id: Annotated[
        str | None,
        typer.Argument(
            help="Session ID to wake (full UUID or 8+ char prefix). "
                 "Omit to wake the most-recent eligible idle-ended session."
        ),
    ] = None,
    allow_missing_mounts: Annotated[
        bool,
        typer.Option(
            "--allow-missing-mounts",
            help="If a mount's host path no longer exists, drop that mount "
                 "from the relaunch and proceed. Default: error.",
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Print the resolved wake target and reconstructed launch "
                 "params without actually launching.",
        ),
    ] = False,
) -> None:
    """Wake (hot-restart) an idle-ended session.

    Eligibility is restricted to sessions that ended with
    `expiry_reason: idle` (D-169 spec). Duration-capped sessions are not
    wakeable — the cap was a deliberate budget, not a pause. Permission
    set carries forward unchanged (D-168).
    """
    resolution = find_wakeable(session_id)
    if resolution.status != WakeStatus.OK or resolution.candidate is None:
        _render_error(resolution.status, resolution.detail)
        raise typer.Exit(code=2)

    candidate = resolution.candidate
    start_event = candidate.start_event

    # Mount existence check (D-169 #2)
    missing_paths = check_mounts_exist(start_event.get("mounts", []) or [])
    drop_names: set[str] = set()
    if missing_paths:
        if not allow_missing_mounts:
            console.print(
                f"[red]Cannot wake {candidate.session_id[:8]}: "
                f"{len(missing_paths)} mount(s) missing on disk:[/red]"
            )
            for path in missing_paths:
                console.print(f"  • {path}")
            console.print(
                "Re-add the missing path(s), or re-run with [bold]--allow-missing-mounts[/bold] "
                "to drop them from the wake."
            )
            raise typer.Exit(code=2)
        # Override path: collect the mount *names* to drop from the relaunch.
        drop_names = set(missing_mount_names(start_event))
        console.print(
            f"[yellow]Dropping {len(drop_names)} missing mount(s) from wake: "
            f"{', '.join(sorted(drop_names))}[/yellow]"
        )

    new_params = reconstruct_launch_params(start_event, drop_mount_names=drop_names)

    if dry_run:
        console.print(
            f"[bold]Would wake session:[/bold] {candidate.session_id[:8]}…"
        )
        console.print(f"  Profile: {new_params['profile_name']}")
        console.print(f"  Image: {new_params['image']}")
        console.print(f"  Harness: {new_params['harness']}")
        console.print(f"  Preset: {new_params.get('preset_name') or '—'}")
        console.print(f"  Mounts: {', '.join(new_params['mount_specs']) or '—'}")
        console.print(f"  allow_broad_mount: {new_params['allow_broad_mount']}")
        if drop_names:
            console.print(f"  Dropped mounts: {', '.join(sorted(drop_names))}")
        return

    # F-G-03: log the `session_woken` event AFTER a successful relaunch.
    # Previously this fired before relaunch on the theory that "the link
    # survives a failure," but the event also marks the sid as already
    # woken — a failed wake would invisibly block the next bare
    # `whiz wake` from picking the same idle session up again. Now: log
    # `session_woken` only on success; log `session_wake_failed` (which
    # is NOT in the woken-set predicate) on failure, so the user can
    # retry. F-G-12: broad-except on the relaunch so an unexpected
    # exception is recorded as wake-failed instead of leaking a
    # traceback to the user with no audit trace.
    relaunch_code = 0
    try:
        _perform_launch(
            profile_name=new_params["profile_name"],
            mount_specs=new_params["mount_specs"],
            image=new_params["image"],
            dry_run=False,
            allow_broad_mount=new_params["allow_broad_mount"],
            harness=new_params["harness"],
            preset_name=new_params.get("preset_name"),
        )
    except typer.Exit as e:
        relaunch_code = int(e.exit_code) if e.exit_code is not None else 0
    except Exception as exc:
        log_wake_event(
            superseded_session_id=candidate.session_id,
            new_session_id=None,
            dropped_mounts=sorted(drop_names) if drop_names else [],
            event="session_wake_failed",
            detail=f"{type(exc).__name__}: {exc}",
        )
        console.print(
            f"[red]Wake failed: {type(exc).__name__}: {exc}[/red]\n"
            f"The original idle session is still wakeable; retry "
            f"`whiz wake {candidate.session_id[:8]}` after fixing the issue."
        )
        raise typer.Exit(code=125) from exc

    if relaunch_code == 0:
        log_wake_event(
            superseded_session_id=candidate.session_id,
            new_session_id=None,
            dropped_mounts=sorted(drop_names) if drop_names else [],
        )
    else:
        log_wake_event(
            superseded_session_id=candidate.session_id,
            new_session_id=None,
            dropped_mounts=sorted(drop_names) if drop_names else [],
            event="session_wake_failed",
            detail=f"relaunch returned exit {relaunch_code}",
        )
        console.print(
            f"[red]Wake relaunch returned exit {relaunch_code}.[/red] "
            f"The idle session remains wakeable; retry once the "
            f"underlying issue is fixed."
        )
        raise typer.Exit(code=relaunch_code)
