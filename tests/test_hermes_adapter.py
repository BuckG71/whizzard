"""Hermes adapter tests — Stages 8 + 12.

Covers Stage 8 build-plan Actions 1–6 (skeleton, Protocol extension,
container_env, preflight, profile create, wrap_up) plus the Stage 12
generalization that moved OneCLI plumbing into `_credentials.py`. The
adapter now consumes `fetch_secret` from the shared utility; tests for
the utility itself live in `test_credentials_utility.py`.
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

from whizzard.adapters import (
    CredentialUnavailableError,
    HarnessAdapter,
    HermesAdapter,
    HermesAuthJsonPresentError,
    HermesProfileExistsError,
    HermesProfileNameError,
    HermesProfileSourceMissingError,
    SecretFetchResult,
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


def test_hermes_default_start_command_is_interactive():
    # D-181 (amends D-88): bare `hermes` (interactive terminal chat) is the
    # default cell invocation, not gateway mode. Gateway is opted into via
    # the harness config's start_command, never a whiz flag.
    assert HermesAdapter().start_command() == ["hermes"]


def test_hermes_start_command_can_be_overridden_via_config():
    adapter = HermesAdapter(config={"start_command": "hermes chat"})
    assert adapter.start_command() == ["hermes", "chat"]


def test_hermes_start_command_list_is_passed_through():
    adapter = HermesAdapter(config={"start_command": ["hermes", "chat", "-q", "hi"]})
    assert adapter.start_command() == ["hermes", "chat", "-q", "hi"]


def test_hermes_env_defaults_empty():
    # No platforms declared, no extra env → empty dict.
    assert HermesAdapter().container_env() == {}


def test_mediated_container_env_injects_placeholder_not_the_real_key():
    """bar C / D-184: a mediated launch hands the cell the broker URL + a
    worthless placeholder; the real key is never injected here (it lives only
    on the broker sidecar)."""
    from whizzard.adapters.hermes import MEDIATION_PLACEHOLDER, MediationContext

    adapter = HermesAdapter()
    adapter.mediation = MediationContext(
        base_url="http://whiz-broker-abc:8080",
        base_url_env="ANTHROPIC_BASE_URL",
        secret_name="ANTHROPIC_API_KEY",
    )
    env = adapter.container_env()
    assert env["ANTHROPIC_BASE_URL"] == "http://whiz-broker-abc:8080"
    assert env["ANTHROPIC_API_KEY"] == MEDIATION_PLACEHOLDER
    # the placeholder is not a real credential → it must not be in the scrub set
    assert "ANTHROPIC_API_KEY" not in adapter.credential_env_keys()


def test_onecli_container_env_strips_all_secrets_and_routes_via_gateway(monkeypatch):
    """D-187 onecli mode: every fetched secret is stripped from the cell env
    (OneCLI injects them host-side); the cell gets only the proxy + CA trust +
    a model placeholder."""
    import types

    from whizzard.adapters import hermes as hz

    monkeypatch.setattr(
        hz, "fetch_secret",
        lambda name: types.SimpleNamespace(value="real-" + name, source="host-env"),
    )
    adapter = hz.HermesAdapter(config={"secrets": ["DISCORD_BOT_TOKEN"]})
    adapter.onecli = hz.OneCLIContext(
        proxy_url="http://x:tok@onecli:10255", ca_host_path="/host/ca.pem"
    )
    env = adapter.container_env()

    # egress routed through the gateway
    assert env["HTTPS_PROXY"] == "http://x:tok@onecli:10255"
    assert env["HTTP_PROXY"] == "http://x:tok@onecli:10255"
    # CA trust points at the in-cell mount
    assert env["NODE_EXTRA_CA_CERTS"] == hz._IN_CELL_ONECLI_CA
    assert env["REQUESTS_CA_BUNDLE"] == hz._IN_CELL_ONECLI_CA
    # model client initializes with a placeholder (gateway injects the real one)
    assert env["ANTHROPIC_API_KEY"] == hz.MEDIATION_PLACEHOLDER
    # the real fetched secret is NOT in the cell env, and the scrub set is clear
    assert "DISCORD_BOT_TOKEN" not in env
    # the fetched service secret is gone from the scrub set, but the proxy vars
    # carry the gateway token and MUST be scrubbed from the audit-log argv
    assert "DISCORD_BOT_TOKEN" not in adapter.credential_env_keys()
    assert "HTTPS_PROXY" in adapter.credential_env_keys()


def test_onecli_container_mounts_the_ca_cert(monkeypatch):
    from whizzard.adapters import hermes as hz

    adapter = hz.HermesAdapter()
    adapter.onecli = hz.OneCLIContext(
        proxy_url="http://x:tok@onecli:10255", ca_host_path="/host/ca.pem"
    )
    mounts = adapter.container_mounts()
    ca = [m for m in mounts if m.container_path == hz._IN_CELL_ONECLI_CA]
    assert len(ca) == 1
    assert str(ca[0].host_path) == "/host/ca.pem"
    assert ca[0].mode == "ro"


def test_hybrid_routes_model_to_broker_and_rest_to_onecli(monkeypatch):
    """D-187 hybrid: the model call goes to the bar-C broker (NO_PROXY exempts
    it from the OneCLI proxy); every other credential is injected by OneCLI;
    the cell holds nothing real."""
    import types

    from whizzard.adapters import hermes as hz

    monkeypatch.setattr(
        hz, "fetch_secret",
        lambda name: types.SimpleNamespace(value="real-" + name, source="host-env"),
    )
    adapter = hz.HermesAdapter(config={"secrets": ["DISCORD_BOT_TOKEN"]})
    adapter.mediation = hz.MediationContext(
        base_url="http://whiz-broker-abc:8080",
        base_url_env="ANTHROPIC_BASE_URL",
        secret_name="ANTHROPIC_API_KEY",
    )
    adapter.onecli = hz.OneCLIContext(
        proxy_url="http://x:tok@onecli:10255", ca_host_path="/host/ca.pem"
    )
    env = adapter.container_env()

    # model → bar-C broker; everything else → OneCLI proxy
    assert env["ANTHROPIC_BASE_URL"] == "http://whiz-broker-abc:8080"
    assert env["HTTPS_PROXY"] == "http://x:tok@onecli:10255"
    # NO_PROXY exempts the broker host so the model call bypasses OneCLI
    assert env["NO_PROXY"] == "whiz-broker-abc"
    assert env["no_proxy"] == "whiz-broker-abc"
    # CA trust for the OneCLI MITM; placeholder model key; nothing real in cell
    assert env["NODE_EXTRA_CA_CERTS"] == hz._IN_CELL_ONECLI_CA
    assert env["ANTHROPIC_API_KEY"] == hz.MEDIATION_PLACEHOLDER
    assert "DISCORD_BOT_TOKEN" not in env
    # the fetched service secret is gone from the scrub set, but the proxy vars
    # carry the gateway token and MUST be scrubbed from the audit-log argv
    assert "DISCORD_BOT_TOKEN" not in adapter.credential_env_keys()
    assert "HTTPS_PROXY" in adapter.credential_env_keys()


def test_hermes_container_env_fetches_platform_credentials(monkeypatch):
    fake_vault = {
        "DISCORD_BOT_TOKEN": "discord-secret-xyz",
        "SLACK_BOT_TOKEN": "slack-secret-abc",
    }
    monkeypatch.setattr(
        hermes_module,
        "fetch_secret",
        lambda name: SecretFetchResult(value=fake_vault[name], source="onecli"),
    )

    adapter = HermesAdapter(config={"platforms": ["discord", "slack"]})
    env = adapter.container_env()

    assert env == {
        "DISCORD_BOT_TOKEN": "discord-secret-xyz",
        "SLACK_BOT_TOKEN": "slack-secret-abc",
    }


def test_hermes_container_env_records_credential_source(monkeypatch):
    def fake_fetch(name):
        # discord via OneCLI, slack via host-env (mixed sources)
        if name == "DISCORD_BOT_TOKEN":
            return SecretFetchResult(value="d", source="onecli")
        return SecretFetchResult(value="s", source="host-env")

    monkeypatch.setattr(hermes_module, "fetch_secret", fake_fetch)

    adapter = HermesAdapter(config={"platforms": ["discord", "slack"]})
    adapter.container_env()

    # S20.7 / D-134: the dict is keyed on the env-var NAME (the same
    # string that lands in `-e KEY=VALUE` argv), not the platform name,
    # so credential_env_keys() advertises a set the audit-log scrubber
    # can actually match against.
    assert adapter._credential_sources == {
        "DISCORD_BOT_TOKEN": "onecli",
        "SLACK_BOT_TOKEN": "host-env",
    }


def test_hermes_container_env_passes_through_non_platform_env(monkeypatch):
    # When `platforms` is absent, fetch_secret is not invoked at all.
    def fail_if_called(name):
        pytest.fail(f"fetch_secret should not be invoked when no platforms declared (got {name!r})")

    monkeypatch.setattr(hermes_module, "fetch_secret", fail_if_called)

    adapter = HermesAdapter(config={"env": {"FOO": "bar", "BAZ": 1}})
    assert adapter.container_env() == {"FOO": "bar", "BAZ": "1"}


def test_hermes_container_env_combines_platforms_and_passthrough_env(monkeypatch):
    monkeypatch.setattr(
        hermes_module,
        "fetch_secret",
        lambda name: SecretFetchResult(value=f"value-of-{name}", source="onecli"),
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


def test_hermes_container_env_propagates_credential_unavailable(monkeypatch):
    # When neither OneCLI nor host env has the credential, fetch_secret
    # raises CredentialUnavailableError; the adapter doesn't swallow it.
    def fake_fetch(name):
        raise CredentialUnavailableError(f"no source has {name}")

    monkeypatch.setattr(hermes_module, "fetch_secret", fake_fetch)

    adapter = HermesAdapter(config={"platforms": ["discord"]})
    with pytest.raises(CredentialUnavailableError):
        adapter.container_env()


def test_env_var_for_platform_uppercases_with_suffix():
    # Convention: <platform> → <PLATFORM>_BOT_TOKEN (per hermes_research.md L17).
    assert hermes_module._env_var_for_platform("discord") == "DISCORD_BOT_TOKEN"
    assert hermes_module._env_var_for_platform("slack") == "SLACK_BOT_TOKEN"
    assert hermes_module._env_var_for_platform("telegram") == "TELEGRAM_BOT_TOKEN"


# --- preflight / gateway.lock concurrency guard (D-87, Milestone 4) ---


def test_hermes_preflight_refuses_when_no_hermes_home_and_not_ephemeral():
    # F-C-04: agent-type harness without hermes_home is fail-loud by default.
    result = HermesAdapter().preflight()
    assert result.ok is False
    assert "hermes_home" in result.reason
    assert "--allow-ephemeral" in result.reason
    assert "profile create" in result.reason  # remediation hint


def test_hermes_preflight_returns_ok_when_no_hermes_home_with_allow_ephemeral():
    # F-C-04: --allow-ephemeral is the documented escape hatch.
    result = HermesAdapter(allow_ephemeral=True).preflight()
    assert result.ok is True
    assert result.reason == ""
    assert result.cleanup_note == ""


def _gateway_adapter(tmp_path):
    """Gateway-mode Hermes adapter. The gateway.lock pre-check only runs in
    gateway mode (D-87/D-181), so the lock tests opt into it explicitly."""
    return HermesAdapter(
        config={"hermes_home": str(tmp_path), "start_command": "hermes gateway run"}
    )


def test_hermes_preflight_returns_ok_when_no_lock_file(tmp_path):
    result = _gateway_adapter(tmp_path).preflight()
    assert result.ok is True


def test_hermes_preflight_blocks_when_pid_alive(tmp_path, monkeypatch):
    lock_data = {"pid": 12345, "kind": "hermes-gateway", "argv": []}
    (tmp_path / "gateway.lock").write_text(json.dumps(lock_data))
    monkeypatch.setattr(hermes_module, "_is_pid_alive", lambda pid: True)

    result = _gateway_adapter(tmp_path).preflight()

    assert result.ok is False
    assert "12345" in result.reason
    assert str(tmp_path) in result.reason
    assert "profile create" in result.reason  # remediation hint is present


def test_hermes_preflight_clears_stale_lock_and_proceeds(tmp_path, monkeypatch):
    lock_path = tmp_path / "gateway.lock"
    lock_data = {"pid": 999999, "kind": "hermes-gateway", "argv": []}
    lock_path.write_text(json.dumps(lock_data))
    monkeypatch.setattr(hermes_module, "_is_pid_alive", lambda pid: False)

    result = _gateway_adapter(tmp_path).preflight()

    assert result.ok is True
    assert "999999" in result.cleanup_note
    assert "stale" in result.cleanup_note.lower()
    assert not lock_path.exists()  # cleaned up


def test_hermes_preflight_treats_malformed_lock_as_no_lock(tmp_path):
    (tmp_path / "gateway.lock").write_text("not valid json {{{")
    result = _gateway_adapter(tmp_path).preflight()
    # Malformed → proceed; Hermes will overwrite on its own launch.
    assert result.ok is True


def test_hermes_preflight_treats_lock_without_pid_as_no_lock(tmp_path):
    (tmp_path / "gateway.lock").write_text(json.dumps({"kind": "hermes-gateway"}))
    result = _gateway_adapter(tmp_path).preflight()
    assert result.ok is True


def test_hermes_preflight_interactive_default_ignores_gateway_lock(tmp_path, monkeypatch):
    """D-181/D-87: the default (interactive) start_command must NOT pre-check
    the gateway.lock — a live lock left by a gateway must not block an
    interactive `whiz r hermes`."""
    (tmp_path / "gateway.lock").write_text(
        json.dumps({"pid": 12345, "kind": "hermes-gateway", "argv": []})
    )
    monkeypatch.setattr(hermes_module, "_is_pid_alive", lambda pid: True)

    # Default start_command is interactive `hermes` (no override).
    result = HermesAdapter(config={"hermes_home": str(tmp_path)}).preflight()

    assert result.ok is True  # not blocked despite a live gateway lock
    assert (tmp_path / "gateway.lock").exists()  # left untouched


@pytest.mark.skipif(
    os.name == "nt",
    reason="POSIX ~ expansion via $HOME; on Windows expanduser uses "
    "%USERPROFILE%, so setenv('HOME') doesn't drive it",
)
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


@pytest.mark.skipif(
    os.name == "nt",
    reason="exercises the POSIX os.kill(pid, 0) branch; Windows uses the "
    "ctypes path (validated by test_is_pid_alive_posix_unaffected, which "
    "runs the live probe on the Windows runner)",
)
def test_is_pid_alive_returns_true_for_signalable_pid(monkeypatch):
    monkeypatch.setattr(os, "kill", lambda pid, sig: None)
    assert hermes_module._is_pid_alive(1) is True


@pytest.mark.skipif(
    os.name == "nt",
    reason="POSIX PermissionError branch; Windows has no equivalent in the "
    "ctypes path",
)
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
    caps = HermesAdapter().active_capabilities()
    assert isinstance(caps, list)
    assert all(isinstance(c, str) for c in caps)


def test_hermes_active_capabilities_surfaces_declared_platforms(monkeypatch):
    # F-C-07: active_capabilities now eagerly populates credential sources,
    # so the test must mock fetch_secret (otherwise it would shell out to
    # a real OneCLI install during the test).
    monkeypatch.setattr(
        hermes_module,
        "fetch_secret",
        lambda name: SecretFetchResult(value="x", source="onecli"),
    )
    adapter = HermesAdapter(config={"platforms": ["discord", "slack"]})
    caps = adapter.active_capabilities()
    assert any("discord" in c and "slack" in c for c in caps)


def test_hermes_active_capabilities_warns_when_host_env_fallback_used(monkeypatch):
    # Mixed sources: discord via OneCLI, slack via host-env → warning lists slack.
    def fake_fetch(name):
        if name == "DISCORD_BOT_TOKEN":
            return SecretFetchResult(value="d", source="onecli")
        return SecretFetchResult(value="s", source="host-env")

    monkeypatch.setattr(hermes_module, "fetch_secret", fake_fetch)

    adapter = HermesAdapter(config={"platforms": ["discord", "slack"]})
    adapter.container_env()  # populates _credential_sources
    caps = adapter.active_capabilities()

    # S20.7: post-fix, the warning surfaces env-var NAMES rather than
    # platform names. More specific UX — the user can grep their env
    # or OneCLI store for the exact var listed.
    assert any("WARNING" in c and "SLACK_BOT_TOKEN" in c for c in caps)
    # discord came from OneCLI — its env var should NOT appear.
    assert not any("WARNING" in c and "DISCORD_BOT_TOKEN" in c for c in caps)


def test_hermes_active_capabilities_no_warning_when_all_onecli(monkeypatch):
    monkeypatch.setattr(
        hermes_module,
        "fetch_secret",
        lambda name: SecretFetchResult(value="x", source="onecli"),
    )

    adapter = HermesAdapter(config={"platforms": ["discord"]})
    adapter.container_env()
    caps = adapter.active_capabilities()

    assert not any("WARNING" in c for c in caps)


def test_hermes_active_capabilities_mentions_mcp_availability():
    caps = HermesAdapter().active_capabilities()
    assert any("MCP" in c for c in caps)


def test_hermes_active_capabilities_mentions_request_tools():
    # Stage 14: the request-side tools surface in the pre-launch banner.
    caps = HermesAdapter().active_capabilities()
    assert any("whiz_request_mount" in c for c in caps)


def test_hermes_mcp_env_returns_in_cell_paths_and_session_id():
    from whizzard.mcp_server import (
        ENV_AUDIT_LOG_PATH,
        ENV_EVENT_LOG_PATH,
        ENV_REQUEST_DIR,
        ENV_SESSION_ID,
        ENV_SNAPSHOT_PATH,
    )

    env = HermesAdapter().mcp_env("session-abc-123")

    # Session id must be passed through.
    assert env[ENV_SESSION_ID] == "session-abc-123"
    # In-cell paths use the conventional /run/whiz/ location.
    assert env[ENV_SNAPSHOT_PATH] == "/run/whiz/snapshot.json"
    assert env[ENV_AUDIT_LOG_PATH] == "/run/whiz/audit.jsonl"
    assert env[ENV_EVENT_LOG_PATH] == "/run/whiz/events.jsonl"
    # Stage 14: the request channel is a dir inside the /run/whiz mount.
    assert env[ENV_REQUEST_DIR] == "/run/whiz/requests"
    # Exactly these five keys; no leakage.
    assert set(env.keys()) == {
        ENV_SNAPSHOT_PATH, ENV_AUDIT_LOG_PATH, ENV_EVENT_LOG_PATH,
        ENV_REQUEST_DIR, ENV_SESSION_ID,
    }


# --- Stage 8 M6: container_mounts() and HERMES_HOME env ---


def test_hermes_container_mounts_empty_when_hermes_home_unset():
    # No hermes_home → no harness mount; the cell would fall back to its
    # ephemeral tmpfs home, which is a misconfiguration the user owns.
    assert HermesAdapter().container_mounts() == []


def test_hermes_container_mounts_includes_hermes_home(tmp_path):
    host_hermes_home = tmp_path / "hermes-profile"
    host_hermes_home.mkdir()
    adapter = HermesAdapter(config={"hermes_home": str(host_hermes_home)})

    mounts = adapter.container_mounts()

    assert len(mounts) == 1
    cm = mounts[0]
    assert cm.host_path == host_hermes_home
    assert cm.container_path == "/home/whizzard/.hermes"
    assert cm.mode == "rw"
    assert cm.uid_parity is True  # D-56


def test_hermes_container_mounts_auto_creates_missing_host_dir(tmp_path):
    # Bundled `hermes-cell` harness ships with `~/.hermes-whizzard-cell`;
    # on first launch the dir won't exist. Adapter creates it rather than
    # requiring a separate `init` step.
    target = tmp_path / "fresh-hermes-cell"
    assert not target.exists()

    HermesAdapter(config={"hermes_home": str(target)}).container_mounts()

    assert target.is_dir()


def test_hermes_container_env_sets_hermes_home_when_configured(tmp_path):
    host_hermes_home = tmp_path / ".hermes"
    host_hermes_home.mkdir()
    adapter = HermesAdapter(config={"hermes_home": str(host_hermes_home)})

    env = adapter.container_env()

    assert env["HERMES_HOME"] == "/home/whizzard/.hermes"


def test_hermes_container_env_omits_hermes_home_when_unset():
    # No hermes_home in config → HERMES_HOME is not injected. Hermes inside
    # the cell would fall back to its own default; the missing env is the
    # visible signal of misconfiguration.
    env = HermesAdapter().container_env()
    assert "HERMES_HOME" not in env


# --- D-162: secrets-block credential injection ---


def test_hermes_secrets_inject_via_fetch_secret(monkeypatch):
    # D-162: each entry in `secrets:` is an env-var name; the adapter fetches
    # its value via the shared utility (OneCLI per D-134; host-env fallback)
    # and injects into the cell's environment.
    captured: list[str] = []

    def fake_fetch(name: str):
        captured.append(name)
        return SecretFetchResult(value=f"value-of-{name}", source="host-env")

    monkeypatch.setattr(hermes_module, "fetch_secret", fake_fetch)

    adapter = HermesAdapter(config={
        "secrets": ["ANTHROPIC_API_KEY", "OPENROUTER_API_KEY"],
    })
    env = adapter.container_env()

    assert captured == ["ANTHROPIC_API_KEY", "OPENROUTER_API_KEY"]
    assert env["ANTHROPIC_API_KEY"] == "value-of-ANTHROPIC_API_KEY"
    assert env["OPENROUTER_API_KEY"] == "value-of-OPENROUTER_API_KEY"


def test_hermes_secrets_source_surfaces_in_active_capabilities(monkeypatch):
    # When a secret comes from host-env fallback (OneCLI unavailable), the
    # WARNING line in active_capabilities names it. Same surface as platforms.
    def fake_fetch(name: str):
        return SecretFetchResult(value="v", source="host-env")

    monkeypatch.setattr(hermes_module, "fetch_secret", fake_fetch)

    adapter = HermesAdapter(config={"secrets": ["ANTHROPIC_API_KEY"]})
    adapter.container_env()  # populates _credential_sources
    caps = adapter.active_capabilities()

    warning = next((c for c in caps if c.startswith("WARNING:")), None)
    assert warning is not None
    assert "ANTHROPIC_API_KEY" in warning
    assert "host env" in warning


def test_hermes_secrets_and_platforms_coexist(monkeypatch):
    # Both `platforms` (D-89) and `secrets` (D-162) inject in one call.
    monkeypatch.setattr(
        hermes_module, "fetch_secret",
        lambda n: SecretFetchResult(value=f"v-{n}", source="onecli"),
    )

    adapter = HermesAdapter(config={
        "platforms": ["discord"],
        "secrets": ["ANTHROPIC_API_KEY"],
    })
    env = adapter.container_env()

    assert env["DISCORD_BOT_TOKEN"] == "v-DISCORD_BOT_TOKEN"
    assert env["ANTHROPIC_API_KEY"] == "v-ANTHROPIC_API_KEY"


def test_hermes_no_secrets_when_field_omitted(monkeypatch):
    # Absent `secrets` field → no extra fetch_secret calls beyond platforms.
    calls: list[str] = []
    monkeypatch.setattr(
        hermes_module, "fetch_secret",
        lambda n: (calls.append(n), SecretFetchResult(value="v", source="host-env"))[1],
    )

    HermesAdapter().container_env()
    assert calls == []  # no platforms, no secrets → no fetches


# --- F-C-01: mount-time auth.json check (D-80 enforcement) ----------------


def test_preflight_refuses_when_auth_json_present_at_root(tmp_path):
    """Path (a) — user pointed hermes_home at a profile containing auth.json
    (e.g. the real ~/.hermes, or after a manual copy)."""
    (tmp_path / "auth.json").write_text('{"token": "leak"}')
    adapter = HermesAdapter(config={"hermes_home": str(tmp_path)})
    result = adapter.preflight()
    assert result.ok is False
    assert "auth.json" in result.reason
    assert "D-80" in result.reason


def test_preflight_refuses_when_auth_lock_present(tmp_path):
    """Path (b/c) — auth.lock alone (vault unlocked but token cleared) also
    blocks the mount. The lock file's presence is a strong signal that
    auth.json was recently here and may reappear."""
    (tmp_path / "auth.lock").write_text("")
    adapter = HermesAdapter(config={"hermes_home": str(tmp_path)})
    result = adapter.preflight()
    assert result.ok is False
    assert "auth.lock" in result.reason


def test_preflight_refuses_when_auth_json_nested_in_subdir(tmp_path):
    """Hermes nests profile data (default/, numeric subdirs, etc.); the
    auth.json check walks at any depth."""
    sub = tmp_path / "default"
    sub.mkdir()
    (sub / "auth.json").write_text('{"token": "leak"}')
    adapter = HermesAdapter(config={"hermes_home": str(tmp_path)})
    result = adapter.preflight()
    assert result.ok is False
    assert "auth.json" in result.reason


def test_preflight_refuses_when_auth_json_case_variant(tmp_path):
    """macOS APFS is case-insensitive by default; the check must too."""
    (tmp_path / "Auth.json").write_text('{"token": "leak"}')
    adapter = HermesAdapter(config={"hermes_home": str(tmp_path)})
    result = adapter.preflight()
    assert result.ok is False


def test_container_mounts_also_refuses_at_mount_time(tmp_path):
    """Defense in depth: even if a caller skips preflight, the mount-time
    walk still raises. F-C-01 was specifically about closing this gap."""
    (tmp_path / "auth.json").write_text('{"token": "leak"}')
    adapter = HermesAdapter(config={"hermes_home": str(tmp_path)})
    with pytest.raises(HermesAuthJsonPresentError, match="D-80"):
        adapter.container_mounts()


def test_preflight_ok_when_profile_has_no_auth_json(tmp_path):
    """The happy path — a profile created via the standard flow has no
    auth.json (cloned with the exclusion filter) and preflight proceeds."""
    (tmp_path / "config.yaml").write_text("approvals:\n  mode: manual\n")
    (tmp_path / "memories").mkdir()
    adapter = HermesAdapter(config={"hermes_home": str(tmp_path)})
    result = adapter.preflight()
    assert result.ok is True


# --- F-A5 (catch-up review pass 2): D-80 symlink-bypass closures ----------


def test_preflight_refuses_symlink_to_directory_in_profile(tmp_path):
    """A symlink to a directory bypassed the original rglob-based check
    because rglob doesn't descend into directory symlinks. If the
    symlinked directory contained auth.json, the docker bind mount would
    follow it at runtime and expose the credentials."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "auth.json").write_text('{"token": "leaked"}')
    profile = tmp_path / "profile"
    profile.mkdir()
    (profile / "credentials_dir").symlink_to(outside)

    adapter = HermesAdapter(config={"hermes_home": str(profile)})
    result = adapter.preflight()
    assert result.ok is False
    assert "symlink" in result.reason.lower()


