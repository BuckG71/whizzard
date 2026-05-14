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
    HermesProfileExistsError,
    HermesProfileNameError,
    HermesProfileSourceMissingError,
    OneCLINotInstalledError,
    OneCLISecretMissingError,
    WrapUpStatus,
    build_adapter,
    create_hermes_profile,
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


# --- Profile creation (D-86, Milestone 5) ---------------------------------


def _seed_default_profile(parent: Path) -> Path:
    """Build a realistic mini Hermes profile at <parent>/.hermes for tests."""
    home = parent / ".hermes"
    home.mkdir()
    (home / "config.yaml").write_text("approvals:\n  mode: manual\n")
    (home / "SOUL.md").write_text("# Soul\nbe helpful\n")
    (home / "auth.json").write_text('{"discord": {"token": "secret"}}')
    (home / "auth.lock").write_text("")
    (home / ".env").write_text("DISCORD_BOT_TOKEN=secret-not-allowed-in-clone\n")
    (home / "state.db").write_bytes(b"\x00" * 16)
    (home / "state.db-shm").write_bytes(b"\x00" * 4)
    (home / "state.db-wal").write_bytes(b"\x00" * 4)
    (home / "gateway.lock").write_text('{"pid": 99}')
    (home / "gateway.pid").write_text('{"pid": 99}')
    (home / "gateway_state.json").write_text('{"running": true}')
    (home / ".DS_Store").write_bytes(b"")
    (home / "memories").mkdir()
    (home / "memories" / "MEMORY.md").write_text("# Memory\n")
    (home / "skills").mkdir()
    (home / "skills" / ".curator_state").write_text("{}")
    (home / "skills" / ".usage.json").write_text("{}")
    (home / "skills" / "example").mkdir()
    (home / "skills" / "example" / "SKILL.md").write_text("# Example\n")
    (home / "sessions").mkdir()
    (home / "sessions" / "old-session.json").write_text("{}")
    (home / "logs").mkdir()
    (home / "logs" / "old.log").write_text("noise\n")
    (home / ".git").mkdir()
    (home / ".git" / "HEAD").write_text("ref: refs/heads/main")
    return home


def test_create_profile_empty_when_no_clone(tmp_path):
    result = create_hermes_profile("scratch", no_clone=True, parent_dir=tmp_path)
    assert result.path == tmp_path / ".hermes-scratch"
    assert result.path.is_dir()
    assert result.source is None
    assert list(result.path.iterdir()) == []  # truly empty


def test_create_profile_bare_clones_from_default_when_present(tmp_path):
    _seed_default_profile(tmp_path)
    result = create_hermes_profile("whizzard-cell", parent_dir=tmp_path)

    assert result.path == tmp_path / ".hermes-whizzard-cell"
    assert result.source == tmp_path / ".hermes"

    # Carried over (configuration / curated content):
    assert (result.path / "config.yaml").read_text().startswith("approvals:")
    assert (result.path / "SOUL.md").exists()
    assert (result.path / "memories" / "MEMORY.md").exists()
    assert (result.path / "skills" / "example" / "SKILL.md").exists()

    # Excluded — security:
    assert not (result.path / "auth.json").exists()
    assert not (result.path / "auth.lock").exists()
    assert not (result.path / ".env").exists()

    # Excluded — per-instance runtime state:
    assert not (result.path / "state.db").exists()
    assert not (result.path / "state.db-shm").exists()
    assert not (result.path / "state.db-wal").exists()
    assert not (result.path / "gateway.lock").exists()
    assert not (result.path / "gateway.pid").exists()
    assert not (result.path / "gateway_state.json").exists()
    assert not (result.path / "sessions").exists()
    assert not (result.path / "logs").exists()
    assert not (result.path / ".git").exists()
    assert not (result.path / ".DS_Store").exists()

    # Excluded — curator state inside skills/:
    assert not (result.path / "skills" / ".curator_state").exists()
    assert not (result.path / "skills" / ".usage.json").exists()


