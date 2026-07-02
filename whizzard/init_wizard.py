"""Stage 19 / M3 — the `whiz init` first-run wizard.

Walks a new user through five short configuration steps plus a Hermes
profile sub-step. Honors the "no magical defaults" principle: every
non-trivial choice is presented to the user with plain-language context.

Wizard structure (see docs/wizard_design.md for the full transcripts):

  Welcome  (Step 0)              — orientation + "5 short steps" preview
  Step 1   — The Docker container — base + Hermes images built silently
  Step 1b  — Hermes profile setup — detect ~/.hermes/ → clone it, or (if
                                    absent) explain the user-supplied setup
                                    steps; the wizard never installs Hermes
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
import platform
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from whizzard._atomic import atomic_write_text
from whizzard._platform import pick_directory
from whizzard.cli._shared import console
from whizzard.config import (
    CONFIG_DIR,
    PROFILES_FILE,
    Profile,
    default_profiles,
)
from whizzard.docker_cmd import (
    WHIZZARD_BROKER_IMAGE,
    WHIZZARD_HERMES_IMAGE,
    WHIZZARD_IMAGE,
    WHIZZARD_ONECLI_SHIM_IMAGE,
    docker_daemon_status,
)
from whizzard.harness_config import HARNESSES_FILE, default_harnesses
from whizzard.mounts import MOUNTS_FILE
from whizzard.onecli_gateway import onecli_gateway_available
from whizzard.preset_config import PRESETS_FILE
from whizzard.safety import (
    OverrideRecord,
    SafetyViolation,
    check_mount_path,
    hard_block_reason,
)

# Config files the wizard creates. Existence of any → wizard refuses
# unless --force is passed. Idempotency contract for first-run UX.
_CONFIG_FILES = (PROFILES_FILE, MOUNTS_FILE, HARNESSES_FILE, PRESETS_FILE)


def _host_platform() -> str:
    """'windows' | 'macos' | 'linux' — drives OS-aware wizard guidance.

    The wizard's *flow* is identical across platforms; this only tailors
    a few hints (Docker-install link, the Windows Linux-container note,
    example mount paths). It does not branch the steps themselves.
    """
    system = platform.system()
    if system == "Windows":
        return "windows"
    if system == "Darwin":
        return "macos"
    return "linux"


def _example_mount_path() -> str:
    """An example folder path in the host OS's idiom, for the mount prompt."""
    return {
        "windows": r"C:\Users\you\projects",
        "macos": "~/projects",
    }.get(_host_platform(), "~/projects")


def _docker_install_hint() -> str:
    """OS-tailored Docker-install guidance for the missing-Docker error."""
    plat = _host_platform()
    if plat == "windows":
        return (
            "Install Docker Desktop for Windows "
            "(https://docs.docker.com/desktop/install/windows-install/), "
            "make sure it's set to the Linux-container / WSL2 backend, "
            "then re-run `whiz init`."
        )
    if plat == "macos":
        return (
            "Install Docker Desktop for Mac "
            "(https://docs.docker.com/desktop/install/mac-install/) "
            "and re-run `whiz init`."
        )
    return (
        "Install the Docker daemon (or Docker Desktop) and re-run "
        "`whiz init`."
    )


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
    #: How the `default` profile keeps credentials out of the cell (D-187):
    #: "mediated" (model key only), "onecli" (all via OneCLI), or "hybrid"
    #: (OneCLI for services + broker for the model login).
    credential_mode: str = "mediated"


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
    console.print(f"[bold]{message}[/bold]")
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

    # Pre-flight checks — every prerequisite is *verified*, not asserted.
    # docker_daemon_status() actually talks to the daemon (not just a PATH
    # check), so we never print "Docker is running" without confirming it,
    # and the Windows Linux-backend requirement is a real check rather than a
    # dim advisory styled like one (fail-closed, D-133).
    host = _host_platform()
    status, detail = docker_daemon_status()
    if status == "missing":
        console.print(
            f"[red]error: docker not found on PATH.[/red] {_docker_install_hint()}"
        )
        sys.exit(127)
    if status == "unreachable":
        start_hint = (
            "Start Docker Desktop and wait for it to finish starting"
            if host in ("windows", "macos")
            else "Start the Docker daemon (e.g. `systemctl start docker`)"
        )
        console.print(
            "[red]error: Docker is installed but not running.[/red] "
            f"{start_hint}, then re-run `whiz init`."
        )
        if detail:
            console.print(f"  [dim]{detail}[/dim]")
        sys.exit(1)
    if status == "daemon_error":
        # Docker ran but failed for a non-daemon-down reason (e.g. permission
        # denied / not in the docker group). Surface the real error rather
        # than misadvising "start the daemon".
        console.print(
            "[red]error: Docker is installed but the daemon check failed.[/red] "
            f"{detail or 'see docker output above'}"
        )
        sys.exit(1)
    if status == "windows_containers":
        console.print(
            "[red]error: Docker is in Windows-container mode.[/red] "
            "Whizzard's sandbox is a Linux container — switch Docker Desktop to "
            "Linux containers (WSL2 backend), then re-run `whiz init`."
        )
        sys.exit(1)
    dockerfile = Path(str(files("whizzard._dockerfiles") / "Dockerfile"))
    if not dockerfile.exists():
        console.print(
            f"[red]error: bundled Dockerfile not found at {dockerfile}.[/red]"
        )
        sys.exit(2)

    console.print("Checking prerequisites:")
    console.print("  [green]✓[/green] Docker daemon reachable")
    if host == "windows":
        # On Windows this is a real, verified state (status == "ok" means
        # docker info reported OSType=linux). Non-Windows hosts skip the line
        # rather than show a grayed advisory.
        console.print("  [green]✓[/green] Linux-container backend (WSL2)")
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

    # Broker image — the credential-broker sidecar for mediated sessions
    # (bar C / D-184). Build context is whizzard/_dockerfiles/ (its Dockerfile
    # COPYs broker/proxy.py).
    broker_dockerfile = Path(
        str(files("whizzard._dockerfiles") / "Dockerfile.broker")
    )
    broker_context = Path(str(files("whizzard._dockerfiles")))
    broker_rc = build_runner([
        "docker", "build", "-t", WHIZZARD_BROKER_IMAGE,
        "-f", str(broker_dockerfile), str(broker_context),
    ])
    if broker_rc != 0:
        console.print(f"[red]Broker image build failed (exit {broker_rc}).[/red]")
        sys.exit(broker_rc)

    # OneCLI forwarder-shim image — isolates the cell from the OneCLI gateway's
    # management port in onecli/hybrid sessions (D-188). Same build context.
    shim_dockerfile = Path(
        str(files("whizzard._dockerfiles") / "Dockerfile.onecli-shim")
    )
    shim_rc = build_runner([
        "docker", "build", "-t", WHIZZARD_ONECLI_SHIM_IMAGE,
        "-f", str(shim_dockerfile), str(broker_context),
    ])
    if shim_rc != 0:
        console.print(f"[red]OneCLI shim image build failed (exit {shim_rc}).[/red]")
        sys.exit(shim_rc)

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


