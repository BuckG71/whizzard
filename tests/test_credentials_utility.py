"""Tests for the OneCLI + env-var credential utility (Stage 12).

Covers the shared adapter-private utility introduced in `whizzard/adapters/
_credentials.py`. Adapters consume `fetch_secret(name)` which tries OneCLI
first and falls back to a host env var; tests for adapter-side consumption
live in `test_hermes_adapter.py`.
"""

import subprocess

import pytest

from whizzard.adapters import (
    CredentialUnavailableError,
    OneCLINotInstalledError,
    OneCLISecretMissingError,
    OneCLITimeoutError,
    SecretFetchResult,
    fetch_secret,
)
from whizzard.adapters import _credentials as creds_module

# --- Internal OneCLI shell-out helper (`_fetch_via_onecli`) ---


def test_fetch_via_onecli_calls_onecli_with_expected_argv(monkeypatch):
    captured = {}

    class _Result:
        returncode = 0
        stdout = "the-secret-value\n"
        stderr = ""

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return _Result()

    monkeypatch.setattr(subprocess, "run", fake_run)

    secret = creds_module._fetch_via_onecli("DISCORD_BOT_TOKEN")

    assert captured["argv"] == ["onecli", "secrets", "get", "DISCORD_BOT_TOKEN"]
    assert captured["kwargs"]["timeout"] == creds_module._ONECLI_TIMEOUT_SECONDS
    assert captured["kwargs"]["capture_output"] is True
    assert captured["kwargs"]["text"] is True
    assert secret == "the-secret-value"


def test_fetch_via_onecli_raises_not_installed_on_filenotfound(monkeypatch):
    def fake_run(argv, **kwargs):
        raise FileNotFoundError("[Errno 2] No such file or directory: 'onecli'")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(OneCLINotInstalledError, match="onecli"):
        creds_module._fetch_via_onecli("DISCORD_BOT_TOKEN")


def test_fetch_via_onecli_raises_secret_missing_on_nonzero_return(monkeypatch):
    class _Result:
        returncode = 1
        stdout = ""
        stderr = "secret not found in vault"

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _Result())

    with pytest.raises(OneCLISecretMissingError, match="DISCORD_BOT_TOKEN"):
        creds_module._fetch_via_onecli("DISCORD_BOT_TOKEN")


# --- Public `fetch_secret` with OneCLI-first / env-var-fallback semantics ---


def test_fetch_secret_returns_onecli_source_when_available(monkeypatch):
    monkeypatch.setattr(
        creds_module, "_fetch_via_onecli", lambda name: "from-onecli"
    )

    result = fetch_secret("DISCORD_BOT_TOKEN")
    assert result.value == "from-onecli"
    assert result.source == "onecli"


def test_fetch_secret_falls_back_to_host_env_when_onecli_not_installed(monkeypatch):
    def raises_not_installed(name):
        raise OneCLINotInstalledError("onecli not on PATH")

    monkeypatch.setattr(creds_module, "_fetch_via_onecli", raises_not_installed)
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "from-host-env")

    result = fetch_secret("DISCORD_BOT_TOKEN")
    assert result.value == "from-host-env"
    assert result.source == "host-env"


def test_fetch_secret_falls_back_to_host_env_when_onecli_missing_secret(monkeypatch):
    def raises_missing(name):
        raise OneCLISecretMissingError(f"OneCLI doesn't have {name}")

    monkeypatch.setattr(creds_module, "_fetch_via_onecli", raises_missing)
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "from-host-env-fallback")

    result = fetch_secret("DISCORD_BOT_TOKEN")
    assert result.value == "from-host-env-fallback"
    assert result.source == "host-env"


def test_fetch_secret_raises_when_onecli_missing_and_no_host_env(monkeypatch):
    def raises_not_installed(name):
        raise OneCLINotInstalledError("onecli not on PATH")

    monkeypatch.setattr(creds_module, "_fetch_via_onecli", raises_not_installed)
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)

    with pytest.raises(CredentialUnavailableError, match="OneCLI not installed"):
        fetch_secret("DISCORD_BOT_TOKEN")


def test_fetch_secret_raises_when_onecli_missing_secret_and_no_host_env(monkeypatch):
    def raises_missing(name):
        raise OneCLISecretMissingError(f"OneCLI doesn't have {name}")

    monkeypatch.setattr(creds_module, "_fetch_via_onecli", raises_missing)
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)

    with pytest.raises(CredentialUnavailableError, match="not in OneCLI vault"):
        fetch_secret("DISCORD_BOT_TOKEN")


def test_secret_fetch_result_is_frozen():
    import dataclasses
    r = SecretFetchResult(value="x", source="onecli")
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.value = "tampered"  # type: ignore[misc]


# --- F-B-03: OneCLI timeout is its own exception type, no fallback --------


def test_fetch_via_onecli_raises_timeout_error_on_subprocess_timeout(monkeypatch):
    """Previously the bare TimeoutExpired propagated as an undocumented
    exception. Now it surfaces as OneCLITimeoutError with a helpful
    message about checking vault status."""
    def fake_run(argv, **kwargs):
        raise subprocess.TimeoutExpired(cmd=argv, timeout=kwargs.get("timeout", 30))

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(OneCLITimeoutError, match="timed out"):
        creds_module._fetch_via_onecli("DISCORD_BOT_TOKEN")


def test_fetch_secret_does_not_fall_back_to_host_env_on_timeout(monkeypatch):
    """Timeout means we don't know what OneCLI would have said. Falling
    back to host env could mask a real problem — D-134 "fail loud" applies."""
    def raises_timeout(name):
        raise OneCLITimeoutError("OneCLI timed out after 30s")

    monkeypatch.setattr(creds_module, "_fetch_via_onecli", raises_timeout)
    # Even with host env set, the fetch should still raise — no silent fallback.
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "this-should-not-be-returned")

    with pytest.raises(OneCLITimeoutError):
        fetch_secret("DISCORD_BOT_TOKEN")
