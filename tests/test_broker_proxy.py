"""Unit tests for the credential-broker reverse proxy's security-critical
pure logic (bar C / D-184). The aiohttp server itself is exercised by the
integration smoke; here we pin the header-rewrite / upstream-allowlist /
key-loading invariants that make the guarantee hold.

The proxy module lives in the broker image build context
(whizzard/_dockerfiles/broker/proxy.py), not the installed package, so it's
imported by path.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_PROXY_PATH = (
    Path(__file__).resolve().parent.parent
    / "whizzard"
    / "_dockerfiles"
    / "broker"
    / "proxy.py"
)


def _load_proxy():
    spec = importlib.util.spec_from_file_location("whiz_broker_proxy", _PROXY_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


proxy = _load_proxy()


def test_upstream_url_is_the_single_allowlisted_host():
    # Whatever path the cell requests, it can only ever land on the one
    # upstream — the egress allowlist is inherent in this mapping.
    url = proxy.build_upstream_url("/v1/messages?beta=true")
    assert url == "https://api.anthropic.com/v1/messages?beta=true"
    assert url.startswith("https://api.anthropic.com/")


def test_real_key_replaces_the_client_placeholder():
    # The cell sends the worthless placeholder in x-api-key; the broker must
    # strip it and inject the real key.
    headers = {"x-api-key": "whiz-proxy-placeholder", "anthropic-version": "2023-06-01"}
    out = proxy.rewrite_request_headers(headers, "sk-REAL-secret")
    assert out["x-api-key"] == "sk-REAL-secret"
    assert out["anthropic-version"] == "2023-06-01"  # passthrough preserved


def test_client_authorization_header_is_stripped():
    headers = {"authorization": "Bearer whatever", "content-type": "application/json"}
    out = proxy.rewrite_request_headers(headers, "sk-REAL")
    assert "authorization" not in {k.lower() for k in out}
    assert out["x-api-key"] == "sk-REAL"
    assert out["content-type"] == "application/json"


def test_hop_by_hop_and_length_headers_dropped():
    headers = {
        "connection": "keep-alive",
        "transfer-encoding": "chunked",
        "content-length": "123",
        "host": "broker:8080",
        "anthropic-beta": "oauth-2025-04-20",
    }
    out = proxy.rewrite_request_headers(headers, "sk-REAL")
    lowered = {k.lower() for k in out}
    assert "connection" not in lowered
    assert "transfer-encoding" not in lowered
    assert "content-length" not in lowered
    # host is reset to the upstream, not the broker
    assert out["host"] == "api.anthropic.com"
    # feature/beta headers survive (needed for OAuth / beta features)
    assert out["anthropic-beta"] == "oauth-2025-04-20"


def test_response_hop_by_hop_stripped():
    resp_headers = {
        "content-type": "text/event-stream",
        "transfer-encoding": "chunked",
        "connection": "close",
    }
    out = proxy.filter_response_headers(resp_headers)
    lowered = {k.lower() for k in out}
    assert "content-type" in lowered
    assert "transfer-encoding" not in lowered
    assert "connection" not in lowered


def test_load_key_reads_and_strips(tmp_path):
    keyfile = tmp_path / "key"
    keyfile.write_text("  sk-REAL-secret\n")
    assert proxy.load_key(str(keyfile)) == "sk-REAL-secret"


def test_load_key_fails_closed_on_empty(tmp_path):
    keyfile = tmp_path / "key"
    keyfile.write_text("   \n")
    with pytest.raises(RuntimeError):
        proxy.load_key(str(keyfile))