# ---------- Hermes profile clone ----------


def _clone_hermes_profile(
    name: str,
    source: Path,
    cloner: Callable[[str, Path], Path] | None = None,
) -> Path:
    """Invoke the existing Hermes profile clone primitive.

    Wrapped so tests can substitute a fake. The real implementation
    calls the same code path as `whiz hermes profile create <name>
    --clone-from <source>`.
    """
    if cloner is None:
        cloner = _default_hermes_cloner
    return cloner(name, source)


def _default_hermes_cloner(name: str, source: Path) -> Path:
    """Default Hermes profile clone — uses the adapter's existing
    create_hermes_profile primitive (Stage 8 / D-80 / D-86).

    `source` is the detected host profile, which Step 1b only ever resolves to
    ``~/.hermes`` (see `_hermes_profile_already_exists`). create_hermes_profile
    addresses that profile by the reserved NAME ``"default"``, not by path —
    passing the path as `clone_from` builds a garbled ``~/.hermes-<path>``
    source and fails ("clone source not found").
    """
    from whizzard.adapters import create_hermes_profile

    if source.resolve() != (Path.home() / ".hermes").resolve():
        raise ValueError(
            f"unsupported clone source {source!r}; the wizard only clones the "
            "host default profile (~/.hermes)"
        )
    result = create_hermes_profile(name, clone_from="default")
    return result.path


_CREDENTIAL_MODE_BY_CHOICE = {1: "mediated", 2: "onecli", 3: "hybrid"}


def _prompt_credential_mode(state: WizardState) -> str:
    """Ask how the `default` profile keeps credentials out of the sandbox and
    return the chosen network_mode (D-187). Deliberately avoids internal jargon
    ("broker"/"mediated"/"bar-C") — the labels describe what the user gets."""
    console.print()
    console.print("[bold]Keeping your credentials out of the sandbox[/bold]")
    console.print("─" * 48)
    console.print()
    console.print(
        "Whizzard makes sure the credentials your agent uses — your model "
        "provider's key or login, plus any service tokens — never enter the "
        "sandbox. How it does that depends on your setup."
    )
    console.print()
    onecli_ok = onecli_gateway_available()
    if onecli_ok:
        console.print("  [green]✓ OneCLI detected and running.[/green]")
    else:
        console.print(
            "  [yellow]• OneCLI not detected[/yellow] — options 2 and 3 below "
            "need OneCLI running to work."
        )
    console.print()
    console.print(
        "  [bold]1) Protect my model key[/bold]\n"
        "     Whizzard holds your model provider's API key outside the sandbox;\n"
        "     the agent only ever sees a placeholder.\n"
        "     [dim]Choose this if you don't use OneCLI.[/dim]"
    )
    console.print()
    console.print(
        "  [bold]2) Let OneCLI handle every credential[/bold]\n"
        "     OneCLI injects each credential (model and services) into outbound\n"
        "     requests, so none enter the sandbox.\n"
        "     [dim]Choose this if you use OneCLI and your model uses an API "
        "key.[/dim]"
    )
    console.print()
    console.print(
        "  [bold]3) OneCLI, plus protect my model login[/bold]\n"
        "     OneCLI injects your service credentials; Whizzard separately keeps\n"
        "     your model-provider login out of the sandbox.\n"
        "     [dim]Choose this if you use OneCLI and sign in to your model\n"
        "     provider (subscription / OAuth) rather than an API key.[/dim]"
    )
    console.print()

    if state.non_interactive:
        # Sensible non-interactive default: full coverage when OneCLI is there,
        # model-key protection otherwise.
        choice = 3 if onecli_ok else 1
    else:
        choice = _prompt_numeric_choice(
            "How should credentials be handled for the default profile?",
            options=[
                "Protect my model key (no OneCLI)",
                "Let OneCLI handle every credential",
                "OneCLI, plus protect my model login",
            ],
        )
    mode = _CREDENTIAL_MODE_BY_CHOICE[choice]
    if mode in ("onecli", "hybrid") and not onecli_ok:
        console.print(
            "  [yellow]⚠ You picked a OneCLI option, but OneCLI isn't running "
            "right now. Start OneCLI before you launch, or the session will "
            "stop with a clear error.[/yellow]"
        )
    state.credential_mode = mode
    return mode


