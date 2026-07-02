"""Shared launch core (`_perform_launch`).

Called by both `whiz run` (CLI flags) and `whiz preset launch` (preset-resolved
args). Handles profile / harness / mount resolution, pre-launch banner, dry-run,
snapshot, and container start. Errors raise typer.Exit with the appropriate
code.
"""

from __future__ import annotations

import time

import typer

from whizzard.adapters import (
    CredentialUnavailableError,
    HermesAdapter,
    OneCLITimeoutError,
    UnknownHarnessTypeError,
    build_adapter,
)
from whizzard.adapters.hermes import (
    MEDIATION_PLACEHOLDER,
    MediationContext,
    OneCLIContext,
)
from whizzard.broker import BrokerError, start_broker, stop_broker
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
from whizzard.onecli_gateway import (
    OneCLIGatewayError,
    start_onecli_route,
    start_onecli_shim,
    stop_onecli_route,
)
from whizzard.safety import OverrideRecord, SafetyViolation, check_mount_path
from whizzard.session_log import new_session_id
from whizzard.snapshot import write_snapshot

# A session that ends almost immediately usually means a one-time setup step
# ran and exited (or an early error) rather than a real working session — worth
# a nudge so the quick return doesn't read as a crash.
_FAST_EXIT_SECONDS = 10


def _print_sandbox_exit_banner(
    *, preset_name: str | None, harness_name: str, fast_exit: bool
) -> None:
    """Announce that the contained session ended and the user is back on the
    host.

    For a containment tool the worst failure mode is a user unknowingly running
    the agent uncontained on the host while believing they're still inside the
    sandbox — a contained session can exit silently (e.g. the harness ran a
    one-time setup and quit) and drop the user back at their host shell with no
    marker. This bookends the entry banner so every boundary crossing is
    announced.
    """
    relaunch = (
        f"whiz r {preset_name}" if preset_name else f"whiz run --harness {harness_name}"
    )
    line = "─" * 60
    console.print()
    console.print(f"[dim]{line}[/dim]")
    console.print(
        "[bold]⊞ Whizzard sandbox session ended — you are back on your HOST.[/bold]"
    )
    console.print(
        "  Commands you run here are [bold]not[/bold] contained. Start another "
        "sandboxed session with:"
    )
    console.print(f"    [green]{relaunch}[/green]")
    if fast_exit:
        console.print(
            "  [dim]The session ended within a few seconds — if this was a "
            "one-time setup step, run the same command again to start your "
            "session.[/dim]"
        )
    console.print(f"[dim]{line}[/dim]")


