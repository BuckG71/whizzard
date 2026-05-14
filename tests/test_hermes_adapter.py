"""Hermes adapter tests — Stage 8.

Covers build-plan Actions 1 (skeleton), 2 (active_capabilities Protocol),
and 3 (container_env with OneCLI-mediated credential injection).
Subsequent milestones (gateway.lock check, --platforms restriction,
wrap_up via /quit) add their own coverage.
"""

import json
import os
import subprocess
from pathlib import Path

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


# --- preflight / gateway.lock concurrency guard (D-87, Milestone 4) ---


def test_hermes_preflight_returns_ok_when_no_hermes_home_configured():
    # Without hermes_home set, there's no profile to check — skip the lock check.
    result = HermesAdapter().preflight()
    assert result.ok is True
    assert result.reason == ""
    assert result.cleanup_note == ""


def test_hermes_preflight_returns_ok_when_no_lock_file(tmp_path):
    adapter = HermesAdapter(config={"hermes_home": str(tmp_path)})
    result = adapter.preflight()
    assert result.ok is True


def test_hermes_preflight_blocks_when_pid_alive(tmp_path, monkeypatch):
    lock_data = {"pid": 12345, "kind": "hermes-gateway", "argv": []}
    (tmp_path / "gateway.lock").write_text(json.dumps(lock_data))
    monkeypatch.setattr(hermes_module, "_is_pid_alive", lambda pid: True)

    adapter = HermesAdapter(config={"hermes_home": str(tmp_path)})
    result = adapter.preflight()

    assert result.ok is False
    assert "12345" in result.reason
    assert str(tmp_path) in result.reason
    assert "profile create" in result.reason  # remediation hint is present


def test_hermes_preflight_clears_stale_lock_and_proceeds(tmp_path, monkeypatch):
    lock_path = tmp_path / "gateway.lock"
    lock_data = {"pid": 999999, "kind": "hermes-gateway", "argv": []}
    lock_path.write_text(json.dumps(lock_data))
    monkeypatch.setattr(hermes_module, "_is_pid_alive", lambda pid: False)

    adapter = HermesAdapter(config={"hermes_home": str(tmp_path)})
    result = adapter.preflight()

    assert result.ok is True
    assert "999999" in result.cleanup_note
    assert "stale" in result.cleanup_note.lower()
    assert not lock_path.exists()  # cleaned up


def test_hermes_preflight_treats_malformed_lock_as_no_lock(tmp_path):
    (tmp_path / "gateway.lock").write_text("not valid json {{{")
    adapter = HermesAdapter(config={"hermes_home": str(tmp_path)})
    result = adapter.preflight()
    # Malformed → proceed; Hermes will overwrite on its own launch.
    assert result.ok is True


def test_hermes_preflight_treats_lock_without_pid_as_no_lock(tmp_path):
    (tmp_path / "gateway.lock").write_text(json.dumps({"kind": "hermes-gateway"}))
    adapter = HermesAdapter(config={"hermes_home": str(tmp_path)})
    result = adapter.preflight()
    assert result.ok is True


def test_resolve_hermes_home_expands_tilde(monkeypatch):
    monkeypatch.setenv("HOME", "/Users/testuser")
    result = hermes_module._resolve_hermes_home({"hermes_home": "~/.hermes-bot"})
    assert result == Path("/Users/testuser/.hermes-bot")


def test_resolve_hermes_home_returns_none_when_missing():
    assert hermes_module._resolve_hermes_home({}) is None


def test_resolve_hermes_home_returns_none_when_empty_string():
    assert hermes_module._resolve_hermes_home({"hermes_home": ""}) is None


def test_is_pid_alive_returns_false_for_dead_pid(monkeypatch):
    def fake_kill(pid, sig):
        raise ProcessLookupError()
    monkeypatch.setattr(os, "kill", fake_kill)
    assert hermes_module._is_pid_alive(99999999) is False


def test_is_pid_alive_returns_true_for_signalable_pid(monkeypatch):
    monkeypatch.setattr(os, "kill", lambda pid, sig: None)
    assert hermes_module._is_pid_alive(1) is True


def test_is_pid_alive_returns_true_when_permission_denied(monkeypatch):
    def fake_kill(pid, sig):
        raise PermissionError()
    monkeypatch.setattr(os, "kill", fake_kill)
    assert hermes_module._is_pid_alive(1) is True


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
