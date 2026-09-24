"""Firecrawl search broker (D-194 Phase C — contained web search).

A **second instance** of the credential-broker proxy (``broker.py`` /
``_dockerfiles/broker/proxy.py``), pinned to ``api.firecrawl.dev``. It gives a
CONTAINED cell web search **without** a Firecrawl key in the cell and **without**
direct web egress from the cell.

Design (per the Fork-1 refinement): reuse the *same* vetted broker image + proxy
code as a second container, rather than teaching the one proxy to route two
upstreams. Each proxy therefore stays **single-upstream** — the containment
invariant ("no code path forwards anywhere else") holds per broker.

Topology: the search broker joins the cell's existing per-session **internal**
network (created by the model broker on a mediated/hybrid launch) so the cell
can reach it, and adds its **own egress** network to reach Firecrawl. The cell
sets ``FIRECRAWL_API_URL`` to this broker + a placeholder key; the broker strips
the placeholder, injects the real key (``Authorization: Bearer`` — proxy scheme
``bearer_plain``, no Anthropic beta header), and forwards to
``api.firecrawl.dev``.
"""

from __future__ import annotations

import os
import shutil
import stat
from dataclasses import dataclass

from whizzard.adapters._credentials import (
    CredentialUnavailableError,
    OneCLINotInstalledError,
    OneCLISecretMissingError,
    OneCLITimeoutError,
    fetch_secret,
)
from whizzard.broker import (
    _BROKER_PORT,
    BrokerError,
    _await_broker_ready,
    _docker,
    _slug,
)
from whizzard.config import STATE_DIR
from whizzard.images import WHIZZARD_BROKER_IMAGE

#: The ONLY host the search broker forwards to. Same single-upstream pinning as
#: the model broker, just a different destination.
_FIRECRAWL_UPSTREAM = "api.firecrawl.dev"
#: Credential the contained rung brokers. Firecrawl uses Authorization: Bearer,
#: so the proxy runs the "bearer_plain" scheme (no Anthropic beta header).
_FIRECRAWL_SECRET = "FIRECRAWL_API_KEY"
#: Host-side key files for the search broker — a separate root from the model
#: broker's so the two per-session key files never collide.
_SEARCH_KEY_ROOT = STATE_DIR / "search-broker-keys"


@dataclass
class SearchBrokerHandle:
    """What a running search broker exposes + what teardown needs."""

    egress_network: str  # search-broker-only; its route to Firecrawl
    container_name: str
    base_url: str  # what the cell sets as FIRECRAWL_API_URL
    _key_dir: str  # host dir holding the key file, removed on teardown


def _write_search_key(secret: str, session_id: str) -> str:
    """Write the Firecrawl key to a 0444 file under a per-session 0700 dir;
    return the dir. Mirrors broker._write_key_file but in the search-key root."""
    _SEARCH_KEY_ROOT.mkdir(parents=True, exist_ok=True)
    key_dir = _SEARCH_KEY_ROOT / _slug(session_id)
    try:
        key_dir.mkdir(mode=0o700, exist_ok=True)
        os.chmod(key_dir, stat.S_IRWXU)  # 0700 (mkdir mode is umask-masked)
        key_path = key_dir / "key"
        with open(key_path, "w", encoding="utf-8") as f:
            f.write(secret)
        os.chmod(key_path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)  # 0444
    except OSError:
        shutil.rmtree(key_dir, ignore_errors=True)
        raise
    return str(key_dir)


def start_search_broker(session_id: str, internal_network: str) -> SearchBrokerHandle:
    """Resolve FIRECRAWL_API_KEY host-side and bring up the search broker on the
    cell's ``internal_network`` (+ its own egress). Fail-closed: raises
    BrokerError after cleaning up whatever was created.

    ``internal_network`` is the per-session ``--internal`` net the cell attaches
    to — created by the model broker (mediated/hybrid). The search broker joins
    it so the cell can reach the broker without any route to the open internet.
    """
    try:
        secret = fetch_secret(_FIRECRAWL_SECRET).value
    except OneCLITimeoutError as e:
        raise BrokerError(f"credential vault timed out: {e}") from e
    except (CredentialUnavailableError, OneCLISecretMissingError,
            OneCLINotInstalledError) as e:
        raise BrokerError(
            f"contained web search needs {_FIRECRAWL_SECRET} — set it as an env "
            f"var or in your OneCLI vault (free key at firecrawl.dev). Or use "
            f"the open profile with keyless ddgs search."
        ) from e

    key_dir = _write_search_key(secret, session_id)
    del secret

    slug = _slug(session_id)
    egress = f"whiz-search-egress-{slug}"
    container = f"whiz-search-broker-{slug}"

    created_egress = started = False
    try:
        # Egress network — search-broker-only, so nothing else can reach the
        # (unauthenticated) proxy. NOT the shared default bridge.
        r = _docker(["network", "create", egress])
        if r.returncode != 0:
            raise BrokerError(
                f"search-broker egress network create failed: {r.stderr.strip()}"
            )
        created_egress = True

        # Start on the CELL's internal net; key bind-mounted read-only; upstream
        # pinned to Firecrawl; bearer_plain auth (no Anthropic beta header).
        key_path = os.path.join(key_dir, "key")
        r = _docker([
            "run", "-d",
            "--name", container,
            "--label", "whizzard.search_broker=1",
            "--network", internal_network,
            "--restart", "no",
            "-e", f"BROKER_UPSTREAM_HOST={_FIRECRAWL_UPSTREAM}",
            "-e", "BROKER_AUTH_SCHEME=bearer_plain",
            "-v", f"{key_path}:/run/broker/key:ro",
            WHIZZARD_BROKER_IMAGE,
        ])
        if r.returncode != 0:
            raise BrokerError(
                f"search-broker container failed to start: {r.stderr.strip()}"
            )
        started = True

        # Attach to its egress network for outbound TLS to Firecrawl.
        r = _docker(["network", "connect", egress, container])
        if r.returncode != 0:
            raise BrokerError(
                f"could not attach search broker to egress net: {r.stderr.strip()}"
            )

        # Fail closed unless the proxy is actually accepting connections.
        _await_broker_ready(container)

        return SearchBrokerHandle(
            egress_network=egress,
            container_name=container,
            base_url=f"http://{container}:{_BROKER_PORT}",
            _key_dir=key_dir,
        )
    except Exception:
        if started:
            _docker(["rm", "-f", container])
        if created_egress:
            _docker(["network", "rm", egress])
        shutil.rmtree(key_dir, ignore_errors=True)
        raise


def stop_search_broker(handle: SearchBrokerHandle) -> None:
    """Tear down the search broker. Removes the container + its OWN egress net +
    the key dir. Does NOT touch the internal net — the model broker owns it and
    removes it in its own teardown (which must run AFTER this, since docker
    won't remove a net while the search broker is still attached)."""
    _docker(["rm", "-f", handle.container_name])
    _docker(["network", "rm", handle.egress_network])
    shutil.rmtree(handle._key_dir, ignore_errors=True)
