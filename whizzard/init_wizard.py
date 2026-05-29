"""Stage 19 / M3 — the `whiz init` first-run wizard.

Walks a new user through five short configuration steps plus a Hermes
profile sub-step. Honors the "no magical defaults" principle: every
non-trivial choice is presented to the user with plain-language context.

Wizard structure (see docs/wizard_design.md for the full transcripts):

  Welcome  (Step 0)              — orientation + "5 short steps" preview
  Step 1   — The Docker container — base + Hermes images built silently
  Step 1b  — Hermes profile setup — detect ~/.hermes/ → clone OR install
                                    instructions when Hermes is missing
  Step 2   — Profiles            — 5 bundled defaults; choice of use-all,
                                    minimal-subset, or define-your-own
  Step 3   — Mounts              — host folders an agent is allowed to see;
                                    loop until user is done
  Step 4   — Presets             — 1 bundled "hermes" preset; choice of
                                    use-bundled, define-your-own, or skip;
                                    per-mount attach prompt loop
  Step 5   — Audit log           — informational only; explains where
                                    session records live
  Done                           — summary + first commands to try

The wizard is invoked via `whiz init`. The CLI entry-point lives at
`whizzard/cli/init.py`; this module implements the orchestration so
the same flow could be invoked programmatically by future tools.

Implementation notes:

- Input is collected via typer/Click prompts so the entire flow is
  testable through Typer's CliRunner with the ``input=`` parameter.
- Side effects (docker build subprocess, config-file writes) are
  isolated behind small helpers so unit tests can monkeypatch them.
- The wizard refuses to run if ``~/.whizzard/config/`` already
  contains any of the four config files (idempotency); ``--force``
  overrides.
- A non-interactive ``--yes`` flag accepts all defaults and skips
  prompts that have a recommended choice; used by CI and scripted
  installs. See `WizardState.non_interactive`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from whizzard.cli._shared import console
from whizzard.config import (
    CONFIG_DIR,
    PROFILES_FILE,
    default_profiles,
)
from whizzard.docker_cmd import (
    WHIZZARD_HERMES_IMAGE,
    WHIZZARD_IMAGE,
    docker_available,
)
from whizzard.harness_config import HARNESSES_FILE, default_harnesses
from whizzard.mounts import MOUNTS_FILE
from whizzard.preset_config import PRESETS_FILE

# Config files the wizard creates. Existence of any → wizard refuses
# unless --force is passed. Idempotency contract for first-run UX.
_CONFIG_FILES = (PROFILES_FILE, MOUNTS_FILE, HARNESSES_FILE, PRESETS_FILE)


@dataclass
class WizardState:
    """Accumulates user choices across steps so the Done-summary step
    can render what was actually set up.

    Also carries non-interactive / force flags so step functions can
    branch on them without threading argv through every signature.
    """

    non_interactive: bool = False
    force: bool = False
    base_image_built: bool = False
    hermes_image_built: bool = False
    hermes_profile_path: Path | None = None
    hermes_branch: str | None = None  # "A" (detected) or "B" (not installed)
    profile_names: list[str] = field(default_factory=list)
    mount_count: int = 0
    mount_names: list[str] = field(default_factory=list)
    preset_count: int = 0
    preset_names: list[str] = field(default_factory=list)


# ---------- input helpers ----------


def _prompt_text(message: str, default: str | None = None) -> str:
    """Single-line text input. Honors a default by returning it when
    the user presses Enter with no input."""
    suffix = f" [{default}]" if default else ""
    raw = input(f"{message}{suffix}: ").strip()
    return raw or (default or "")


def _prompt_numeric_choice(
    message: str,
    options: list[str],
) -> int:
    """Show a numbered list and parse the chosen integer (1-indexed).

    Re-prompts on invalid input. Returns 1-based choice (1 = first option).
    """
    for i, label in enumerate(options, 1):
        console.print(f"  {i}) {label}")
    while True:
        raw = input("choose: ").strip()
        try:
            n = int(raw)
        except ValueError:
            console.print(f"[yellow]please enter a number 1–{len(options)}[/yellow]")
            continue
        if 1 <= n <= len(options):
            return n
        console.print(f"[yellow]please enter a number 1–{len(options)}[/yellow]")


def _pause_for_enter(message: str = "Press Enter to continue.") -> None:
    """Wait for the user to acknowledge an informational page."""
    import contextlib

    with contextlib.suppress(EOFError):
        input(f"{message} ")


# ---------- step functions ----------


def step_welcome(state: WizardState) -> None:
    """Step 0 — welcome page + 5-step preview."""
    console.print("[bold]Whizzard setup[/bold]")
    console.print("─" * 48)
    console.print()
    console.print(
        "Whizzard provides local capability governance for AI agents. "
        "Each agent session runs inside a Docker container (referred "
        "to as the \"sandbox\" throughout this wizard) with the host "
        "file system, network, and tool access restricted to what you "
        "explicitly grant. At present, Whizzard requires installation "
        "of the Hermes Agent harness by Nous Research. Setup of that "
        "harness is a part of this setup wizard."
    )
    console.print()
    console.print("This setup will walk you through 5 short configuration steps:")
    console.print()
    console.print("  1. Docker container image template (includes Hermes profile setup)")
    console.print("  2. Profiles        — named capability postures (e.g. \"safe\")")
    console.print(
        "  3. Mounts          — host folders/directories an agent is allowed to access"
    )
    console.print("  4. Presets         — saved launch bundles")
    console.print("  5. Audit log       — where session records go")
    console.print()
    console.print(
        "You can use the defaults for any step, or customize. Setup takes "
        "about 5 minutes. Nothing leaves your machine."
    )
    console.print()
    if state.non_interactive:
        return
    _pause_for_enter("Press Enter to begin, or Ctrl-C to exit.")


def step_1_image(state: WizardState, build_runner: Callable[[list[str]], int]) -> None:
    """Step 1 — build the Docker container (base + Hermes images).

    ``build_runner`` is the side-effect-isolated docker-build callable; the
    default implementation uses subprocess but tests can substitute a fake.
    """
    from importlib.resources import files

    console.print()
    console.print("[bold]Step 1 of 5 — The Docker container[/bold]")
    console.print("─" * 48)
    console.print()
    console.print(
        "This step builds the sandbox — the Docker container that "
        "holds your agent sessions, with the Hermes Agent harness by "
        "Nous Research pre-installed."
    )
    console.print()
    console.print(
        "Whizzard ships with a recipe (a Dockerfile) that builds it. "
        "The sandbox is minimal: just enough Linux to run Hermes and "
        "the tools you give it, configured so an agent inside it "
        "can't escape to your host, can't gain admin privileges, and "
        "can't talk to your Docker setup to launch other containers."
    )
    console.print()
    console.print(
        "The sandbox is built once. After that, every agent session "
        "uses a fresh copy of it."
    )
    console.print()

    # Pre-flight checks.
    if not docker_available():
        console.print(
            "[red]error: docker not found on PATH.[/red] "
            "Install Docker Desktop (mac/Windows) or the docker daemon "
            "(Linux) and re-run `whiz init`."
        )
        sys.exit(127)
    dockerfile = Path(str(files("whizzard._dockerfiles") / "Dockerfile"))
    if not dockerfile.exists():
        console.print(
            f"[red]error: bundled Dockerfile not found at {dockerfile}.[/red]"
        )
        sys.exit(2)

    console.print("Checking prerequisites:")
    console.print("  [green]✓[/green] Docker is running")
    console.print("  [green]✓[/green] Container recipe found")
    console.print()
    console.print(
        "Building takes about 2 minutes and requires no input from you."
    )
    console.print()
    if not state.non_interactive:
        _pause_for_enter("Press Enter to build.")
        console.print()

    # Base image.
    console.print("[dim]Building sandbox... (this takes about 2 minutes)[/dim]")
    base_rc = build_runner([
        "docker", "build", "-t", WHIZZARD_IMAGE,
        "-f", str(dockerfile), str(dockerfile.parent),
    ])
    if base_rc != 0:
        console.print(f"[red]docker build failed (exit {base_rc}).[/red]")
        sys.exit(base_rc)

    # Hermes image — derived from base. Build context is the parent of
    # the `whizzard/` package (so `COPY whizzard/mcp_server.py` resolves).
    import whizzard

    hermes_dockerfile = Path(
        str(files("whizzard._dockerfiles") / "Dockerfile.hermes")
    )
    hermes_context = Path(whizzard.__file__).resolve().parent.parent
    hermes_rc = build_runner([
        "docker", "build", "-t", WHIZZARD_HERMES_IMAGE,
        "-f", str(hermes_dockerfile), str(hermes_context),
    ])
    if hermes_rc != 0:
        console.print(f"[red]Hermes image build failed (exit {hermes_rc}).[/red]")
        sys.exit(hermes_rc)

    console.print("  [green]✓ sandbox built[/green]")
    console.print()
    console.print(
        "  [dim italic]For the curious: the sandbox was built from a "
        "pinned version of Debian, runs as a non-admin user, drops "
        "all Linux capabilities, and uses a read-only root filesystem. "
        "You can check on it later with `whiz image status`.[/dim italic]"
    )

    state.base_image_built = True
    state.hermes_image_built = True


def _default_build_runner(argv: list[str]) -> int:
    """Default docker-build invocation. Streams output to the user's
    terminal so they see real-time progress (the build takes ~2 min)."""
    completed = subprocess.run(argv)
    return completed.returncode


# ---------- orchestration ----------


def _idempotency_check(force: bool) -> None:
    """Refuse to run if any of the four config files already exist."""
    existing = [f for f in _CONFIG_FILES if f.exists()]
    if existing and not force:
        console.print(
            "[yellow]Whizzard config already exists at[/yellow] "
            f"{CONFIG_DIR}."
        )
        console.print("Found:")
        for f in existing:
            console.print(f"  • {f.name}")
        console.print()
        console.print(
            "Use [bold]whiz init --force[/bold] to overwrite, or edit the "
            "existing files directly. See `whiz profile --help`, "
            "`whiz mount --help`, `whiz preset --help`."
        )
        sys.exit(1)


def run_wizard(
    *,
    non_interactive: bool = False,
    force: bool = False,
    build_runner: Callable[[list[str]], int] | None = None,
) -> WizardState:
    """Main entry point. Walks the user through every step in order.

    Returns the populated WizardState (so the CLI command can render the
    Done-summary, and tests can assert what was set up).

    ``build_runner`` is resolved at call time (not as a default arg) so
    tests can monkeypatch ``_default_build_runner`` and have it take effect.
    """
    if build_runner is None:
        # Module attribute lookup at call time picks up monkeypatches.
        build_runner = _default_build_runner

    state = WizardState(non_interactive=non_interactive, force=force)

    # Always make sure the home + config dirs exist before any step
    # tries to write into them.
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    _idempotency_check(force)

    step_welcome(state)
    step_1_image(state, build_runner=build_runner)
    # Steps 1b through 5 + Done land in follow-up commits.

    return state


# ---------- writers (used by later step commits) ----------


def _write_default_profiles() -> list[str]:
    """Serialize the bundled default profiles to PROFILES_FILE.

    Returns the list of profile names that were written.
    """
    profiles = default_profiles()
    payload = {
        "schema_version": 1,
        "profiles": {
            name: {
                "network_enabled": p.network_enabled,
                "duration_seconds": p.duration_seconds,
                "idle_timeout_seconds": p.idle_timeout_seconds,
                "allow_broad_mount": p.allow_broad_mount,
                "description": p.description,
            }
            for name, p in profiles.items()
        },
    }
    PROFILES_FILE.write_text(json.dumps(payload, indent=2) + "\n")
    return list(profiles.keys())


def _write_default_harnesses() -> int:
    """Serialize the bundled default harnesses to HARNESSES_FILE.

    Returns the count of harnesses written.
    """
    harnesses = default_harnesses()
    payload = {"schema_version": 1, "harnesses": harnesses}
    HARNESSES_FILE.write_text(json.dumps(payload, indent=2) + "\n")
    return len(harnesses)


def _hermes_profile_already_exists() -> Path | None:
    """Returns ~/.hermes/ if it exists on the host, else None.

    Used by Step 1b to branch between detect-and-clone (Branch A) and
    install-instructions (Branch B). Cross-platform safe — uses
    ``Path.home()`` which respects ``$HOME`` on POSIX and
    ``%USERPROFILE%`` on Windows.
    """
    candidate = Path.home() / ".hermes"
    return candidate if candidate.exists() else None


# Placeholder export — keeps the module importable while we land
# subsequent commits that implement the remaining steps.
__all__ = [
    "WizardState",
    "run_wizard",
    "step_welcome",
    "step_1_image",
]

# Suppress unused-import linter warning for os, kept for future use
# in cross-platform handling (e.g. expanduser variants on Windows).
_ = os