def _perform_launch(
    *,
    profile_name: str,
    mount_specs: list[str],
    image: str | None,
    dry_run: bool,
    allow_broad_mount: bool,
    harness: str,
    platform_restriction: list[str] | None = None,
    preset_name: str | None = None,
    duration_override_seconds: int | None = None,
    allow_ephemeral: bool = False,
) -> None:
    """Shared launch core. Called by `run` (CLI flags) and `preset launch`
    (preset-resolved args). Handles profile / harness / mount resolution,
    pre-launch banner, dry-run, snapshot, and container start. Errors
    raise typer.Exit with the appropriate code.

    platform_restriction: optional subset of the harness's declared platforms
    (per D-89 amended) — when provided, overlays on the harness config dict
    so the adapter sees the restricted set.

    duration_override_seconds: optional override of the profile's duration
    cap (Stage 15) — a `whiz adjust --extend` relaunch passes the extended
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

    # Harness↔image coupling: with no explicit `--image`, use the image the
    # selected harness needs (Hermes → the Hermes image), not the base. The
    # base image has no `hermes` binary, so `whiz r hermes` on the base used
    # to die inside the container with `exec hermes: No such file or directory`.
    if image is None:
        image = adapter.default_image

    # F-C-04: propagate the --allow-ephemeral opt-in into the adapter so
    # preflight knows whether the user is OK with no persistent HERMES_HOME.
    if isinstance(adapter, HermesAdapter):
        adapter.allow_ephemeral = allow_ephemeral

    # F-C-10: run the adapter preflight before any docker work.
    # `preflight()` is defined on the Protocol (gateway.lock concurrency
    # guard, the D-80 auth.json mount-time check, the F-C-04 hermes_home
    # policy) but used to be defined-and-never-called. Surface ok=False
    # as a clean red error; pass cleanup_note through as an info line so
    # the user sees what changed.
    preflight = adapter.preflight()
    if preflight.cleanup_note:
        console.print(f"[dim]{preflight.cleanup_note}[/dim]")
    if not preflight.ok:
        console.print(f"[red]{preflight.reason or 'preflight failed'}[/red]")
        raise typer.Exit(code=2)

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
    else:
        console.print(
            "[bold]▶ Entering the Whizzard sandbox[/bold] — this session runs "
            "within the limits below."
        )
    console.print(f"[bold]Whizzard Profile:[/bold] {prof.name.upper()}")
    if prof.network_mode == "mediated":
        _net_str = "mediated (broker only — model key stays out of the cell)"
    elif prof.network_mode == "onecli":
        _net_str = "onecli gateway (all credentials injected host-side)"
    elif prof.network_mode == "hybrid":
        _net_str = ("hybrid (model via broker, everything else via OneCLI "
                    "— no credential in the cell)")
    elif prof.network_enabled:
        _net_str = "enabled"
    else:
        _net_str = "disabled"
    console.print(f"[bold]Network:[/bold] {_net_str}")
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

    # Mediated launch (bar C / D-184): the cell reaches only the credential
    # broker. Resolve the model-credential config now (fail closed if a
    # mediated profile has none); the broker itself starts just-in-time on the
    # real path below — dry-run only reports intent.
    mediation_secret: str | None = None
    mediation_base_url_env = "ANTHROPIC_BASE_URL"
    mediation_placeholder = MEDIATION_PLACEHOLDER
    mediated_network: str | None = None
    if prof.network_mode in ("mediated", "hybrid"):
        mc = harness_cfg.get("model_credential") or {}
        mediation_secret = mc.get("secret")
        if not mediation_secret:
            console.print(
                f"[red]profile network_mode is {prof.network_mode!r} but the "
                "harness has no model_credential.secret in harnesses.json.[/red]"
            )
            raise typer.Exit(code=2)
        mediation_base_url_env = mc.get("base_url_env", mediation_base_url_env)
        mediation_placeholder = mc.get("placeholder", mediation_placeholder)

    if dry_run:
        import shlex
        if prof.network_mode == "mediated":
            assert mediation_secret is not None  # guaranteed by the check above
            slug = session_id
            mediated_network = f"whiz-int-{slug}"
            adapter.mediation = MediationContext(  # type: ignore[attr-defined]
                base_url=f"http://whiz-broker-{slug}:8080",
                base_url_env=mediation_base_url_env,
                secret_name=mediation_secret,
                placeholder=mediation_placeholder,
            )
        elif prof.network_mode == "onecli":
            # Dry-run reports intent without touching the OneCLI gateway.
            mediated_network = f"whiz-oc-{session_id}"
            adapter.onecli = OneCLIContext(  # type: ignore[attr-defined]
                proxy_url="http://x:***@onecli:10255",
                ca_host_path="~/.onecli/gateway-ca.pem",
            )
        elif prof.network_mode == "hybrid":
            assert mediation_secret is not None  # guaranteed by the check above
            slug = session_id
            mediated_network = f"whiz-int-{slug}"
            adapter.mediation = MediationContext(  # type: ignore[attr-defined]
                base_url=f"http://whiz-broker-{slug}:8080",
                base_url_env=mediation_base_url_env,
                secret_name=mediation_secret,
                placeholder=mediation_placeholder,
            )
            adapter.onecli = OneCLIContext(  # type: ignore[attr-defined]
                proxy_url="http://x:***@onecli:10255",
                ca_host_path="~/.onecli/gateway-ca.pem",
            )
        argv = build_run_argv(
            prof,
            image=image,
            resolved_mounts=resolved,
            session_id=session_id,
            adapter=adapter,
            mediated_network=mediated_network,
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
    #
    # S20.3 / D-133: fail-closed if the snapshot can't be written. The
    # cooperation-layer contract (D-156) is that the agent's whiz_status
    # reflects host-side constraints; a launch with no readable snapshot
    # leaves the agent blind to its own boundaries. Treat write failure
    # as an abort, not a soft-warning.
    try:
        write_snapshot(
            session_id=session_id,
            profile=prof,
            resolved_mounts=resolved,
            harness_name=adapter.name,
            # F-D-06: pass the effective duration cap (from adjust --extend,
            # if any) so the cell's whiz_status reflects what enforcement
            # is using, not the underlying profile value.
            duration_override_seconds=duration_override_seconds,
        )
    except OSError as e:
        console.print(
            f"[red]error: could not write the per-session snapshot: {e}[/red]"
        )
        console.print(
            "[red]aborting launch — the agent's MCP status surface "
            "requires the snapshot.[/red]"
        )
        raise typer.Exit(code=2) from e

    # F-A6 (catch-up review pass 2): wrap the launch in handlers for the
    # credential-fetch exceptions the Hermes adapter's `container_env()`
    # can raise. Without this, OneCLI timeouts / unavailable secrets
    # surface as raw Python tracebacks to the user instead of the styled
    # red-error path every other launch failure uses. No container has
    # started yet at the raise point (container_env runs in
    # build_run_argv), so no cleanup is needed.
    # Mediated launch: bring up the broker just-in-time (it resolves the real
    # credential host-side and gives us the --internal network the cell will
    # join). Fail closed if it can't start. Torn down in the finally below so
    # the network + container + key file never outlive the session.
    broker_handle = None
    onecli_handle = None
    if prof.network_mode == "mediated":
        assert mediation_secret is not None  # guaranteed by the check above
        try:
            broker_handle = start_broker(session_id, mediation_secret)
        except BrokerError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(code=125) from e
        adapter.mediation = MediationContext(  # type: ignore[attr-defined]
            base_url=broker_handle.base_url,
            base_url_env=mediation_base_url_env,
            secret_name=mediation_secret,
            placeholder=mediation_placeholder,
        )
        mediated_network = broker_handle.internal_network
    elif prof.network_mode == "onecli":
        # Route the cell's egress through the OneCLI gateway (D-187). All
        # configured credentials are injected host-side; the cell holds none.
        try:
            onecli_handle = start_onecli_route(session_id)
        except OneCLIGatewayError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(code=125) from e
        adapter.onecli = OneCLIContext(  # type: ignore[attr-defined]
            proxy_url=onecli_handle.proxy_url,
            ca_host_path=onecli_handle.ca_host_path,
        )
        mediated_network = onecli_handle.internal_network
    elif prof.network_mode == "hybrid":
        # Hybrid (D-187/D-188): the bar-C broker owns the per-session --internal
        # net and injects the MODEL credential (incl. subscription-OAuth's two
        # headers); the OneCLI forwarder shim joins that same net and relays the
        # gateway's proxy port for every OTHER credential. Both fail closed;
        # broker torn down if the shim can't come up.
        assert mediation_secret is not None  # guaranteed by the check above
        try:
            broker_handle = start_broker(session_id, mediation_secret)
        except BrokerError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(code=125) from e
        try:
            onecli_handle = start_onecli_shim(
                session_id, broker_handle.internal_network
            )
        except OneCLIGatewayError as e:
            stop_broker(broker_handle)
            broker_handle = None
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(code=125) from e
        adapter.mediation = MediationContext(  # type: ignore[attr-defined]
            base_url=broker_handle.base_url,
            base_url_env=mediation_base_url_env,
            secret_name=mediation_secret,
            placeholder=mediation_placeholder,
        )
        adapter.onecli = OneCLIContext(  # type: ignore[attr-defined]
            proxy_url=onecli_handle.proxy_url,
            ca_host_path=onecli_handle.ca_host_path,
        )
        mediated_network = broker_handle.internal_network

    launch_started = time.monotonic()
    try:
        result = run_shell(
            prof,
            image=image,
            resolved_mounts=resolved,
            session_id=session_id,
            overrides_used=[{"path": o.path, "reason": o.reason} for o in overrides_used],
            adapter=adapter,
            preset_name=preset_name,
            duration_override_seconds=duration_override_seconds,
            mediated_network=mediated_network,
        )
    except OneCLITimeoutError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=125) from e
    except CredentialUnavailableError as e:
        console.print(f"[red]credential fetch failed: {e}[/red]")
        raise typer.Exit(code=125) from e
    except DockerDaemonError as e:
        # F-B2 (catch-up review pass 2): `run_shell` calls `get_image_id`
        # after the preflight `image_exists` check; a daemon flap between
        # the two leaks a DockerDaemonError past run_shell to the user.
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=125) from e
    finally:
        # Tear the OneCLI shim down FIRST: in hybrid it lives on the broker's
        # net, and docker refuses to remove a net that still has the shim
        # attached. stop_onecli_route only removes the cell net when it owns it
        # (pure onecli), so the broker keeps ownership of its own net in hybrid.
        if onecli_handle is not None:
            stop_onecli_route(onecli_handle)
        if broker_handle is not None:
            stop_broker(broker_handle)

    # The container has exited — the user is back on the host shell. Announce
    # the boundary so a silent return can't be mistaken for still being inside.
    _print_sandbox_exit_banner(
        preset_name=preset_name,
        harness_name=adapter.name,
        fast_exit=(time.monotonic() - launch_started) < _FAST_EXIT_SECONDS,
    )
    raise typer.Exit(code=result.exit_code)