def step_2_profiles(state: WizardState) -> None:
    """Step 2 — set up profiles.

    Three top-level options: use all 5 defaults, use minimal subset
    (safe + default), or define-your-own (Option 3 sub-flow).
    """
    console.print()
    console.print("[bold]Step 2 of 5 — Profiles[/bold]")
    console.print("─" * 48)
    console.print()
    console.print(
        "A profile is a named set of rules that controls what an agent "
        "session can do. Every time you launch a session, you pick a "
        "profile, and that profile decides:"
    )
    console.print()
    console.print("  • whether the session can use the internet")
    console.print("  • whether it has a time limit, and how long")
    console.print("  • whether it stops automatically when idle")
    console.print()
    console.print(
        "You can have many profiles for different situations — one strict, "
        "one permissive, one for long tasks — and switch between them by "
        "name."
    )
    console.print()
    console.print("Whizzard ships with five sensible defaults:")
    console.print()
    console.print(
        "  [bold]default[/bold]     internet on, no time limit, no idle limit\n"
        "              [dim](the everyday baseline — productive, always-on)[/dim]"
    )
    console.print()
    console.print(
        "  [bold]safe[/bold]        internet off, 30 min limit, idle stop at 15 min\n"
        "              [dim](running something you don't fully trust)[/dim]"
    )
    console.print()
    console.print(
        "  [bold]build[/bold]       internet on, 2 hour limit, idle stop at 30 min\n"
        "              [dim](development work, long compiles)[/dim]"
    )
    console.print()
    console.print(
        "  [bold]power[/bold]       internet on, 1 hour limit, idle stop at 15 min\n"
        "              [dim](broad access — shorter limit on purpose)[/dim]"
    )
    console.print()
    console.print(
        "  [bold]quarantine[/bold]  internet off, 30 min limit, idle stop at 15 min\n"
        "              [dim](untrusted execution, read-only folders only)[/dim]"
    )
    console.print()

    if state.non_interactive:
        choice = 1
    else:
        choice = _prompt_numeric_choice(
            "How do you want to set up profiles?",
            options=[
                "Use all five defaults [dim](recommended for first run)[/dim]",
                "Use only \"safe\" and \"default\" [dim](minimal — add more later)[/dim]",
                "Start empty and define your own [dim](advanced)[/dim]",
            ],
        )

    if choice == 3:
        names = _step_2_custom_profiles_subflow(state)
    elif choice == 2:
        # Minimal subset: safe + default.
        mode = _prompt_credential_mode(state)
        names = _write_profiles_subset(["safe", "default"], credential_mode=mode)
    else:
        mode = _prompt_credential_mode(state)
        names = _write_default_profiles(credential_mode=mode)

    state.profile_names = names
    console.print()
    console.print(
        f"  [green]✓[/green] wrote {PROFILES_FILE} "
        f"({len(names)} profile{'s' if len(names) != 1 else ''})"
    )
    console.print()
    console.print(
        "  [dim italic]For the curious: profiles are JSON; you can edit "
        "the file directly or use `whiz profile --help` later to see the "
        "commands for adding, listing, or removing profiles.[/dim italic]"
    )


def _write_profiles_subset(
    names: list[str], credential_mode: str = "mediated"
) -> list[str]:
    """Write only the named subset of bundled profiles."""
    all_defaults = default_profiles()
    selected = {n: all_defaults[n] for n in names if n in all_defaults}
    payload = {
        "schema_version": 1,
        "profiles": {
            name: {
                "network_enabled": p.network_enabled,
                # D-184/D-185/D-187: credential privacy by default — the
                # `default` profile keeps credentials out of the cell via the
                # user-chosen posture (mediated / onecli / hybrid). Other
                # profiles keep their derived posture.
                "network_mode": credential_mode if name == "default" else p.network_mode,
                "duration_seconds": p.duration_seconds,
                "idle_timeout_seconds": p.idle_timeout_seconds,
                "allow_broad_mount": p.allow_broad_mount,
                "description": p.description,
            }
            for name, p in selected.items()
        },
    }
    atomic_write_text(PROFILES_FILE, json.dumps(payload, indent=2) + "\n")
    return list(selected.keys())


def _step_2_custom_profiles_subflow(state: WizardState) -> list[str]:
    """Option 3 sub-flow: walk through creating one or more custom
    profiles. Returns the names that were written.
    """
    console.print()
    console.print("[bold]Step 2 of 5 — Profiles — custom setup[/bold]")
    console.print("─" * 48)
    console.print()
    console.print(
        "You chose to define your own profiles. Whizzard needs at least "
        "one to launch anything, so we'll create your first one now. You "
        "can add more later."
    )
    console.print()

    created: dict[str, dict] = {}
    first = True
    while True:
        if first:
            console.print("[dim]──────── First profile ────────[/dim]")
            first = False
        else:
            console.print("[dim]──────── Next profile ────────[/dim]")

        # Name
        console.print()
        console.print("[bold]Pick a short name for this profile.[/bold]")
        console.print(
            "You'll type it to launch sessions with these rules, like "
            "[green]whiz r <preset>[/green] later. Common names: \"work\", "
            "\"scratch\", \"research\". Lowercase, no spaces."
        )
        console.print()
        name = _prompt_text("  name").strip().lower().replace(" ", "")
        if not name:
            console.print(
                "[yellow]name is required.[/yellow] Try again."
            )
            continue

        # Internet
        console.print()
        net_choice = _prompt_numeric_choice(
            "Should sessions using this profile have internet access?",
            options=[
                "Yes [dim](agent can fetch web pages, call APIs, install packages)[/dim]",
                "No  [dim](fully offline — only what's in the sandbox is reachable)[/dim]",
            ],
        )
        network_enabled = net_choice == 1

        # Time limit
        console.print()
        console.print(
            "A time limit auto-stops the session after the time runs out, "
            "even if it's still doing useful work. Useful as a safety net; "
            "not always wanted."
        )
        duration_choice = _prompt_numeric_choice(
            "Should sessions using this profile have a time limit?",
            options=[
                "No time limit [dim](sessions run until you stop them)[/dim]",
                "Yes, set one",
            ],
        )
        if duration_choice == 1:
            duration_seconds: int | None = None
        else:
            console.print()
            console.print(
                "  [bold]How many hours?[/bold] Type a whole number — for "
                "example, type [green]2[/green] for two hours or "
                "[green]8[/green] for eight."
            )
            duration_seconds = _prompt_positive_int("  hours") * 3600

        # Idle limit
        console.print()
        console.print(
            "\"Idle\" means no agent activity, no CPU work, no file changes. "
            "Useful for sessions you might forget about."
        )
        idle_choice = _prompt_numeric_choice(
            "Should sessions stop automatically if idle?",
            options=[
                "No idle limit",
                "Yes, set one",
            ],
        )
        if idle_choice == 1:
            idle_timeout_seconds: int | None = None
        else:
            console.print()
            console.print(
                "  [bold]How many minutes of idle before the session stops?[/bold]"
            )
            console.print(
                "  Type a whole number — for example, [green]30[/green] for "
                "half an hour, or [green]60[/green] for an hour."
            )
            idle_timeout_seconds = _prompt_positive_int("  minutes") * 60

        # Description
        console.print()
        console.print(
            "[bold]A short description (optional, used in `whiz status`):[/bold]"
        )
        description = _prompt_text("  description") or ""

        # Review + confirm
        console.print()
        console.print("[dim]──────── Review ────────[/dim]")
        console.print(f"  name:         {name}")
        console.print(f"  internet:     {'on' if network_enabled else 'off'}")
        console.print(
            "  time limit:   "
            + ("none" if duration_seconds is None else f"{duration_seconds // 3600} hours")
        )
        console.print(
            "  idle limit:   "
            + ("none" if idle_timeout_seconds is None else f"{idle_timeout_seconds // 60} minutes")
        )
        console.print(f"  description:  {description or '(none)'}")
        console.print()

        save_choice = _prompt_numeric_choice(
            "Save this profile?",
            options=["Yes, save and continue", "No, start over"],
        )
        if save_choice == 2:
            console.print("[yellow]discarded.[/yellow] starting over.")
            continue

        created[name] = {
            "network_enabled": network_enabled,
            "duration_seconds": duration_seconds,
            "idle_timeout_seconds": idle_timeout_seconds,
            "allow_broad_mount": False,
            "description": description,
        }
        console.print()
        console.print(
            f"  [green]✓[/green] profile \"{name}\" defined ({len(created)} "
            f"total this session)"
        )

        # Another?
        console.print()
        another = _prompt_numeric_choice(
            "Add another profile?",
            options=["Yes", "No, continue to step 3"],
        )
        if another == 2:
            break
        console.print()

    # Write what we collected.
    payload = {"schema_version": 1, "profiles": created}
    atomic_write_text(PROFILES_FILE, json.dumps(payload, indent=2) + "\n")
    return list(created.keys())