def test_preflight_refuses_symlink_to_file_in_profile(tmp_path):
    """A symlink whose own name doesn't match auth.json/lock but whose
    target IS auth.json (or any sensitive file) bypassed the original
    check because `entry.name` is the symlink's name, not the target's."""
    outside_secret = tmp_path / "auth.json"
    outside_secret.write_text('{"token": "leaked-via-symlink"}')
    profile = tmp_path / "profile"
    profile.mkdir()
    (profile / "innocent-looking-name").symlink_to(outside_secret)

    adapter = HermesAdapter(config={"hermes_home": str(profile)})
    result = adapter.preflight()
    assert result.ok is False
    assert "symlink" in result.reason.lower()


# --- F-C-02: case-insensitive clone exclusion -----------------------------


def test_clone_exclusion_matches_uppercase_variants(tmp_path):
    """A source-profile file named Auth.json (which would slip through an
    exact-match check on case-insensitive APFS) is still excluded."""
    source = tmp_path / ".hermes"
    source.mkdir()
    (source / "Auth.json").write_text('{"token": "leak"}')
    (source / "AUTH.JSON").write_text('{"token": "also-leak"}')
    (source / "config.yaml").write_text("approvals:\n")

    result = create_hermes_profile("test-case", parent_dir=tmp_path)

    assert not (result.path / "Auth.json").exists()
    assert not (result.path / "AUTH.JSON").exists()
    assert (result.path / "config.yaml").exists()


