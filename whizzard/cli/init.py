"""`whiz init` — first-run setup wizard (Stage 19 / M3).

Thin CLI wrapper around `whizzard.init_wizard.run_wizard`.
"""

from __future__ import annotations

from typing import Annotated

import typer

from whizzard.cli._shared import console
from whizzard.init_wizard import run_wizard


def init_cmd(
    yes: Annotated[
        bool,
        typer.Option(
            "--yes", "-y",
            help="Non-interactive mode: accept all defaults, skip recommended-"
                 "choice prompts. Defaults to: write configs, build base image, "
                 "build Hermes image. CI / scripted-install friendly.",
        ),
    ] = False,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Overwrite existing ~/.whizzard/config/ files. Without this, "
                 "the wizard refuses to run when prior config is present so "
                 "you don't accidentally clobber a working setup.",
        ),
    ] = False,
) -> None:
    """Walk through a guided first-run setup for Whizzard."""
    try:
        run_wizard(non_interactive=yes, force=force)
    except KeyboardInterrupt:
        console.print()
        console.print("[yellow]setup aborted.[/yellow] re-run `whiz init` to retry.")
        raise typer.Exit(code=130) from None
    except EOFError:
        # stdin closed at an interactive prompt (Ctrl-D, or piped/empty input).
        # Without this the EOFError propagates uncaught and dumps a Python
        # traceback; instead, abort cleanly and point at the non-interactive path.
        console.print()
        console.print(
            "[yellow]setup aborted:[/yellow] no input available (stdin closed). "
            "Run `whiz init` in an interactive terminal, or `whiz init --yes` to "
            "accept defaults non-interactively."
        )
        raise typer.Exit(code=1) from None