def step_3_mounts(state: WizardState) -> None:
    """Step 3 — register host folders the agent is allowed to see.

    Loop: ask "add a folder?" → collect path/name/description/mode →
    confirm → ask "add another?" → repeat. Empty registry is fine
    (Hermes uses HERMES_HOME for its own profile dir; user-registered
    mounts are for project work).
    """
    console.print()
    console.print("[bold]Step 3 of 5 — Mounts[/bold]")
    console.print("─" * 48)
    console.print()
    console.print(
        "This step is the heart of Whizzard's safety model. Pay attention "
        "here."
    )
    console.print()
    console.print(
        "A \"mount\" tells Whizzard which folders on your computer the agent "
        "is allowed to see. Once a session starts, the mount list is locked "
        "for that session — no flag, no agent request, no edit you make can "
        "change what's mounted. To change mounts, stop the session, edit "
        "the list, then launch a new one. The list is the ceiling, not a "
        "default."
    )
    console.print()
    console.print("For each folder you list, you also pick what the agent can do with it:")
    console.print()
    console.print(
        "  • [bold]read-only[/bold]   agent can look at the files but can't change them"
    )
    console.print(
        "  • [bold]read-write[/bold]  agent can both look at and change the files"
    )
    console.print()
    console.print(
        "At session launch, you can restrict a folder further than its "
        "registered mode (for example, mount a read-write folder as "
        "read-only for that session), but you can never grant more access "
        "than the mode listed here."
    )
    console.print()
    console.print(
        "The list starts empty. You'll typically add folders here for "
        "projects you want an agent to work on."
    )
    console.print()

    mounts: dict[str, dict] = {}

    if state.non_interactive:
        # Default: empty registry. User adds folders later with `whiz mount add`.
        _write_mounts(mounts)
        state.mount_count = 0
        state.mount_names = []
        console.print(
            f"  [green]✓[/green] wrote {MOUNTS_FILE} (0 folders) — "
            "[dim]non-interactive mode; add later with `whiz mount --help`[/dim]"
        )
        return

    add_choice = _prompt_numeric_choice(
        "Add a folder to the list now?",
        options=["Yes", "No"],
    )

    while add_choice == 1:
        console.print()
        path_raw = _prompt_text(
            f"  Path on your computer (e.g. {_example_mount_path()}) "
            "— or type 'pick' to browse"
        )
        if path_raw.strip().lower() == "pick":
            chosen = pick_directory()
            if chosen is None:
                console.print(
                    "[yellow]no folder selected[/yellow] (cancelled, or no file "
                    "dialog available here). Type a path instead."
                )
                continue
            path_raw = chosen
            console.print(f"  [dim]picked: {chosen}[/dim]")
        if not path_raw:
            console.print("[yellow]path required.[/yellow] try again.")
            continue
        resolved = Path(path_raw).expanduser()
        # Reject hard-blocked paths (e.g. ~/.ssh, /) up front — before any
        # dir-creation — since no profile can override them at launch anyway.
        block = hard_block_reason(resolved)
        if block is not None:
            console.print(
                f"[red]can't add that folder:[/red] {resolved} is hard-blocked "
                f"({block}); no profile can mount it."
            )
            continue
        # Offer to create the folder if it doesn't exist yet, so the mount
        # doesn't fail later at launch with "source does not exist".
        if not resolved.exists():
            create = _prompt_numeric_choice(
                f"That folder doesn't exist yet ({resolved}). Create it?",
                options=["Yes, create it", "No, let me pick another path"],
            )
            if create == 2:
                continue
            try:
                resolved.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                console.print(f"[red]couldn't create that folder:[/red] {e}")
                continue
            console.print(f"  [green]✓[/green] created {resolved}")
        # Early safety check — surface hard-blocked paths (e.g. ~/.ssh) here in
        # the wizard rather than at launch. Broad/cloud locations are advised
        # only; per-profile override gating happens at launch.
        other_registered = [
            Path(m["host_path"]).expanduser() for m in mounts.values()
        ]
        try:
            advisories = _wizard_validate_mount_path(resolved, other_registered)
        except SafetyViolation as e:
            console.print(f"[red]can't add that folder:[/red] {e}")
            continue
        if advisories:
            reasons = "; ".join(a.reason for a in advisories)
            console.print(
                f"  [yellow]note:[/yellow] this is a broad or sensitive "
                f"location ({reasons})."
            )
            console.print(
                "  [dim]Launching with it will need a profile that allows "
                "broad mounts (or `--allow-broad-mount`).[/dim]"
            )
        # Keep path string as the user typed; mounts.py expands ~ at load.
        name = _prompt_text(
            "  Name (how you'll refer to it later)"
        ).strip().lower().replace(" ", "-")
        if not name:
            console.print("[yellow]name required.[/yellow] try again.")
            continue
        if name in mounts:
            console.print(
                f"[yellow]\"{name}\" already added in this session — "
                "pick a different name.[/yellow]"
            )
            continue
        description = _prompt_text(
            "  Description (optional — a note for your own reference)"
        )
        console.print()
        mode_choice = _prompt_numeric_choice(
            "Read-only or read-write?",
            options=[
                "read-only   [dim](agent can look at the files but can't change them)[/dim]",
                "read-write  [dim](agent can both look at and change the files)[/dim]",
            ],
        )
        default_mode = "ro" if mode_choice == 1 else "rw"
        mounts[name] = {
            "host_path": path_raw,
            "default_mode": default_mode,
            "description": description,
        }
        console.print()
        console.print(
            f"  [green]✓[/green] added: {name} → {resolved} "
            f"({'read-write' if default_mode == 'rw' else 'read-only'})"
        )
        console.print()
        add_choice = _prompt_numeric_choice(
            "Add another folder?",
            options=["Yes", "No"],
        )

    _write_mounts(mounts)
    state.mount_count = len(mounts)
    state.mount_names = list(mounts.keys())
    console.print()
    console.print(
        f"  [green]✓[/green] wrote {MOUNTS_FILE} "
        f"({len(mounts)} folder{'s' if len(mounts) != 1 else ''})"
    )
    console.print()
    console.print(
        "  [dim italic]For the curious: you can add more folders later "
        "with `whiz mount --help`, or edit the JSON file directly.[/dim italic]"
    )