# --- F-C-03: symlinks preserved, not dereferenced -------------------------


@pytest.mark.skipif(
    os.name == "nt",
    reason="Windows symlink creation needs Developer Mode/admin and "
    "readlink returns the \\\\?\\ extended-length prefix; symlink "
    "preservation is validated on POSIX",
)
def test_clone_preserves_symlinks_instead_of_copying_target_content(tmp_path):
    """A symlink in the source profile is preserved as a symlink in the
    destination. The symlink's target is host-side and won't resolve
    inside the cell — surfaces as a visible failure, not silent
    credential exfiltration."""
    # Real credential file outside the profile dir
    real_secret = tmp_path / "outside-secret.txt"
    real_secret.write_text("the-real-secret")

    source = tmp_path / ".hermes"
    source.mkdir()
    (source / "config.yaml").write_text("ok\n")
    # Symlink under a non-excluded name pointing at the secret
    (source / "innocent_settings.json").symlink_to(real_secret)

    result = create_hermes_profile("test-symlink", parent_dir=tmp_path)

    copied = result.path / "innocent_settings.json"
    # Symlink preserved (not dereferenced + content-copied)
    assert copied.is_symlink()
    # The copied symlink still points at the host path (broken inside any
    # container that doesn't expose tmp_path)
    assert copied.readlink() == real_secret


