"""Host-side lifecycle for the credential-broker sidecar (bar C / D-183, D-184).

A *mediated* launch (``network_mode == "mediated"``) routes the cell's model-API
egress through a broker sidecar so the cell never holds a usable credential and
can reach nothing but the broker. This module owns the Docker plumbing:

    start_broker()                             stop_broker()
    ├─ resolve the real secret host-side       ├─ remove the broker container
    │  (fetch_secret → OneCLI / host-env)      ├─ remove the --internal network
    ├─ write it to a host-only key file        └─ delete the key file
    ├─ create a per-session --internal net
    │  (no NAT, no route out — the cell's
    │   only reachable peer is the broker)
    ├─ start the broker on that net, bind-
    │  mounting the key file read-only
    └─ connect the broker to an egress net
       (its own route to the provider)

The cell (started separately, on the --internal net only — see
docker_cmd.build_run_argv) can address the broker by name but has no route
anywhere else. The real key is on the broker, never in the cell.

Security notes:
  * The key file lives in a 0700 host tmpdir, 0444, bind-mounted read-only into
    the broker container ONLY. The cell has no access to it. It is NOT passed as
    a container env var (which would show in ``docker inspect``). Deleted on
    teardown. (A tmpfs-backed path is a possible hardening follow-up.)
  * Broker start is fail-closed: if the secret can't be resolved or the broker
    doesn't come up, we tear down everything created so far and raise, rather
    than launch a cell with a broken or absent mediation path.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
import time
from dataclasses import dataclass

from whizzard.adapters._credentials import fetch_secret
from whizzard.docker_cmd import _docker_env
from whizzard.images import WHIZZARD_BROKER_IMAGE

#: Egress network the broker is attached to for its own outbound TLS. The
#: default bridge has NAT + the host resolver, which is all the broker needs.
_EGRESS_NETWORK = os.environ.get("WHIZZARD_BROKER_EGRESS_NETWORK", "bridge")
_BROKER_PORT = 8080
_START_TIMEOUT_S = 15.0


class BrokerError(Exception):
    """The broker could not be started (fail-closed)."""


@dataclass(frozen=True)
class BrokerHandle:
    """What a running broker exposes to the launch path + what teardown needs."""

    internal_network: str  # the cell attaches here (and ONLY here)
    container_name: str
    base_url: str  # what the cell sets as ANTHROPIC_BASE_URL
    _key_dir: str  # host tmpdir holding the key file, removed on teardown


def _docker(args: list[str], *, timeout: float = 30.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", *args],
        env=_docker_env(),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _write_key_file(secret: str) -> str:
    """Write the secret to a 0444 file inside a fresh 0700 host tmpdir; return
    the directory. Only the broker (via bind mount) and the host user can read
    it; the cell cannot."""
    key_dir = tempfile.mkdtemp(prefix="whiz-broker-")
    os.chmod(key_dir, stat.S_IRWXU)  # 0700
    key_path = os.path.join(key_dir, "key")
    # Write then tighten to read-only.
    with open(key_path, "w", encoding="utf-8") as f:
        f.write(secret)
    os.chmod(key_path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)  # 0444
    return key_dir


def start_broker(session_id: str, secret_name: str) -> BrokerHandle:
    """Resolve the credential host-side and bring up the broker + its networks.

    Raises BrokerError (fail-closed) on any failure, after cleaning up whatever
    was created. The caller must pass the resulting handle to stop_broker().
    """
    slug = session_id[:24]
    net = f"whiz-int-{slug}"
    container = f"whiz-broker-{slug}"

    # 1. Resolve the real secret host-side. Let credential errors propagate as
    #    BrokerError so the launch fails closed with a clear message.
    try:
        secret = fetch_secret(secret_name).value
    except Exception as e:  # OneCLI*/CredentialUnavailable* — all fail-closed
        raise BrokerError(
            f"could not resolve credential {secret_name!r} for the broker: {e}"
        ) from e

    key_dir = _write_key_file(secret)
    del secret  # do not keep the plaintext in this process longer than needed

    created_network = False
    started_container = False
    try:
        # 2. Per-session internal network: no NAT, no default route out.
        r = _docker(["network", "create", "--internal", net])
        if r.returncode != 0:
            raise BrokerError(f"docker network create failed: {r.stderr.strip()}")
        created_network = True

        # 3. Start the broker on the internal net, key bind-mounted read-only.
        key_path = os.path.join(key_dir, "key")
        r = _docker(
            [
                "run",
                "-d",
                "--name",
                container,
                "--network",
                net,
                "--restart",
                "no",
                "-v",
                f"{key_path}:/run/broker/key:ro",
                WHIZZARD_BROKER_IMAGE,
            ]
        )
        if r.returncode != 0:
            raise BrokerError(f"broker container failed to start: {r.stderr.strip()}")
        started_container = True

        # 4. Give the broker egress for its own outbound TLS to the provider.
        r = _docker(["network", "connect", _EGRESS_NETWORK, container])
        if r.returncode != 0:
            raise BrokerError(
                f"could not attach broker to egress network "
                f"{_EGRESS_NETWORK!r}: {r.stderr.strip()}"
            )

        # 5. Fail closed if the proxy process didn't stay up (e.g. empty key).
        _await_broker_running(container)

        return BrokerHandle(
            internal_network=net,
            container_name=container,
            base_url=f"http://{container}:{_BROKER_PORT}",
            _key_dir=key_dir,
        )
    except Exception:
        # Best-effort rollback of everything created so far (fail-closed).
        if started_container:
            _docker(["rm", "-f", container])
        if created_network:
            _docker(["network", "rm", net])
        shutil.rmtree(key_dir, ignore_errors=True)
        raise


def _await_broker_running(container: str) -> None:
    """Poll until the broker container is Running, or raise with its logs."""
    deadline = time.monotonic() + _START_TIMEOUT_S
    while time.monotonic() < deadline:
        r = _docker(["inspect", "-f", "{{.State.Running}}", container])
        if r.returncode == 0 and r.stdout.strip() == "true":
            return
        # If it exited already, surface why immediately.
        if r.returncode == 0 and r.stdout.strip() == "false":
            break
        time.sleep(0.3)
    logs = _docker(["logs", "--tail", "20", container])
    raise BrokerError(
        f"broker {container!r} did not come up: {logs.stdout.strip()} "
        f"{logs.stderr.strip()}".strip()
    )


def stop_broker(handle: BrokerHandle) -> None:
    """Tear down the broker, its network, and the key file. Best-effort — never
    raises, so it is safe in a finally block."""
    _docker(["rm", "-f", handle.container_name])
    _docker(["network", "rm", handle.internal_network])
    shutil.rmtree(handle._key_dir, ignore_errors=True)