def _write_mounts(mounts: dict[str, dict]) -> None:
    """Write the mount registry JSON."""
    payload = {"schema_version": 1, "mounts": mounts}
    atomic_write_text(MOUNTS_FILE, json.dumps(payload, indent=2) + "\n")


# Permissive profile used only to run the structural mount checks during the
# wizard. Profile-dependent gating (broad-mount overrides) is deferred to
# launch, when the real profile is known — so this opens both gates and never
# raises on Tier-2 reasons; only profile-independent hard blocks raise here.
_WIZARD_CHECK_PROFILE = Profile(
    name="wizard-check",
    network_enabled=True,
    duration_seconds=None,
    allow_broad_mount=True,
)


def _wizard_validate_mount_path(
    resolved: Path, other_registered: list[Path]
) -> list[OverrideRecord]:
    """Early mount safety check during the wizard.

    Raises SafetyViolation on profile-independent hard blocks (e.g. ``~/.ssh``,
    ``/``) so they surface here rather than at launch. Returns broad/cloud/
    parent override reasons as advisories — those are enforced per-profile at
    launch, not blocked here.
    """
    return check_mount_path(
        resolved,
        _WIZARD_CHECK_PROFILE,
        allow_broad_mount_flag=True,
        other_registered_paths=other_registered,
    )


def step_4_presets(state: WizardState) -> None:
    """Step 4 — define a preset, optionally attaching registered folders.

    Writes both ``harnesses.json`` (the wizard-bundled hermes-cell entry
    pointing at ``~/.hermes-main/``) and ``presets.json``.
    """
    console.print()
    console.print("[bold]Step 4 of 5 — Presets[/bold]")
    console.print("─" * 48)
    console.print()
    console.print(
        "Whizzard doesn't ship its own agent. It gives you a hardened "
        "place to run other people's agents. A \"harness\" is the actual "
        "AI agent runtime that runs inside the sandbox. The Hermes "
        "harness — which you set up in step 1b — is registered for you. "
        "Whizzard currently only supports the Hermes Agent harness but "
        "intends to extend support to additional agent harnesses in the "
        "future."
    )
    console.print()
    console.print("Presets:")
    console.print()
    console.print(
        "Instead of typing out the profile, harness, and folders every "
        "time you launch, you save those choices under a short name — a "
        "preset — and Whizzard remembers them. Then:"
    )
    console.print()
    console.print("  [green]whiz r hermes[/green]")
    console.print()
    console.print(
        "launches whatever you wired into the \"hermes\" preset."
    )
    console.print()
    console.print("Whizzard ships one preset:")
    console.print()
    console.print(
        "  [bold]hermes[/bold]  preset uses the \"default\" profile and "
        "the \"hermes\" harness"
    )
    console.print()

    # Write harnesses.json — wizard-customized hermes-cell pointing at
    # the profile dir we created in Step 1b.
    _write_wizard_harnesses()

    if state.non_interactive:
        choice = 1
    else:
        choice = _prompt_numeric_choice(
            "Use the bundled \"hermes\" preset?",
            options=[
                "Yes [dim](recommended)[/dim]",
                "No — let me define my own now",
                "Skip — I'll set up presets later [dim](advanced)[/dim]",
            ],
        )

    if choice == 3:
        # Skip — write an empty presets.json so subsequent commands have
        # the file shape even if it has no entries.
        _write_presets({})
        state.preset_count = 0
        state.preset_names = []
        console.print()
        console.print(
            f"  [green]✓[/green] wrote {PRESETS_FILE} (0 presets) — "
            "[dim]add later with `whiz preset --help`[/dim]"
        )
        return

    if choice == 2:
        presets = _step_4_custom_preset_subflow(state)
    else:
        # Choice 1: bundled preset, then per-mount attach prompts.
        attached = _step_4_attach_mounts_prompt(state)
        presets = {
            "hermes": {
                "profile": "default",
                "harness": "hermes-cell",
                "mounts": attached,
                "description": "Hermes session (uses ~/.hermes-main profile)",
            }
        }

    _write_presets(presets)
    state.preset_count = len(presets)
    state.preset_names = list(presets.keys())
    attached_summary = ""
    if presets and any(p.get("mounts") for p in presets.values()):
        mount_names = [
            ", ".join(p["mounts"])
            for p in presets.values() if p.get("mounts")
        ]
        attached_summary = f", attached: {'; '.join(mount_names)}"
    console.print()
    console.print(
        f"  [green]✓[/green] wrote {HARNESSES_FILE} (1 harness)"
    )
    console.print(
        f"  [green]✓[/green] wrote {PRESETS_FILE} ("
        f"{len(presets)} preset{'s' if len(presets) != 1 else ''}{attached_summary})"
    )
    console.print()
    console.print(
        "  [dim italic]For the curious: to change the preset later, "
        "see `whiz preset --help`.[/dim italic]"
    )


