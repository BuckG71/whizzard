"""Unit tests for the OneCLI-gateway host-side logic that doesn't need Docker —
the proxy/CA wiring parse (D-187). The Docker attach/detach + isolation is
covered by the acceptance smoke."""

from __future__ import annotations

import types

import pytest

from whizzard import onecli_gateway as og
from whizzard.onecli_gateway import OneCLIGatewayError


def _fake_run(stdout: str, returncode: int = 0):
    def _run(*a, **k):
        return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr="")
    return _run


def test_resolve_wiring_parses_proxy_token_port_and_ca(monkeypatch):
    out = (
        "HTTP_PROXY=http://x:aoc_tok123abc@127.0.0.1:10255\n"
        "HTTPS_PROXY=http://x:aoc_tok123abc@127.0.0.1:10255\n"
        "NODE_EXTRA_CA_CERTS=/home/u/.onecli/gateway-ca.pem\n"
        "OTHER=ignored\n"
    )
    monkeypatch.setattr(og.subprocess, "run", _fake_run(out))
    token, port, ca = og.resolve_onecli_wiring()
    assert token == "aoc_tok123abc"
    assert port == "10255"
    assert ca == "/home/u/.onecli/gateway-ca.pem"


def test_resolve_wiring_fails_closed_without_a_proxy(monkeypatch):
    monkeypatch.setattr(og.subprocess, "run", _fake_run("FOO=bar\n"))
    with pytest.raises(OneCLIGatewayError):
        og.resolve_onecli_wiring()


def test_resolve_wiring_fails_closed_on_nonzero_exit(monkeypatch):
    monkeypatch.setattr(og.subprocess, "run", _fake_run("", returncode=1))
    with pytest.raises(OneCLIGatewayError):
        og.resolve_onecli_wiring()


def test_slug_sanitizes_and_keeps_full_id():
    assert og._slug("abc-123.def") == "abc-123.def"
    assert "/" not in og._slug("a/b c")
    assert " " not in og._slug("a b")


# --- shim topology (D-188), Docker calls mocked ----------------------------


def _mock_docker_ok(og_mod, monkeypatch):
    """Make every _docker() call 'succeed'; record the argv lists. inspect
    (shim-running probe) reports 'true'."""
    calls: list[list[str]] = []

    def fake(args, **kw):
        calls.append(args)
        out = "true" if args and args[0] == "inspect" else ""
        return types.SimpleNamespace(returncode=0, stdout=out, stderr="")

    monkeypatch.setattr(og_mod, "_docker", fake)
    monkeypatch.setattr(og_mod, "onecli_gateway_available", lambda: True)
    monkeypatch.setattr(og_mod, "resolve_onecli_wiring", lambda: ("tok", "10255", "/ca.pem"))
    monkeypatch.setattr(og_mod.os.path, "isfile", lambda p: True)
    monkeypatch.setattr(og_mod, "_reap_orphans", lambda: None)
    return calls


def test_start_onecli_route_builds_shim_topology(monkeypatch):
    calls = _mock_docker_ok(og, monkeypatch)
    h = og.start_onecli_route("sid123")

    assert h.internal_network == "whiz-oc-sid123"
    assert h.owns_internal_network is True
    assert h.shim_container == "whiz-shim-sid123"
    assert h.link_network == "whiz-oclink-sid123"
    # cell reaches the SHIM (not the gateway) — token relayed transparently
    assert h.proxy_url == "http://x:tok@whiz-shim-sid123:10255"
    assert h.ca_host_path == "/ca.pem"

    joined = [" ".join(c) for c in calls]
    # cell net + link net created --internal; gateway + shim on link; shim runs
    # on the cell net forwarding ONLY the proxy port to the gateway.
    assert any("network create --internal whiz-oc-sid123" in j for j in joined)
    assert any("network create --internal whiz-oclink-sid123" in j for j in joined)
    assert any("network connect whiz-oclink-sid123 onecli" in j for j in joined)
    assert any("run -d --name whiz-shim-sid123 --network whiz-oc-sid123" in j for j in joined)
    assert any("TCP-LISTEN:10255,fork,reuseaddr" in j and "TCP:onecli:10255" in j for j in joined)
    # the gateway is NEVER attached to the cell net (that was the :10254 hole)
    assert not any("network connect whiz-oc-sid123 onecli" in j for j in joined)


def test_hybrid_shim_does_not_own_cell_net(monkeypatch):
    _mock_docker_ok(og, monkeypatch)
    h = og.start_onecli_shim("sid9", "whiz-int-sid9")  # broker's net
    assert h.internal_network == "whiz-int-sid9"
    assert h.owns_internal_network is False


def test_stop_onecli_route_removes_cell_net_only_when_owned(monkeypatch):
    calls = _mock_docker_ok(og, monkeypatch)
    owned = og.OneCLIHandle("whiz-oc-a", True, "whiz-shim-a", "whiz-oclink-a", "http://x:t@s:1", "/ca")
    guest = og.OneCLIHandle("whiz-int-b", False, "whiz-shim-b", "whiz-oclink-b", "http://x:t@s:1", "/ca")

    calls.clear()
    og.stop_onecli_route(owned)
    joined = [" ".join(c) for c in calls]
    assert any("rm -f whiz-shim-a" in j for j in joined)
    assert any("network rm whiz-oclink-a" in j for j in joined)
    assert any("network rm whiz-oc-a" in j for j in joined)  # owns → removes cell net

    calls.clear()
    og.stop_onecli_route(guest)
    joined = [" ".join(c) for c in calls]
    assert any("rm -f whiz-shim-b" in j for j in joined)
    assert any("network rm whiz-oclink-b" in j for j in joined)
    assert not any("network rm whiz-int-b" in j for j in joined)  # broker owns it
