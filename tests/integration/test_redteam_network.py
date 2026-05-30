"""Red-team — network policy (cluster 4 of the Stage 20 suite).

The existing ``test_network_off_profile_blocks_egress`` proves a generic
public URL is unreachable when the profile sets ``network_enabled=false``
(``--network none``). This file adds explicit per-path probes for the
three specific reachability surfaces a host-aware attacker would try:

  1. ``host.docker.internal`` — Docker Desktop's host-facing hostname.
     Reachable when network is on (used by the Hermes adapter for the
     Ollama backend); must be unreachable when network is off.
  2. Docker bridge gateway (``172.17.0.1``) — the host-side IP exposed
     to the default Docker bridge. Even without DNS, an attacker who
     knows the gateway address could try to hit host services.
  3. DNS resolution — a cell that can resolve names but can't open
     sockets could still exfiltrate via DNS lookups. ``--network none``
     should remove the resolver entirely.

Each test launches the cell under the bundled ``safe`` profile (network
off) and asserts the specific surface is unreachable. Compared to the
single generic probe, these tests pinpoint *which* surface regressed if
the network posture weakens.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_host_docker_internal_unreachable_under_network_off(run_in_cell) -> None:
    """``host.docker.internal`` is the host-facing hostname Docker Desktop
    publishes. With ``--network none`` it must not resolve and must not
    connect — otherwise a contained agent could reach host-side services
    (e.g., the user's local Ollama at port 11434, the Whizzard CLI's own
    listeners, anything bound to localhost from the host's view)."""
    result = run_in_cell(
        [
            "sh", "-c",
            "curl -s --max-time 5 http://host.docker.internal:11434/ "
            ">/dev/null 2>&1 "
            "&& echo REACHED || echo blocked",
        ],
        profile="safe",
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "blocked" in result.stdout
    assert "REACHED" not in result.stdout, (
        "host.docker.internal reachable under --network none — "
        "host services exposed to the cell"
    )


def test_docker_bridge_gateway_unreachable_under_network_off(run_in_cell) -> None:
    """The Docker bridge's default gateway IP is ``172.17.0.1`` on Linux
    and similar on Docker Desktop. An attacker who knows this address
    could probe it even if DNS fails. ``--network none`` removes the
    bridge entirely; the IP must not respond."""
    result = run_in_cell(
        [
            "sh", "-c",
            "curl -s --max-time 5 http://172.17.0.1/ >/dev/null 2>&1 "
            "&& echo REACHED || echo blocked",
        ],
        profile="safe",
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "blocked" in result.stdout
    assert "REACHED" not in result.stdout, (
        "Docker bridge gateway 172.17.0.1 reachable under --network none — "
        "host-side IPs exposed to the cell"
    )


def test_dns_resolution_unavailable_under_network_off(run_in_cell) -> None:
    """DNS-based exfiltration is a known sub-track of the v1.0 allowlist
    work. Today the only mitigation is ``--network none`` removing the
    resolver entirely. Verify the cell cannot resolve any name when
    network is off — neither via curl, getent, nor any other path. (If
    the cell could resolve names but not open sockets, an attacker could
    still leak data through DNS queries to an attacker-controlled
    nameserver.)"""
    result = run_in_cell(
        [
            "sh", "-c",
            # Try multiple resolution paths; all must fail.
            "getent hosts example.com 2>&1; "
            "echo '---'; "
            "curl -s --max-time 5 https://example.com >/dev/null 2>&1 "
            "&& echo CURL_REACHED || echo curl_blocked; "
            "true",
        ],
        profile="safe",
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    # curl must fail; getent must either fail outright or return nothing.
    assert "CURL_REACHED" not in result.stdout, (
        "example.com reachable under --network none — DNS or egress live"
    )
    # getent returning a resolved IP would mean the resolver is reachable.
    # Resolved IPs look like "93.184.216.34 example.com" — assert no
    # successful resolution line. (Failure modes: empty output, or an
    # error like "Temporary failure in name resolution".)
    lines_before_marker = result.stdout.split("---", 1)[0].strip().splitlines()
    # If getent printed any line containing "example.com" with an IP
    # prefix, that's resolution. Failure cases produce no such line.
    for ln in lines_before_marker:
        # Accept error lines ("name does not resolve", "host not found"),
        # reject resolution lines ("<ip> example.com").
        if "example.com" in ln and ln[:1].isdigit():
            pytest.fail(
                f"DNS resolved example.com under --network none — "
                f"DNS exfil surface still reachable: {ln!r}"
            )