def _step_4_attach_mounts_prompt(state: WizardState) -> list[str]:
    """Ask the user which registered mounts to attach to the bundled
    "hermes" preset.

    Returns the list of mount names to attach. Handles 0 / 1 / 2+ cases:
    - 0 mounts: skip the prompt entirely.
    - 1 mount: single yes/no.
    - 2+ mounts: per-mount yes/no loop.

    In non-interactive mode, every registered mount is attached.
    """
    if not state.mount_names:
        return []

    if state.non_interactive:
        return list(state.mount_names)

    attached: list[str] = []
    if len(state.mount_names) == 1:
        name = state.mount_names[0]
        console.print()
        console.print(
            f"Your \"{name}\" folder is registered (from step 3). You can "
            "attach it to the preset, which means it'll be mounted every "
            "time you launch a session with that preset. You can change "
            "the attachment later."
        )
        console.print()
        choice = _prompt_numeric_choice(
            "Attach a folder to your preset?",
            options=[
                f"Yes, attach \"{name}\"",
                "No, leave the preset without a folder",
            ],
        )
        if choice == 1:
            attached.append(name)
        return attached

    # 2+ mounts.
    console.print()
    console.print("[bold]Attach folders to your preset?[/bold]")
    console.print()
    console.print(
        f"You have {len(state.mount_names)} folders registered (from "
        "step 3). An attached folder is mounted every time you launch a "
        "session with this preset. You can change attachments later."
    )
    console.print()
    for name in state.mount_names:
        choice = _prompt_numeric_choice(
            f"Attach \"{name}\" to the \"hermes\" preset?",
            options=["Yes", "No"],
        )
        if choice == 1:
            attached.append(name)
        console.print()
    return attached


def _step_4_custom_preset_subflow(state: WizardState) -> dict[str, dict]:
    """Walk the user through defining custom presets. Returns the dict
    of preset_name → preset_spec that will be written to presets.json.
    """
    console.print()
    console.print("[bold]Define your own preset[/bold]")
    console.print()

    created: dict[str, dict] = {}
    first = True
    while True:
        if first:
            first = False
        else:
            console.print()
            console.print("[dim]──────── Next preset ────────[/dim]")
        console.print()
        console.print(
            "Pick a short name for this preset (lowercase, no spaces):"
        )
        name = _prompt_text("  name").strip().lower().replace(" ", "")
        if not name:
            console.print("[yellow]name required.[/yellow] try again.")
            continue
        if name in created:
            console.print(
                f"[yellow]\"{name}\" already defined this session — "
                "pick a different name.[/yellow]"
            )
            continue

        # Profile selection.
        console.print()
        profile_options = state.profile_names or ["default"]
        choice = _prompt_numeric_choice(
            "Which profile should this preset use?", options=profile_options
        )
        profile_name = profile_options[choice - 1]

        # Harness (only hermes today).
        console.print()
        console.print(
            "Harness: hermes (the only supported harness today)"
        )

        # Attach folders (per-mount loop or single yes/no).
        attached: list[str] = []
        if state.mount_names:
            console.print()
            for mount_name in state.mount_names:
                a_choice = _prompt_numeric_choice(
                    f"Attach your \"{mount_name}\" folder to this preset?",
                    options=["Yes", "No"],
                )
                if a_choice == 1:
                    attached.append(mount_name)
                console.print()

        # Review.
        console.print("[dim]──────── Review ────────[/dim]")
        console.print(f"  name:     {name}")
        console.print(f"  profile:  {profile_name}")
        console.print("  harness:  hermes")
        console.print(
            "  folders:  "
            + (", ".join(attached) if attached else "(none)")
        )
        console.print()
        save_choice = _prompt_numeric_choice(
            "Save this preset?",
            options=["Yes, save and continue", "No, start over"],
        )
        if save_choice == 2:
            console.print("[yellow]discarded.[/yellow] starting over.")
            continue

        created[name] = {
            "profile": profile_name,
            "harness": "hermes-cell",
            "mounts": attached,
            "description": "Custom preset created by `whiz init`",
        }
        console.print()
        console.print(
            f"  [green]✓[/green] preset \"{name}\" defined ({len(created)} total)"
        )

        console.print()
        another = _prompt_numeric_choice(
            "Add another preset?",
            options=["Yes", "No, continue to step 5"],
        )
        if another == 2:
            break

    return created


def _write_wizard_harnesses() -> None:
    """Write a wizard-customized harnesses.json with just hermes-cell.

    The bundled hermes-cell points at ~/.hermes-whizzard-cell by default
    (Stage 10 era); the wizard overrides hermes_home to ~/.hermes-main
    so it matches what step 1b created. The `generic` shell harness is
    NOT written — per Stage 19 product decision, shell isn't a featured
    user surface.
    """
    harnesses = {
        "hermes-cell": {
            "type": "agent",
            # D-181: bare `hermes` (interactive chat) is the default, not
            # `hermes gateway run` — a fresh `whiz r hermes` should drop the
            # user into a chat, not an idle gateway. Gateway is opt-in via a
            # manual start_command override.
            "start_command": "hermes",
            "wrap_up_command": "/quit",
            "wrap_up_grace_seconds": 30,
            "hermes_home": "~/.hermes-main",
            "description": "Hermes (interactive chat) inside the Whizzard sandbox",
            # D-185: how the cell's model credential is mediated (bar C). Inert
            # until a mediated profile (network_mode="mediated") uses it, at
            # which point the broker resolves ANTHROPIC_API_KEY host-side and
            # the cell only ever sees a placeholder + the broker URL.
            "model_credential": {
                "provider": "anthropic",
                "secret": "ANTHROPIC_API_KEY",
                "base_url_env": "ANTHROPIC_BASE_URL",
            },
        },
    }
    payload = {"schema_version": 1, "harnesses": harnesses}
    atomic_write_text(HARNESSES_FILE, json.dumps(payload, indent=2) + "\n")


def _write_presets(presets: dict[str, dict]) -> None:
    """Write the presets.json file."""
    payload = {"schema_version": 1, "presets": presets}
    atomic_write_text(PRESETS_FILE, json.dumps(payload, indent=2) + "\n")


def step_5_audit_log(state: WizardState) -> None:
    """Step 5 — informational; explains the audit log location and shape."""
    from whizzard.config import LOGS_DIR

    log_path = LOGS_DIR / "sessions.jsonl"
    console.print()
    console.print("[bold]Step 5 of 5 — Audit log[/bold]")
    console.print("─" * 48)
    console.print()
    console.print("This step is informational — no choices to make.")
    console.print()
    console.print(
        "Whizzard keeps a record of every agent session you run. The "
        "record lives on your computer at:"
    )
    console.print()
    console.print(f"  [green]{log_path}[/green]")
    console.print()
    console.print("For every session, Whizzard writes down:")
    console.print()
    console.print("  • when it started and stopped, and why it stopped")
    console.print("  • which profile, harness, and folders it used")
    console.print(
        "  • the agent's own activity inside the sandbox, if it "
        "chose to write any (an agent can announce what it's doing "
        "through Whizzard's reporting channel)"
    )
    console.print()
    console.print("Three things to know:")
    console.print()
    console.print("  • [italic]The record is yours.[/italic] Nothing is sent anywhere.")
    console.print(
        "  • [italic]The record is plain text.[/italic] One JSON entry per "
        "line — you can grep it, open it in any editor, or feed it to a "
        "script."
    )
    console.print(
        "  • [italic]The record is append-only by Whizzard.[/italic] You "
        "can delete or archive the file yourself, but Whizzard never "
        "rewrites past entries."
    )
    console.print()
    if not state.non_interactive:
        _pause_for_enter("Press Enter to finish setup.")


