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
    value, scheme, name = broker._resolve_credential("ANTHROPIC_API_KEY")
    assert value == "sk-real"
    assert scheme == "api_key"
    assert name == "ANTHROPIC_API_KEY"


def test_resolve_credential_falls_back_to_oauth_token(monkeypatch):
    # No API key set, but a subscription/OAuth token is → bearer scheme.
    def fake_fetch(name):
        if name == "CLAUDE_CODE_OAUTH_TOKEN":
            return _result("oauth-token-xyz")
        raise CredentialUnavailableError(name)

    monkeypatch.setattr(broker, "fetch_secret", fake_fetch)
    value, scheme, name = broker._resolve_credential("ANTHROPIC_API_KEY")
    assert value == "oauth-token-xyz"
    assert scheme == "bearer"
    # The name is reported so the launch banner can say what actually resolved,
    # which is not necessarily what the harness declared.
    assert name == "CLAUDE_CODE_OAUTH_TOKEN"


def test_resolve_credential_fails_closed_when_none_resolve(monkeypatch):
    def fake_fetch(name):
        raise CredentialUnavailableError(name)

    monkeypatch.setattr(broker, "fetch_secret", fake_fetch)
    with pytest.raises(BrokerError):
        broker._resolve_credential("ANTHROPIC_API_KEY")


# --- declared scheme beats the name-based guess -----------------------------


def test_infer_scheme_misreads_an_api_key_named_token():
    # The motivating defect: a raw API key called ANTHROPIC_API_TOKEN matches on
    # "TOKEN" and is guessed as bearer, so it goes upstream as
    # `Authorization: Bearer` + an OAuth beta header and earns an opaque 401.
    # Pinned as a KNOWN property of the guess, which is why declaring the
    # scheme exists — not as desired behavior.
    assert broker._infer_scheme("ANTHROPIC_API_TOKEN") == "bearer"


def test_declared_scheme_overrides_the_name_guess(monkeypatch):
    def fake_fetch(name):
        if name == "ANTHROPIC_API_TOKEN":
            return _result("sk-really-an-api-key")
        raise CredentialUnavailableError(name)

    monkeypatch.setattr(broker, "fetch_secret", fake_fetch)
    value, scheme, name = broker._resolve_credential(
        "ANTHROPIC_API_TOKEN", "api_key"
    )
    assert value == "sk-really-an-api-key"
    assert scheme == "api_key"  # declared wins over the "TOKEN" guess
    assert name == "ANTHROPIC_API_TOKEN"


def test_declared_scheme_applies_only_to_the_declared_secret(monkeypatch):
    # A declaration describes the harness's OWN secret. If resolution falls
    # through to one of our known candidates, that candidate's own scheme must
    # win — otherwise declaring "api_key" would send an OAuth token as x-api-key.
    def fake_fetch(name):
        if name == "CLAUDE_CODE_OAUTH_TOKEN":
            return _result("oauth-token-xyz")
        raise CredentialUnavailableError(name)

    monkeypatch.setattr(broker, "fetch_secret", fake_fetch)
    value, scheme, name = broker._resolve_credential("MY_OWN_KEY", "api_key")
    assert value == "oauth-token-xyz"
    assert scheme == "bearer"
    assert name == "CLAUDE_CODE_OAUTH_TOKEN"


def test_undeclared_scheme_still_falls_back_to_the_guess(monkeypatch):
    # Backwards compatibility: a harness config with no `scheme` keeps the
    # pre-existing inferred behavior.
    def fake_fetch(name):
        if name == "SOME_OAUTH_CRED":
            return _result("tok")
        raise CredentialUnavailableError(name)

    monkeypatch.setattr(broker, "fetch_secret", fake_fetch)
    _, scheme, _ = broker._resolve_credential("SOME_OAUTH_CRED")
    assert scheme == "bearer"
