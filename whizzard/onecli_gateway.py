"""Host-side lifecycle for routing a cell's egress through the OneCLI gateway
(bar C companion / D-187; shim isolation / D-188).

When ``network_mode`` is ``onecli`` or ``hybrid`` the cell's service egress goes
through the user's OneCLI gateway, which MITM-injects every configured service
credential host-side — so none of them land in the cell.

The cell never shares a Docker network with the gateway directly. The gateway
also serves an unauthenticated management dashboard/API on :10254 (bound
0.0.0.0, ``AUTH_MODE=local``); a peer on its network can read /api/secrets and
/api/agents. OneCLI offers no supported way to loopback-bind or disable that
port, so instead we interpose a per-session forwarder **shim** (D-188):

    net-cell  (--internal):  cell ── HTTPS_PROXY ──▶ shim
    net-link  (--internal):                         shim ──▶ gateway :<proxy-port> ONLY

The shim (``socat``) relays only the proxy port; it never exposes :10254. The
gateway forwards outbound via its own egress interfaces. Pure ``onecli`` mode
owns net-cell; ``hybrid`` reuses the bar-C broker's net as net-cell (the broker
also lives there for the model call). The gateway is a persistent, shared
container — we only attach/detach it to the per-session net-link.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from whizzard.docker_cmd import _docker_env
from whizzard.images import WHIZZARD_ONECLI_SHIM_IMAGE

#: The OneCLI gateway container name (env-overridable for non-default installs).
GATEWAY_CONTAINER = os.environ.get("WHIZZARD_ONECLI_CONTAINER", "onecli")
#: The CA-trust env vars a client honors to trust the gateway MITM cert live in
#: hermes._ONECLI_CA_ENV_VARS (the injection side). This module doesn't inject.
_DEFAULT_CA_PATH = str(Path.home() / ".onecli" / "gateway-ca.pem")
_REAP_GRACE_S = 180.0


class OneCLIGatewayError(Exception):
    """The OneCLI gateway route could not be established (fail-closed)."""


@dataclass(frozen=True)
class OneCLIHandle:
    internal_network: str  # net-cell — the cell's isolated net
    owns_internal_network: bool  # True (pure onecli, we rm it) / False (hybrid: broker owns it)
    shim_container: str  # per-session forwarder shim
    link_network: str  # net-link — shim <-> gateway (we own it)
    proxy_url: str  # http://x:<token>@<shim>:<port> — cell HTTP(S)_PROXY
    ca_host_path: str  # host path to the gateway CA cert, mounted into the cell


def _docker(args: list[str], *, timeout: float = 30.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", *args], env=_docker_env(),
        capture_output=True, text=True, timeout=timeout,
    )


def _slug(session_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]", "-", session_id)


def onecli_gateway_available() -> bool:
    """True if the OneCLI gateway container is present and running."""
    r = _docker(["ps", "--filter", f"name=^{GATEWAY_CONTAINER}$",
                 "--filter", "status=running", "--format", "{{.Names}}"])
    return r.returncode == 0 and GATEWAY_CONTAINER in r.stdout.split()


def resolve_onecli_wiring() -> tuple[str, str, str]:
    """Return (proxy_token, proxy_port, ca_host_path) from the gateway.

    Runs ``onecli run -- printenv`` once and parses the injected proxy + CA.
    The token is the gateway's basic-auth password; the port is the proxy port
    (distinct from the docs/API port). Fail-closed on any parse failure.
    """
    try:
        r = subprocess.run(["onecli", "run", "--", "printenv"],
                           capture_output=True, text=True, timeout=30)
    except FileNotFoundError as e:
        raise OneCLIGatewayError("`onecli` not found on PATH") from e
    except subprocess.TimeoutExpired as e:
        raise OneCLIGatewayError("OneCLI timed out resolving gateway wiring") from e
    if r.returncode != 0:
        raise OneCLIGatewayError(f"`onecli run` failed: {r.stderr.strip()}")

    env: dict[str, str] = {}
    for line in r.stdout.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            env[k] = v
    proxy = env.get("HTTP_PROXY") or env.get("http_proxy") or ""
    m = re.match(r"https?://[^:@/]*:([^@]+)@[^:@/]+:(\d+)", proxy)
    if not m:
        raise OneCLIGatewayError(
            "could not parse the OneCLI gateway proxy (HTTP_PROXY) — is the "
            "gateway configured?"
        )
    token, port = m.group(1), m.group(2)
    ca_path = env.get("NODE_EXTRA_CA_CERTS") or env.get("SSL_CERT_FILE") \
        or _DEFAULT_CA_PATH
    return token, port, ca_path


def _bring_up_shim(
    session_id: str, cell_net: str, *, owns_cell_net: bool
) -> OneCLIHandle:
    """Create net-link, attach the gateway to it, and start the forwarder shim
    on both net-cell and net-link. Fail-closed with full rollback. Shared by
    pure-onecli (owns_cell_net=True) and hybrid (False) paths."""
    _reap_orphans()
    if not onecli_gateway_available():
        raise OneCLIGatewayError(
            f"the OneCLI gateway container ({GATEWAY_CONTAINER!r}) is not "
            f"running — start OneCLI or use a non-onecli profile"
        )
    token, port, ca_path = resolve_onecli_wiring()
    if not os.path.isfile(ca_path):
        raise OneCLIGatewayError(f"OneCLI gateway CA cert not found at {ca_path}")

    slug = _slug(session_id)
    link_net = f"whiz-oclink-{slug}"
    shim = f"whiz-shim-{slug}"

    link_created = gw_connected = shim_started = False
    try:
        r = _docker(["network", "create", "--internal", link_net])
        if r.returncode != 0:
            raise OneCLIGatewayError(f"link network create failed: {r.stderr.strip()}")
        link_created = True

        r = _docker(["network", "connect", link_net, GATEWAY_CONTAINER])
        if r.returncode != 0:
            raise OneCLIGatewayError(
                f"could not attach the OneCLI gateway to the link net: "
                f"{r.stderr.strip()}"
            )
        gw_connected = True

        # The shim listens on the proxy port on net-cell and relays ONLY that
        # port to the gateway on net-link. socat is a transparent byte relay, so
        # the gateway's Proxy-Authorization/CONNECT flow is untouched.
        r = _docker([
            "run", "-d", "--name", shim, "--network", cell_net,
            "--label", f"whizzard.session_id={session_id}",
            "--label", "whizzard.role=onecli-shim",
            WHIZZARD_ONECLI_SHIM_IMAGE,
            f"TCP-LISTEN:{port},fork,reuseaddr", f"TCP:{GATEWAY_CONTAINER}:{port}",
        ])
        if r.returncode != 0:
            raise OneCLIGatewayError(
                f"could not start the OneCLI forwarder shim (is the "
                f"{WHIZZARD_ONECLI_SHIM_IMAGE} image built? re-run `whiz init`): "
                f"{r.stderr.strip()}"
            )
        shim_started = True

        r = _docker(["network", "connect", link_net, shim])
        if r.returncode != 0:
            raise OneCLIGatewayError(
                f"could not attach the shim to the link net: {r.stderr.strip()}"
            )

        if not _shim_running(shim):
            raise OneCLIGatewayError(
                "the OneCLI forwarder shim exited immediately after start"
            )

        return OneCLIHandle(
            internal_network=cell_net,
            owns_internal_network=owns_cell_net,
            shim_container=shim,
            link_network=link_net,
            proxy_url=f"http://x:{token}@{shim}:{port}",
            ca_host_path=ca_path,
        )
    except Exception:
        if shim_started:
            _docker(["rm", "-f", shim])
        if gw_connected:
            _docker(["network", "disconnect", link_net, GATEWAY_CONTAINER])
        if link_created:
            _docker(["network", "rm", link_net])
        raise


def _shim_running(shim: str) -> bool:
    r = _docker(["inspect", "-f", "{{.State.Running}}", shim])
    return r.returncode == 0 and r.stdout.strip() == "true"


def start_onecli_route(session_id: str) -> OneCLIHandle:
    """Pure onecli mode: create the cell's --internal net (which we own) and
    bring up the shim onto it. Fail-closed; rolls back the net on failure."""
    slug = _slug(session_id)
    cell_net = f"whiz-oc-{slug}"

    _reap_orphans()
    r = _docker(["network", "create", "--internal", cell_net])
    if r.returncode != 0:
        raise OneCLIGatewayError(f"network create failed: {r.stderr.strip()}")
    try:
        return _bring_up_shim(session_id, cell_net, owns_cell_net=True)
    except Exception:
        _docker(["network", "rm", cell_net])
        raise


def start_onecli_shim(session_id: str, cell_net: str) -> OneCLIHandle:
    """Hybrid mode: bring up the shim onto an EXISTING cell net (the bar-C
    broker's --internal net, which the broker owns). Fail-closed."""
    return _bring_up_shim(session_id, cell_net, owns_cell_net=False)


def stop_onecli_route(handle: OneCLIHandle) -> None:
    """Tear down the shim + link net; remove the cell net only if we own it
    (pure onecli — for hybrid the broker removes its own net). Best-effort —
    never raises (safe in a finally). The gateway container is left running."""
    _docker(["rm", "-f", handle.shim_container])
    _docker(["network", "disconnect", handle.link_network, GATEWAY_CONTAINER])
    _docker(["network", "rm", handle.link_network])
    if handle.owns_internal_network:
        _docker(["network", "rm", handle.internal_network])


def _reap_orphans() -> None:
    """Sweep the shim + link net + (pure-onecli) cell net left by a crashed
    session (finally never ran), gated on no-live-cell + older-than-grace. The
    shim container is the anchor — keying on it cleans up both modes. For hybrid
    the broker's own reaper removes its whiz-int-* net. Best-effort; never raises.
    """
    try:
        listing = _docker(["ps", "-a", "--filter", "label=whizzard.role=onecli-shim",
                           "--format", "{{.Names}}"])
        if listing.returncode != 0:
            return
        for shim in listing.stdout.split():
            if not shim.startswith("whiz-shim-"):
                continue
            slug = shim[len("whiz-shim-"):]
            cell = _docker(["ps", "--filter",
                           f"label=whizzard.session_id={slug}", "--format", "{{.ID}}"])
            if cell.returncode == 0 and cell.stdout.strip():
                continue  # live session — leave it
            if not _container_older_than_grace(shim):
                continue
            _docker(["rm", "-f", shim])
            link_net = f"whiz-oclink-{slug}"
            _docker(["network", "disconnect", link_net, GATEWAY_CONTAINER])
            _docker(["network", "rm", link_net])
            # pure-onecli cell net (we own it); no-op if hybrid (broker owns whiz-int-*)
            _docker(["network", "rm", f"whiz-oc-{slug}"])
    except Exception:
        return


def _container_older_than_grace(name: str) -> bool:
    r = _docker(["inspect", "-f", "{{.State.StartedAt}}", name])
    if r.returncode != 0:
        return False
    ts = r.stdout.strip()
    ts = re.sub(r"(\.\d{6})\d+", r"\1", ts).replace("Z", "+00:00")
    try:
        started = datetime.fromisoformat(ts)
    except ValueError:
        return False
    return (datetime.now(UTC) - started).total_seconds() > _REAP_GRACE_S
