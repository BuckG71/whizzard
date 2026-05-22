"""Adversarial containment smoke — real-Docker probe-and-assert tests.

Each test launches a real contained cell, has it *attempt* to observe or do
something the containment model must prevent, and asserts the attempt was
blocked. These are probes, not payloads: a containment failure shows up as a
pytest assertion failure, never as host damage. Extra margin — on Docker
Desktop the cell runs inside the Docker VM, so even a genuine hole lands in
the VM, not the host OS.

This is the start of the Stage 20 red-team suite, one test per containment
invariant from architecture.md. Gated on real Docker per `conftest.py`; run
with `make integration` or `pytest -m integration`.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_docker_socket_not_reachable(run_in_cell) -> None:
    """The cell must not see the Docker socket. Reaching it would be a full
    host escape — the agent could launch its own uncontained containers
    (D-9 one-way capability flow; D-164 OIQ owns the docker surface)."""
    result = run_in_cell([
        "sh", "-c",
        "test -e /var/run/docker.sock && echo PRESENT || echo absent",
    ])
    assert result.returncode == 0, result.stderr
    assert "absent" in result.stdout
    assert "PRESENT" not in result.stdout


def test_all_capabilities_dropped(run_in_cell) -> None:
    """`--cap-drop=ALL` plus a non-root user means the cell's effective
    capability set is empty. A non-zero CapEff would mean the contained
    process can still perform privileged kernel operations."""
    result = run_in_cell(["sh", "-c", "grep CapEff /proc/self/status"])
    assert result.returncode == 0, result.stderr
    assert "0000000000000000" in result.stdout, (
        f"effective capabilities not fully dropped — containment weakened: "
        f"{result.stdout!r}"
    )


def test_network_off_profile_blocks_egress(run_in_cell) -> None:
    """A network-disabled profile (`safe` → `--network none`) gives the cell
    no egress: the contained agent cannot reach the internet."""
    result = run_in_cell(
        [
            "sh", "-c",
            "curl -s --max-time 5 https://example.com >/dev/null 2>&1 "
            "&& echo REACHED || echo blocked",
        ],
        profile="safe",
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "blocked" in result.stdout
    assert "REACHED" not in result.stdout