def _print_credential_privacy_summary(mode: str) -> None:
    """Done-summary line for the chosen credential posture (D-187). Warns (not
    fails) when the posture's prerequisite isn't satisfied yet."""
    from whizzard.adapters._credentials import fetch_secret

    if mode == "onecli":
        if onecli_gateway_available():
            console.print(
                "  Credential privacy: [green]on[/green] — OneCLI injects every "
                "credential; none enter the cell.  [green]✓ OneCLI running[/green]"
            )
        else:
            console.print(
                "  Credential privacy: [green]on[/green] — OneCLI injects every "
                "credential; none enter the cell."
            )
            console.print(
                "  [yellow]⚠ OneCLI isn't running — start it before "
                "[bold]whiz r hermes[/bold], or the launch will stop with a "
                "clear error.[/yellow]"
            )
        return

    if mode == "hybrid":
        if onecli_gateway_available():
            console.print(
                "  Credential privacy: [green]on[/green] — services via OneCLI, "
                "your model login kept out of the cell.  "
                "[green]✓ OneCLI running[/green]"
            )
        else:
            console.print(
                "  Credential privacy: [green]on[/green] — services via OneCLI, "
                "your model login kept out of the cell."
            )
            console.print(
                "  [yellow]⚠ OneCLI isn't running — start it before "
                "[bold]whiz r hermes[/bold], or the launch will stop.[/yellow]"
            )
        console.print(
            "  [dim]Your model login must be resolvable host-side (env var or "
            "OneCLI vault) for the protected model path.[/dim]"
        )
        return

    # mediated (default posture)
    try:
        fetch_secret("ANTHROPIC_API_KEY")
        console.print(
            "  Credential privacy: [green]on[/green] — your model key stays out "
            "of the cell.  [green]✓ ANTHROPIC_API_KEY found[/green]"
        )
    except Exception:
        console.print(
            "  Credential privacy: [green]on[/green] — your model key stays out "
            "of the cell."
        )
        console.print(
            "  [yellow]⚠ ANTHROPIC_API_KEY isn't resolvable yet — set it (env "
            "var or OneCLI vault) before [bold]whiz r hermes[/bold], or the "
            "launch will stop with a clear error.[/yellow]"
        )


def step_done_summary(state: WizardState) -> None:
    """Final page — recap what was set up and suggest first commands."""
    from whizzard.config import LOGS_DIR

    console.print()
    console.print("[bold green]Setup complete.[/bold green]")
    console.print("─" * 48)
    console.print()
    console.print("Here's what you set up:")
    console.print()
    image_status = "[green]✓ built[/green]" if state.hermes_image_built else "—"
    console.print(f"  Sandbox image:     {WHIZZARD_HERMES_IMAGE}        {image_status}")
    if state.hermes_profile_path is not None:
        console.print(
            f"  Hermes profile:    {state.hermes_profile_path}        "
            "[green]✓ cloned[/green]"
        )
    elif state.hermes_branch == "B":
        console.print(
            "  Hermes profile:    [yellow](not yet — install Hermes "
            "and run `whiz hermes profile create main`)[/yellow]"
        )
    profiles_str = ", ".join(state.profile_names) if state.profile_names else "(none)"
    console.print(f"  Profiles:          {profiles_str}        [green]{len(state.profile_names)}[/green]")
    if state.mount_names:
        mounts_str = ", ".join(state.mount_names)
        console.print(
            f"  Mounted folders:   {mounts_str}        [green]{state.mount_count}[/green]"
        )
    else:
        console.print("  Mounted folders:   (none)        [green]0[/green]")
    presets_str = ", ".join(state.preset_names) if state.preset_names else "(none)"
    console.print(f"  Preset:            {presets_str}        [green]{state.preset_count}[/green]")
    console.print(f"  Audit log:         {LOGS_DIR / 'sessions.jsonl'}")

    # D-184/D-185/D-187: credential privacy is on by default. Confirm the chosen
    # posture's prerequisite resolves now (warn, don't fail) so a fresh user
    # learns before their first launch rather than at a fail-closed launch error.
    _print_credential_privacy_summary(state.credential_mode)
    console.print()
    console.print("A few first commands to try:")
    console.print()
    console.print(
        "  [green]whiz[/green]              "
        "show what's running and what you have set up"
    )
    if state.preset_count and "hermes" in state.preset_names:
        console.print(
            "  [green]whiz r hermes[/green]     launch a Hermes session"
        )
    console.print("  [green]whiz --help[/green]       list every command")
    console.print(
        "  [green]whiz hermes --help[/green]  manage your Hermes profile"
    )
    console.print()
    console.print(
        "[bold yellow]⚠ WARNING: Always launch Hermes with Whizzard controls in "
        "place via the `whiz r hermes` command[/bold yellow]"
    )
    console.print()
    console.print(
        "   Running `hermes` directly in CLI (outside Whizzard) is UNCONTAINED — "
        "Hermes would have full access to your computer, with none of the "
        "capability controls Whizzard provides."
    )
    console.print()


def _prompt_positive_int(label: str) -> int:
    """Prompt for a positive integer, re-prompting until valid."""
    while True:
        raw = _prompt_text(label).strip()
        try:
            n = int(raw)
        except ValueError:
            console.print(
                "[yellow]please enter a whole number greater than zero[/yellow]"
            )
            continue
        if n > 0:
            return n
        console.print(
            "[yellow]please enter a whole number greater than zero[/yellow]"
        )


