"""Hermes adapter tests — Stage 8.

Covers build-plan Actions 1 (skeleton), 2 (active_capabilities Protocol),
and 3 (container_env with OneCLI-mediated credential injection).
Subsequent milestones (gateway.lock check, --platforms restriction,
wrap_up via /quit) add their own coverage.
"""

import subprocess

import pytest

from whizzard.adapters import (
    HarnessAdapter,
    HermesAdapter,
    OneCLINotInstalledError,
    OneCLISecretMissingError,
    WrapUpStatus,
    build_adapter,
)
from whizzard.adapters import hermes as hermes_module


def test_build_adapter_returns_hermes_for_agent_type():
    adapter = build_adapter(
        "hermes", {"type": "agent", "start_command": "hermes gateway run"}
    )
    assert isinstance(adapter, HermesAdapter)
    assert adapter.name == "hermes"


def test_hermes_adapter_satisfies_protocol():
    assert isinstance(HermesAdapter(), HarnessAdapter)


def test_hermes_default_start_command_is_gateway_run():
    # D-88: gateway is the default mode for the Hermes adapter.
    assert HermesAdapter().start_command() == ["hermes", "gateway", "run"]


def test_hermes_start_command_can_be_overridden_via_config():
    adapter = HermesAdapter(config={"start_command": "hermes chat"})
    assert adapter.start_command() == ["hermes", "chat"]


def test_hermes_start_command_list_is_passed_through():
    adapter = HermesAdapter(config={"start_command": ["hermes", "chat", "-q", "hi"]})
    assert adapter.start_command() == ["hermes", "chat", "-q", "hi"]


def test_hermes_env_defaults_empty():
    # No platforms declared, no extra env → empty dict.
    assert HermesAdapter().container_env() == {}


def test_hermes_container_env_fetches_platform_credentials(monkeypatch):
    fake_vault = {
        "DISCORD_BOT_TOKEN": "discord-secret-xyz",
        "SLACK_BOT_TOKEN": "slack-secret-abc",
    }
    monkeypatch.setattr(
        hermes_module,
        "_fetch_secret_via_onecli",
        lambda name: fake_vault[name],
    )

    adapter = HermesAdapter(config={"platforms": ["discord", "slack"]})
    env = adapter.container_env()

    assert env == {
        "DISCORD_BOT_TOKEN": "discord-secret-xyz",
        "SLACK_BOT_TOKEN": "slack-secret-abc",
    }


def test_hermes_container_env_passes_through_non_platform_env(monkeypatch):
    # When `platforms` is absent, OneCLI is not invoked at all.
    def fail_if_called(name):
        pytest.fail(f"OneCLI should not be invoked when no platforms declared (got {name!r})")

    monkeypatch.setattr(hermes_module, "_fetch_secret_via_onecli", fail_if_called)

    adapter = HermesAdapter(config={"env": {"FOO": "bar", "BAZ": 1}})
    assert adapter.container_env() == {"FOO": "bar", "BAZ": "1"}


def test_hermes_container_env_combines_platforms_and_passthrough_env(monkeypatch):
    monkeypatch.setattr(
        hermes_module,
        "_fetch_secret_via_onecli",
        lambda name: f"value-of-{name}",
    )

    adapter = HermesAdapter(
        config={
            "platforms": ["discord"],
            "env": {"HERMES_HOME": "/mnt/hermes"},
        }
    )
    env = adapter.container_env()

    assert env == {
        "DISCORD_BOT_TOKEN": "value-of-DISCORD_BOT_TOKEN",
        "HERMES_HOME": "/mnt/hermes",
    }


def test_hermes_container_env_raises_when_onecli_not_installed(monkeypatch):
    def fake_fetch(name):
        raise OneCLINotInstalledError("onecli not on PATH")

    monkeypatch.setattr(hermes_module, "_fetch_secret_via_onecli", fake_fetch)

    adapter = HermesAdapter(config={"platforms": ["discord"]})
    with pytest.raises(OneCLINotInstalledError):
        adapter.container_env()


def test_hermes_container_env_raises_when_secret_missing(monkeypatch):
    def fake_fetch(name):
        raise OneCLISecretMissingError(f"no such secret {name!r}")

    monkeypatch.setattr(hermes_module, "_fetch_secret_via_onecli", fake_fetch)

    adapter = HermesAdapter(config={"platforms": ["discord"]})
    with pytest.raises(OneCLISecretMissingError):
        adapter.container_env()


def test_env_var_for_platform_uppercases_with_suffix():
    # Convention: <platform> → <PLATFORM>_BOT_TOKEN (per hermes_research.md L17).
    assert hermes_module._env_var_for_platform("discord") == "DISCORD_BOT_TOKEN"
    assert hermes_module._env_var_for_platform("slack") == "SLACK_BOT_TOKEN"
    assert hermes_module._env_var_for_platform("telegram") == "TELEGRAM_BOT_TOKEN"


def test_fetch_secret_calls_onecli_with_expected_argv(monkeypatch):
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

    secret = hermes_module._fetch_secret_via_onecli("DISCORD_BOT_TOKEN")

    assert captured["argv"] == ["onecli", "secrets", "get", "DISCORD_BOT_TOKEN"]
    assert captured["kwargs"]["timeout"] == hermes_module._ONECLI_TIMEOUT_SECONDS
    assert captured["kwargs"]["capture_output"] is True
    assert captured["kwargs"]["text"] is True
    assert secret == "the-secret-value"


def test_fetch_secret_raises_onecli_not_installed_on_filenotfound(monkeypatch):
    def fake_run(argv, **kwargs):
        raise FileNotFoundError("[Errno 2] No such file or directory: 'onecli'")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(OneCLINotInstalledError, match="onecli"):
        hermes_module._fetch_secret_via_onecli("DISCORD_BOT_TOKEN")


def test_fetch_secret_raises_secret_missing_on_nonzero_return(monkeypatch):
    class _Result:
        returncode = 1
        stdout = ""
        stderr = "secret not found in vault"

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _Result())

    with pytest.raises(OneCLISecretMissingError, match="DISCORD_BOT_TOKEN"):
        hermes_module._fetch_secret_via_onecli("DISCORD_BOT_TOKEN")


def test_hermes_working_dir_defaults_none():
    assert HermesAdapter().working_dir() is None


def test_hermes_wrap_up_not_yet_implemented():
    # Real wrap_up via `docker exec /quit` lands in build-plan milestone 6.
    # Skeleton raises so end-to-end runs fail loudly rather than silently
    # mishandling shutdown.
    with pytest.raises(NotImplementedError, match="milestone 6"):
        HermesAdapter().wrap_up("container-id", grace_seconds=10)


def test_hermes_health_check_is_none():
    assert HermesAdapter().health_check_command() is None


def test_hermes_active_capabilities_returns_list_of_strings():
    # Skeleton: empty. Action 3 populates from config.yaml + approval mode.
    caps = HermesAdapter().active_capabilities()
    assert isinstance(caps, list)
    assert all(isinstance(c, str) for c in caps)