def test_create_profile_bare_degrades_to_empty_when_no_default(tmp_path):
    # No ~/.hermes seeded → bare command falls through to empty.
    result = create_hermes_profile("scratch", parent_dir=tmp_path)
    assert result.path.is_dir()
    assert result.source is None
    assert list(result.path.iterdir()) == []


def test_create_profile_explicit_clone_from_named_source(tmp_path):
    # Seed a non-default profile to clone from.
    other = tmp_path / ".hermes-base"
    other.mkdir()
    (other / "config.yaml").write_text("model: claude-sonnet-4-6\n")
    (other / "auth.json").write_text('{"token": "secret"}')

    result = create_hermes_profile("derived", clone_from="base", parent_dir=tmp_path)

    assert result.source == other
    assert (result.path / "config.yaml").exists()
    assert not (result.path / "auth.json").exists()


def test_create_profile_explicit_clone_from_missing_source_raises(tmp_path):
    with pytest.raises(HermesProfileSourceMissingError, match="does-not-exist"):
        create_hermes_profile(
            "derived", clone_from="does-not-exist", parent_dir=tmp_path
        )


def test_create_profile_refuses_existing_target(tmp_path):
    (tmp_path / ".hermes-already-there").mkdir()
    with pytest.raises(HermesProfileExistsError, match="already exists"):
        create_hermes_profile("already-there", no_clone=True, parent_dir=tmp_path)


def test_create_profile_refuses_default_name(tmp_path):
    with pytest.raises(HermesProfileNameError, match="reserved"):
        create_hermes_profile("default", parent_dir=tmp_path)


def test_create_profile_refuses_slash_in_name(tmp_path):
    with pytest.raises(HermesProfileNameError, match="invalid profile name"):
        create_hermes_profile("foo/bar", parent_dir=tmp_path)


def test_create_profile_refuses_leading_dot(tmp_path):
    with pytest.raises(HermesProfileNameError, match="invalid profile name"):
        create_hermes_profile(".hidden", parent_dir=tmp_path)


def test_create_profile_refuses_empty_name(tmp_path):
    with pytest.raises(HermesProfileNameError, match="invalid profile name"):
        create_hermes_profile("", parent_dir=tmp_path)


def test_hermes_profile_path_maps_default_to_hermes_dir(tmp_path):
    assert hermes_module._hermes_profile_path("default", tmp_path) == tmp_path / ".hermes"


def test_hermes_profile_path_maps_named_to_suffixed_dir(tmp_path):
    assert (
        hermes_module._hermes_profile_path("whizzard-cell", tmp_path)
        == tmp_path / ".hermes-whizzard-cell"
    )


def test_hermes_working_dir_defaults_none():
    assert HermesAdapter().working_dir() is None


def test_hermes_wrap_up_success_on_clean_exit(monkeypatch):
    """docker stop returns 0; container exit code is non-137 → SUCCESS."""
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        if argv[:2] == ["docker", "stop"]:
            class _R:
                returncode = 0
                stdout = ""
                stderr = ""
            return _R()
        if argv[:2] == ["docker", "inspect"]:
            class _R:
                returncode = 0
                stdout = "0\n"
                stderr = ""
            return _R()
        pytest.fail(f"unexpected argv: {argv}")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = HermesAdapter().wrap_up("container-id-abc", grace_seconds=15)

    assert result.status == WrapUpStatus.SUCCESS
    assert calls[0] == ["docker", "stop", "--time", "15", "container-id-abc"]
    assert calls[1] == [
        "docker", "inspect",
        "--format", "{{.State.ExitCode}}",
        "container-id-abc",
    ]