def step_1b_hermes_profile(
    state: WizardState,
    cloner: Callable[[str, Path], Path] | None = None,
) -> None:
    """Step 1b — set up the Hermes profile sandbox sessions will use.

    Detects ``~/.hermes/`` on the host:
    - Present (Branch A): offer to clone it into ``~/.hermes-main/``
    - Absent (Branch B): explain why a harness is needed + the steps to
      install/configure one, then continue setup. Whizzard does not install
      the harness itself (D-182 — harness is user-supplied).

    Either branch leaves ``whiz init`` runnable to completion — Branch B
    users just need to install + configure Hermes, then create a profile,
    before the bundled "hermes" preset will launch a working session.
    """
    console.print()
    console.print("[bold]Step 1b of 5 — Hermes profile setup[/bold]")
    console.print("─" * 48)
    console.print()
    console.print(
        "The sandbox is built and ready. Hermes also needs a profile — "
        "a folder on your computer that holds the agent's model config "
        "(which LLM to use), persona, memories, and skills. Whizzard "
        "reads from it when it launches Hermes inside the sandbox."
    )
    console.print()

    detected = _hermes_profile_already_exists()

    if detected is None:
        # Branch B — no Hermes profile found (Hermes not installed, or
        # installed but not yet configured). Informational only: Whizzard
        # does not install the harness for you (D-182). Lead with why a
        # harness is required, then the steps, then the reassurance.
        state.hermes_branch = "B"
        console.print(
            "Whizzard runs an agent harness inside the sandbox — it needs at "
            "least one installed and configured to do its job. Hermes is the "
            "supported harness today."
        )
        console.print()
        console.print(
            "[yellow]No Hermes profile was found at ~/.hermes/, so Hermes "
            "isn't set up on this computer yet.[/yellow]"
        )
        console.print()
        console.print("Three steps get it working (you can do them after setup):")
        console.print()
        console.print(
            "  1. [bold]Install Hermes[/bold] following Nous Research's instructions"
        )
        console.print("     [green]https://github.com/NousResearch/hermes-agent[/green]")
        console.print(
            "     [dim](Whizzard's README notes the Hermes version it's tested "
            "against.)[/dim]"
        )
        console.print()
        console.print(
            "  2. [bold]Configure Hermes[/bold] so it creates a profile at ~/.hermes/"
        )
        console.print(
            "     [dim](run Hermes once and complete its setup — model, persona, "
            "etc.)[/dim]"
        )
        console.print()
        console.print("  3. [bold]Create a Whizzard profile from it[/bold] — run:")
        console.print("       [green]whiz hermes profile create main[/green]")
        console.print(
            "     [dim](copies ~/.hermes/ into ~/.hermes-main/, which the bundled "
            "\"hermes\" preset uses)[/dim]"
        )
        console.print()
        console.print(
            "You can finish `whiz init` now — Whizzard's other commands work "
            "without Hermes. The \"hermes\" preset just won't launch a working "
            "session until the three steps above are done."
        )
        console.print()
        if not state.non_interactive:
            _pause_for_enter("Press Enter to continue with setup.")
        return

    # Branch A — Hermes detected; offer to clone.
    state.hermes_branch = "A"
    target = Path.home() / ".hermes-main"
    console.print("[bold]Hermes detected on your computer.[/bold]")
    console.print()
    console.print(
        f"You already have Hermes installed at [green]{detected}[/green]. "
        "Whizzard can copy that setup into a profile that sessions inside "
        "the sandbox will use. Your existing Hermes setup on the host is "
        "not changed — Whizzard only reads from it."
    )
    console.print()
    console.print(
        f"The copy lives at [green]{target}[/green] and includes your "
        "model config, persona, memories, and skills."
    )
    console.print()

    if state.non_interactive:
        # Default in --yes mode: clone the profile.
        choice = 1
    else:
        choice = _prompt_numeric_choice(
            "Copy your Hermes setup into a Whizzard profile?",
            options=[
                "Yes (recommended — gets you running right away)",
                "No  (I'll set up a profile later with `whiz hermes profile create`)",
            ],
        )

    if choice == 2:
        # User declined the clone — leave a footer note.
        console.print()
        console.print(
            "  [dim]Skipped. Run `whiz hermes profile create main` "
            "when you're ready.[/dim]"
        )
        return

    # Proceed with the clone.
    console.print()
    console.print(f"  [dim]cloning {detected} → {target} ...[/dim]")
    try:
        path = _clone_hermes_profile("main", detected, cloner=cloner)
    except Exception as e:  # noqa: BLE001 -- surface anything the cloner raises
        console.print(f"[red]profile clone failed:[/red] {e}")
        console.print(
            "You can retry later with [green]whiz hermes profile create main[/green]."
        )
        return
    state.hermes_profile_path = path
    console.print(f"  [green]✓[/green] profile \"main\" created at {path}")
    console.print()
    console.print(
        "  [dim italic]For the curious: the bundled \"hermes\" preset in "
        "step 4 uses this profile by default. To use a different profile, "
        "create one with `whiz hermes profile create <name>`.[/dim italic]"
    )


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
    step_1b_hermes_profile(state)
    step_2_profiles(state)
    step_3_mounts(state)
    step_4_presets(state)
    step_5_audit_log(state)
    step_done_summary(state)

    return state


# ---------- writers (used by later step commits) ----------


def _write_default_profiles(credential_mode: str = "mediated") -> list[str]:
    """Serialize the bundled default profiles to PROFILES_FILE.

    Returns the list of profile names that were written.
    """
    profiles = default_profiles()
    payload = {
        "schema_version": 1,
        "profiles": {
            name: {
                "network_enabled": p.network_enabled,
                # D-184/D-185/D-187: credential privacy by default — the
                # `default` profile keeps credentials out of the cell via the
                # user-chosen posture (mediated / onecli / hybrid). Other
                # profiles keep their derived posture.
                "network_mode": credential_mode if name == "default" else p.network_mode,
                "duration_seconds": p.duration_seconds,
                "idle_timeout_seconds": p.idle_timeout_seconds,
                "allow_broad_mount": p.allow_broad_mount,
                "description": p.description,
            }
            for name, p in profiles.items()
        },
    }
    atomic_write_text(PROFILES_FILE, json.dumps(payload, indent=2) + "\n")
    return list(profiles.keys())


def _write_default_harnesses() -> int:
    """Serialize the bundled default harnesses to HARNESSES_FILE.

    Returns the count of harnesses written.
    """
    harnesses = default_harnesses()
    payload = {"schema_version": 1, "harnesses": harnesses}
    atomic_write_text(HARNESSES_FILE, json.dumps(payload, indent=2) + "\n")
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