# --- F-C-04: --allow-ephemeral escape hatch -------------------------------


def test_active_capabilities_works_without_hermes_home_or_ephemeral():
    """active_capabilities is informational — must not raise even when
    preflight would refuse. The fail-loud lives in preflight, not the
    capability banner."""
    caps = HermesAdapter().active_capabilities()
    # No platforms configured → just the MCP-availability line + request
    # tools line; no exception.
    assert any("MCP" in c for c in caps)


# --- F-C-08: gateway.lock cleanup reports OSError honestly ---------------


def test_preflight_reports_truthfully_when_unlink_fails(tmp_path, monkeypatch):
    """A read-only filesystem or owner-mismatched lock can't be unlinked.
    The cleanup_note must reflect that — not falsely claim 'cleared'."""
    lock_path = tmp_path / "gateway.lock"
    lock_path.write_text(json.dumps({"pid": 999999}))
    monkeypatch.setattr(hermes_module, "_is_pid_alive", lambda pid: False)

    real_unlink = Path.unlink

    def failing_unlink(self, *args, **kwargs):
        if self.name == "gateway.lock":
            raise OSError("Read-only filesystem")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", failing_unlink)

    # Gateway mode — the stale-lock cleanup path only runs when gateway.lock is
    # pre-checked (D-87/D-181), i.e. when start_command is gateway.
    adapter = HermesAdapter(
        config={"hermes_home": str(tmp_path), "start_command": "hermes gateway run"}
    )
    result = adapter.preflight()

    assert result.ok is True  # not blocking, just informational
    assert "could not unlink" in result.cleanup_note.lower()
    assert "Read-only filesystem" in result.cleanup_note
