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
