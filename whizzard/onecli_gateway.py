"""Host-side lifecycle for routing a cell's egress through the OneCLI gateway
(bar C companion / D-187, phase 1).

When ``network_mode == "onecli"`` the cell reaches only the user's OneCLI
gateway container, which MITM-injects every configured service credential
host-side (GitHub, Slack, tool APIs, and any API-key / single-header-OAuth
model key) — so none of them ever land in the cell. This module owns the
Docker plumbing:

    start_onecli_route()                        stop_onecli_route()
    ├─ confirm the OneCLI gateway is running     ├─ disconnect the gateway from
    ├─ resolve its proxy token + CA cert         │   the per-session net
    │  (host-side, from `onecli run`)            └─ remove the net
    ├─ create a per-session --internal net
    └─ connect the (persistent, shared) gateway
       container to that net

The cell is launched on the --internal net (no route out) and points its
HTTP(S)_PROXY at the gateway container by name; the gateway is its only
reachable peer. The gateway forwards outbound via its own egress interfaces —
the cell cannot IP-route through it.

Unlike the bar-C broker, the OneCLI gateway is a **persistent, shared**
container (the user's own OneCLI). We only attach/detach it to per-session
networks; we never start or stop it.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from whizzard.docker_cmd import _docker_env

#: The OneCLI gateway container name (env-overridable for non-default installs).
GATEWAY_CONTAINER = os.environ.get("WHIZZARD_ONECLI_CONTAINER", "onecli")
#: CA-trust env vars OneCLI sets so a client trusts the gateway's MITM cert.
CA_ENV_VARS = (
    "NODE_EXTRA_CA_CERTS",
    "SSL_CERT_FILE",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
    "GIT_SSL_CAINFO",
    "DENO_CERT",
)
_DEFAULT_CA_PATH = str(Path.home() / ".onecli" / "gateway-ca.pem")
_REAP_GRACE_S = 180.0


class OneCLIGatewayError(Exception):
    """The OneCLI gateway route could not be established (fail-closed)."""


@dataclass(frozen=True)
class OneCLIHandle:
    internal_network: str
    gateway_container: str
    proxy_url: str  # http://x:<token>@<gateway>:<port> — cell HTTP(S)_PROXY
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


def start_onecli_route(session_id: str) -> OneCLIHandle:
    """Bring up a per-session isolated network and attach the OneCLI gateway to
    it. Fail-closed: raises OneCLIGatewayError (rolling back the net) if the
    gateway is absent, its wiring can't be resolved, or the CA cert is missing.
    """
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
    net = f"whiz-oc-{slug}"

    created = connected = False
    try:
        r = _docker(["network", "create", "--internal", net])
        if r.returncode != 0:
            raise OneCLIGatewayError(f"network create failed: {r.stderr.strip()}")
        created = True

        r = _docker(["network", "connect", net, GATEWAY_CONTAINER])
        if r.returncode != 0:
            raise OneCLIGatewayError(
                f"could not attach the OneCLI gateway to the session net: "
                f"{r.stderr.strip()}"
            )
        connected = True

        return OneCLIHandle(
            internal_network=net,
            gateway_container=GATEWAY_CONTAINER,
            proxy_url=f"http://x:{token}@{GATEWAY_CONTAINER}:{port}",
            ca_host_path=ca_path,
        )
    except Exception:
        if connected:
            _docker(["network", "disconnect", net, GATEWAY_CONTAINER])
        if created:
            _docker(["network", "rm", net])
        raise


def stop_onecli_route(handle: OneCLIHandle) -> None:
    """Detach the gateway and remove the per-session net. Best-effort — never
    raises (safe in a finally). The gateway container itself is left running
    (it's the user's persistent, shared OneCLI)."""
    _docker(["network", "disconnect", handle.internal_network,
             handle.gateway_container])
    _docker(["network", "rm", handle.internal_network])


def attach_gateway_to_net(net: str) -> tuple[str, str]:
    """Attach the OneCLI gateway to an EXISTING per-session net — used by hybrid
    mode, which shares the bar-C broker's --internal net so one cell reaches
    both proxies. Returns (proxy_url, ca_host_path). Fail-closed; does NOT
    create or remove the net (the broker owns its lifecycle)."""
    if not onecli_gateway_available():
        raise OneCLIGatewayError(
            f"the OneCLI gateway container ({GATEWAY_CONTAINER!r}) is not running"
        )
    token, port, ca_path = resolve_onecli_wiring()
    if not os.path.isfile(ca_path):
        raise OneCLIGatewayError(f"OneCLI gateway CA cert not found at {ca_path}")
    r = _docker(["network", "connect", net, GATEWAY_CONTAINER])
    if r.returncode != 0:
        raise OneCLIGatewayError(
            f"could not attach the OneCLI gateway to {net}: {r.stderr.strip()}"
        )
    return f"http://x:{token}@{GATEWAY_CONTAINER}:{port}", ca_path


def detach_gateway_from_net(net: str) -> None:
    """Detach the gateway from a shared net (hybrid teardown). Best-effort;
    never raises. Leaves the gateway container + the net (the broker removes
    the net)."""
    _docker(["network", "disconnect", net, GATEWAY_CONTAINER])


def _reap_orphans() -> None:
    """Sweep per-session onecli nets left by a crashed session (finally never
    ran): a whiz-oc-* net whose cell is gone and that is older than the grace.
    Best-effort; never raises."""
    try:
        listing = _docker(["network", "ls", "--filter", "name=whiz-oc-",
                           "--format", "{{.Name}}"])
        if listing.returncode != 0:
            return
        for net in listing.stdout.split():
            if not net.startswith("whiz-oc-"):
                continue
            slug = net[len("whiz-oc-"):]
            cell = _docker(["ps", "--filter",
                           f"label=whizzard.session_id={slug}", "--format", "{{.ID}}"])
            if cell.returncode == 0 and cell.stdout.strip():
                continue  # live session — leave it
            if not _older_than_grace(net):
                continue
            _docker(["network", "disconnect", net, GATEWAY_CONTAINER])
            _docker(["network", "rm", net])
    except Exception:
        return


def _older_than_grace(net: str) -> bool:
    r = _docker(["network", "inspect", "-f", "{{.Created}}", net])
    if r.returncode != 0:
        return False
    ts = re.sub(r"(\.\d{6})\d+", r"\1", r.stdout.strip()).replace("Z", "+00:00")
    # Docker network Created may carry a numeric tz offset already.
    try:
        created = datetime.fromisoformat(ts)
    except ValueError:
        return False
    return (datetime.now(UTC) - created).total_seconds() > _REAP_GRACE_S
