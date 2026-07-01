"""Host-side lifecycle for the credential-broker sidecar (bar C / D-183, D-184).

A *mediated* launch (``network_mode == "mediated"``) routes the cell's model-API
egress through a broker sidecar so the cell never holds a usable credential and
can reach nothing but the broker. This module owns the Docker plumbing:

    start_broker()                             stop_broker()
    ├─ reap orphaned brokers from prior crashes ├─ remove the broker container
    ├─ resolve the real credential host-side    ├─ remove the two networks
    │  (fetch_secret; API-key or OAuth token)   └─ delete the key file
    ├─ write it to a host-only key file
    ├─ create a per-session --internal net
    │  (no NAT, no route out — the cell's only
    │   reachable peer is the broker)
    ├─ create a per-session EGRESS net (broker-
    │  only; NOT the shared default bridge)
    ├─ start the broker on the --internal net,
    │  bind-mounting the key file read-only
    └─ attach the broker to the egress net

Security notes:
  * The broker's egress interface is a per-session network with the broker as
    its ONLY member, so no other container (e.g. a concurrent open-egress cell
    on the default bridge) can reach the unauthenticated proxy and abuse the
    key. The cell reaches the broker only via the --internal net.
  * The key file lives under STATE_DIR (0700 dir, 0444 file), bind-mounted
    read-only into the broker ONLY, never passed as a container env var, and
    deleted on teardown. Its per-session path lets the reaper clean up files
    left by a crashed session.
  * Start is fail-closed: partial-start failures roll back everything created.
  * A hard kill (SIGKILL/crash) can't run the finally; the reaper sweeps such
    orphans (broker + networks + key file) on the next launch.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from whizzard.adapters._credentials import (
    CredentialUnavailableError,
    OneCLINotInstalledError,
    OneCLISecretMissingError,
    OneCLITimeoutError,
    fetch_secret,
)
from whizzard.config import STATE_DIR
from whizzard.docker_cmd import _docker_env
from whizzard.images import WHIZZARD_BROKER_IMAGE

_BROKER_PORT = 8080
_START_TIMEOUT_S = 15.0
#: Don't reap a broker younger than this — its cell may still be starting (the
#: broker comes up before the cell in _perform_launch). Comfortably covers the
#: broker-up→cell-up window.
_REAP_GRACE_S = 180.0

#: Host-side key files, one dir per session, reapable by the sweep.
_KEY_ROOT = STATE_DIR / "broker-keys"

#: Model-credential candidates in Hermes's own priority order. The resolved
#: one's scheme tells the broker how to inject it: "api_key" → x-api-key;
#: "bearer" → Authorization: Bearer + the oauth beta header.
_CREDENTIAL_CANDIDATES: tuple[tuple[str, str], ...] = (
    ("ANTHROPIC_API_KEY", "api_key"),
    ("ANTHROPIC_TOKEN", "bearer"),
    ("CLAUDE_CODE_OAUTH_TOKEN", "bearer"),
)


class BrokerError(Exception):
    """The broker could not be started (fail-closed)."""


@dataclass(frozen=True)
class BrokerHandle:
    """What a running broker exposes to the launch path + what teardown needs."""

    internal_network: str  # the cell attaches here (and ONLY here)
    egress_network: str  # broker-only; its route to the provider
    container_name: str
    base_url: str  # what the cell sets as ANTHROPIC_BASE_URL
    _key_dir: str  # host dir holding the key file, removed on teardown


def _docker(args: list[str], *, timeout: float = 30.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", *args],
        env=_docker_env(),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _slug(session_id: str) -> str:
    """Docker-name-safe, collision-free per-session slug (full id, sanitized)."""
    return re.sub(r"[^a-zA-Z0-9_.-]", "-", session_id)


def _infer_scheme(secret_name: str) -> str:
    """A raw API key uses x-api-key; a subscription/OAuth token uses Bearer."""
    upper = secret_name.upper()
    if "OAUTH" in upper or "TOKEN" in upper:
        return "bearer"
    return "api_key"


def _resolve_credential(primary_secret: str) -> tuple[str, str]:
    """Resolve the model credential host-side, trying the declared secret first
    then Hermes's known fallbacks. Returns (value, scheme). Fail-closed: raises
    BrokerError if nothing resolves; OneCLI *timeouts* propagate (D-134: no
    fallback past a hung vault)."""
    ordered: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(name: str, scheme: str) -> None:
        if name and name not in seen:
            ordered.append((name, scheme))
            seen.add(name)

    add(primary_secret, _infer_scheme(primary_secret))
    for name, scheme in _CREDENTIAL_CANDIDATES:
        add(name, scheme)

    tried = ", ".join(n for n, _ in ordered)
    for name, scheme in ordered:
        try:
            return fetch_secret(name).value, scheme
        except (CredentialUnavailableError, OneCLISecretMissingError,
                OneCLINotInstalledError):
            continue  # not this one — try the next candidate
    raise BrokerError(
        f"no model credential resolved (tried {tried}) — set one of them as an "
        f"env var or in your OneCLI vault"
    )


def _write_key_file(secret: str, session_id: str) -> str:
    """Write the secret to a 0444 file under a per-session 0700 dir; return the
    dir. Only the broker (via bind mount) and the host user can read it."""
    _KEY_ROOT.mkdir(parents=True, exist_ok=True)
    key_dir = _KEY_ROOT / _slug(session_id)
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


def start_broker(session_id: str, secret_name: str) -> BrokerHandle:
    """Resolve the credential host-side and bring up the broker + its networks.

    Raises BrokerError (fail-closed) on any failure, after cleaning up whatever
    was created. The caller must pass the resulting handle to stop_broker().
    """
    _reap_orphans()  # best-effort sweep of resources left by prior crashes

    slug = _slug(session_id)
    net = f"whiz-int-{slug}"
    egress = f"whiz-egress-{slug}"
    container = f"whiz-broker-{slug}"

    try:
        secret, scheme = _resolve_credential(secret_name)
    except OneCLITimeoutError as e:
        raise BrokerError(f"credential vault timed out: {e}") from e

    key_dir = _write_key_file(secret, session_id)
    del secret

    created_net = created_egress = started = False
    try:
        # 1. Per-session internal network: no NAT, no default route out.
        r = _docker(["network", "create", "--internal", net])
        if r.returncode != 0:
            raise BrokerError(f"docker network create failed: {r.stderr.strip()}")
        created_net = True

        # 2. Per-session EGRESS network — broker-only, so no other container can
        #    reach the (unauthenticated) proxy. NOT the shared default bridge.
        r = _docker(["network", "create", egress])
        if r.returncode != 0:
            raise BrokerError(f"docker egress network create failed: {r.stderr.strip()}")
        created_egress = True

        # 3. Start the broker on the internal net, key bind-mounted read-only,
        #    auth scheme (api_key/bearer) passed via env (host-controlled).
        key_path = os.path.join(key_dir, "key")
        r = _docker([
            "run", "-d",
            "--name", container,
            "--label", "whizzard.broker=1",
            "--network", net,
            "--restart", "no",
            "-e", f"BROKER_AUTH_SCHEME={scheme}",
            "-v", f"{key_path}:/run/broker/key:ro",
            WHIZZARD_BROKER_IMAGE,
        ])
        if r.returncode != 0:
            raise BrokerError(f"broker container failed to start: {r.stderr.strip()}")
        started = True

        # 4. Attach the broker to its egress network for outbound TLS.
        r = _docker(["network", "connect", egress, container])
        if r.returncode != 0:
            raise BrokerError(f"could not attach broker to egress net: {r.stderr.strip()}")

        # 5. Fail closed unless the proxy is actually accepting connections.
        _await_broker_ready(container)

        return BrokerHandle(
            internal_network=net,
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
        if created_net:
            _docker(["network", "rm", net])
        shutil.rmtree(key_dir, ignore_errors=True)
        raise


def _await_broker_ready(container: str) -> None:
    """Poll until the proxy accepts a TCP connection on its port, or raise with
    the container's logs. `docker run -d` reports Running before the entrypoint
    binds, so we probe the actual port (via `docker exec` inside the broker,
    which also catches a broker that crashes on an empty key) rather than
    trusting the Running flag."""
    probe = (
        f"import socket,sys; s=socket.socket(); s.settimeout(2); "
        f"sys.exit(0 if s.connect_ex(('127.0.0.1',{_BROKER_PORT}))==0 else 1)"
    )
    deadline = time.monotonic() + _START_TIMEOUT_S
    while time.monotonic() < deadline:
        r = _docker(["exec", container, "python3", "-c", probe], timeout=10.0)
        if r.returncode == 0:
            return
        # If the broker has exited, stop waiting and surface why.
        state = _docker(["inspect", "-f", "{{.State.Running}}", container])
        if state.returncode == 0 and state.stdout.strip() == "false":
            break
        time.sleep(0.4)
    logs = _docker(["logs", "--tail", "20", container])
    raise BrokerError(
        f"broker {container!r} never became ready: "
        f"{logs.stdout.strip()} {logs.stderr.strip()}".strip()
    )


def stop_broker(handle: BrokerHandle) -> None:
    """Tear down the broker, both networks, and the key file. Best-effort —
    never raises, so it is safe in a finally block."""
    _docker(["rm", "-f", handle.container_name])
    _docker(["network", "rm", handle.egress_network])
    _docker(["network", "rm", handle.internal_network])
    shutil.rmtree(handle._key_dir, ignore_errors=True)


def _reap_orphans() -> None:
    """Sweep broker resources orphaned by a crashed session (the finally never
    ran). Safe: only reaps a broker whose cell (label whizzard.session_id) is
    gone AND that is older than the reap grace, so a broker whose cell is still
    starting is never touched. Best-effort; never raises."""
    try:
        listing = _docker(["ps", "-a", "--filter", "label=whizzard.broker=1",
                           "--format", "{{.Names}}"])
        if listing.returncode != 0:
            return
        for cname in listing.stdout.split():
            if not cname.startswith("whiz-broker-"):
                continue
            slug = cname[len("whiz-broker-"):]
            # Live cell for this session? Then it's an active session — leave it.
            cell = _docker(["ps", "--filter",
                           f"label=whizzard.session_id={slug}", "--format", "{{.ID}}"])
            if cell.returncode == 0 and cell.stdout.strip():
                continue
            if not _older_than_grace(cname):
                continue  # too young — its cell may still be coming up
            _docker(["rm", "-f", cname])
            _docker(["network", "rm", f"whiz-egress-{slug}"])
            _docker(["network", "rm", f"whiz-int-{slug}"])
            shutil.rmtree(_KEY_ROOT / slug, ignore_errors=True)
    except Exception:
        return  # reaping is best-effort; never block a launch


def _older_than_grace(container: str) -> bool:
    r = _docker(["inspect", "-f", "{{.State.StartedAt}}", container])
    if r.returncode != 0:
        return False  # can't tell → conservative, don't reap
    ts = r.stdout.strip()
    # Docker stamps nanosecond precision; fromisoformat wants ≤6 fractional
    # digits — truncate, and normalize the trailing Z.
    ts = re.sub(r"(\.\d{6})\d+", r"\1", ts).replace("Z", "+00:00")
    try:
        started = datetime.fromisoformat(ts)
    except ValueError:
        return False
    age = (datetime.now(UTC) - started).total_seconds()
    return age > _REAP_GRACE_S
