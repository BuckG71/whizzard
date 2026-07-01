"""Unit tests for the broker host-side logic that doesn't need Docker — the
credential-resolution + auth-scheme rules that decide how the broker injects
(bar C / D-184). The Docker orchestration + isolation is covered by the
acceptance smoke."""

from __future__ import annotations

import types

import pytest

from whizzard import broker
from whizzard.adapters._credentials import CredentialUnavailableError
from whizzard.broker import BrokerError


def _result(value: str):
    return types.SimpleNamespace(value=value)


def test_infer_scheme_api_key_vs_bearer():
    assert broker._infer_scheme("ANTHROPIC_API_KEY") == "api_key"
    assert broker._infer_scheme("ANTHROPIC_TOKEN") == "bearer"
    assert broker._infer_scheme("CLAUDE_CODE_OAUTH_TOKEN") == "bearer"


def test_slug_sanitizes_and_keeps_full_id():
    assert broker._slug("abc-123.def") == "abc-123.def"
    assert "/" not in broker._slug("a/b c")
    assert " " not in broker._slug("a b")


def test_resolve_credential_prefers_the_api_key(monkeypatch):
    def fake_fetch(name):
        if name == "ANTHROPIC_API_KEY":
            return _result("sk-real")
        raise CredentialUnavailableError(name)

    monkeypatch.setattr(broker, "fetch_secret", fake_fetch)
    value, scheme = broker._resolve_credential("ANTHROPIC_API_KEY")
    assert value == "sk-real"
    assert scheme == "api_key"


def test_resolve_credential_falls_back_to_oauth_token(monkeypatch):
    # No API key set, but a subscription/OAuth token is → bearer scheme.
    def fake_fetch(name):
        if name == "CLAUDE_CODE_OAUTH_TOKEN":
            return _result("oauth-token-xyz")
        raise CredentialUnavailableError(name)

    monkeypatch.setattr(broker, "fetch_secret", fake_fetch)
    value, scheme = broker._resolve_credential("ANTHROPIC_API_KEY")
    assert value == "oauth-token-xyz"
    assert scheme == "bearer"


def test_resolve_credential_fails_closed_when_none_resolve(monkeypatch):
    def fake_fetch(name):
        raise CredentialUnavailableError(name)

    monkeypatch.setattr(broker, "fetch_secret", fake_fetch)
    with pytest.raises(BrokerError):
        broker._resolve_credential("ANTHROPIC_API_KEY")