def test_hermes_wrap_up_timeout_on_sigkill_exit_code(monkeypatch):
    """Exit code 137 means docker had to SIGKILL after grace → TIMEOUT."""
    def fake_run(argv, **kwargs):
        if argv[:2] == ["docker", "stop"]:
            class _R:
                returncode = 0
                stdout = ""
                stderr = ""
            return _R()
        if argv[:2] == ["docker", "inspect"]:
            class _R:
                returncode = 0
                stdout = "137\n"
                stderr = ""
            return _R()
        pytest.fail(f"unexpected argv: {argv}")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = HermesAdapter().wrap_up("c", grace_seconds=10)
    assert result.status == WrapUpStatus.TIMEOUT
    assert "SIGKILL" in result.detail
    assert "10s grace" in result.detail


def test_hermes_wrap_up_error_when_docker_missing(monkeypatch):
    def fake_run(argv, **kwargs):
        raise FileNotFoundError("docker")
    monkeypatch.setattr(subprocess, "run", fake_run)

    result = HermesAdapter().wrap_up("c", grace_seconds=5)
    assert result.status == WrapUpStatus.ERROR
    assert "docker" in result.detail.lower()


def test_hermes_wrap_up_timeout_on_subprocess_hang(monkeypatch):
    def fake_run(argv, **kwargs):
        if argv[:2] == ["docker", "stop"]:
            raise subprocess.TimeoutExpired(cmd=argv, timeout=kwargs.get("timeout", 0))
        pytest.fail(f"unexpected argv: {argv}")
    monkeypatch.setattr(subprocess, "run", fake_run)

    result = HermesAdapter().wrap_up("c", grace_seconds=5)
    assert result.status == WrapUpStatus.TIMEOUT
    assert "docker stop" in result.detail.lower()


def test_hermes_wrap_up_error_on_docker_stop_nonzero(monkeypatch):
    def fake_run(argv, **kwargs):
        class _R:
            returncode = 1
            stdout = ""
            stderr = "Error response from daemon: No such container: c"
        return _R()
    monkeypatch.setattr(subprocess, "run", fake_run)

    result = HermesAdapter().wrap_up("c", grace_seconds=5)
    assert result.status == WrapUpStatus.ERROR
    assert "exit 1" in result.detail
    assert "No such container" in result.detail


def test_hermes_wrap_up_success_when_inspect_probe_fails(monkeypatch):
    """Inspect failure shouldn't downgrade a successful docker stop."""
    def fake_run(argv, **kwargs):
        if argv[:2] == ["docker", "stop"]:
            class _R:
                returncode = 0
                stdout = ""
                stderr = ""
            return _R()
        if argv[:2] == ["docker", "inspect"]:
            class _R:
                returncode = 1
                stdout = ""
                stderr = "container not found"
            return _R()
        pytest.fail(f"unexpected argv: {argv}")
    monkeypatch.setattr(subprocess, "run", fake_run)

    result = HermesAdapter().wrap_up("c", grace_seconds=5)
    assert result.status == WrapUpStatus.SUCCESS
    assert "probe" in result.detail.lower()


def test_hermes_wrap_up_success_when_inspect_output_unparseable(monkeypatch):
    def fake_run(argv, **kwargs):
        if argv[:2] == ["docker", "stop"]:
            class _R:
                returncode = 0
                stdout = ""
                stderr = ""
            return _R()
        if argv[:2] == ["docker", "inspect"]:
            class _R:
                returncode = 0
                stdout = "not-an-int\n"
                stderr = ""
            return _R()
        pytest.fail(f"unexpected argv: {argv}")
    monkeypatch.setattr(subprocess, "run", fake_run)

    result = HermesAdapter().wrap_up("c", grace_seconds=5)
    assert result.status == WrapUpStatus.SUCCESS
    assert "unparseable" in result.detail.lower()


def test_hermes_health_check_is_none():
    assert HermesAdapter().health_check_command() is None


def test_hermes_active_capabilities_returns_list_of_strings():
    # Skeleton: empty. Action 3 populates from config.yaml + approval mode.
    caps = HermesAdapter().active_capabilities()
    assert isinstance(caps, list)
    assert all(isinstance(c, str) for c in caps)
