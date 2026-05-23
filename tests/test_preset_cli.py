"""Stage 10 #3: preset CLI subapp tests (list / show / init / launch)."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from whizzard.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated_whizzard_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point WHIZZARD_HOME at a temp dir so tests use bundled defaults
    and don't touch the user's actual ~/.whizzard.

    Also writes a `mounts.json` rebinding the bundled `claude-projects`
    and `ai-sandbox` mount *names* to tmp_path subdirs that exist. The
    bundled mount defaults' `~/Documents/Claude/projects` and `~/ai-sandbox`
    paths exist on the maintainer's machine but not on CI runners
    (`/home/runner/...`), and the safety policy rejects mounts whose
    host_path is missing. Rebinding keeps the preset names valid while
    pointing at directories the test guarantees exist.
    """
    home = tmp_path / "whizzard-home"
    monkeypatch.setenv("WHIZZARD_HOME", str(home))
    from whizzard import config, harness_config, mounts, preset_config
    monkeypatch.setattr(config, "WHIZZARD_HOME", home)
    monkeypatch.setattr(config, "CONFIG_DIR", home / "config")
    monkeypatch.setattr(config, "LOGS_DIR", home / "logs")
    monkeypatch.setattr(config, "STATE_DIR", home / "state")
    monkeypatch.setattr(config, "PROFILES_FILE", home / "config" / "profiles.json")
    monkeypatch.setattr(mounts, "MOUNTS_FILE", home / "config" / "mounts.json")
    monkeypatch.setattr(harness_config, "HARNESSES_FILE", home / "config" / "harnesses.json")
    monkeypatch.setattr(preset_config, "PRESETS_FILE", home / "config" / "presets.json")
    # Also patch the references in each CLI subapp module — they import
    # the file-path constants at module load, so the source-module
    # patches above don't reach the already-bound names in subapps.
    from whizzard.cli import harnesses as cli_harnesses
    from whizzard.cli import mounts as cli_mounts
    from whizzard.cli import preset as cli_preset
    from whizzard.cli import profiles as cli_profiles
    monkeypatch.setattr(cli_profiles, "PROFILES_FILE", home / "config" / "profiles.json")
    monkeypatch.setattr(cli_mounts, "MOUNTS_FILE", home / "config" / "mounts.json")
    monkeypatch.setattr(cli_harnesses, "HARNESSES_FILE", home / "config" / "harnesses.json")
    monkeypatch.setattr(cli_preset, "PRESETS_FILE", home / "config" / "presets.json")

    # Rebind bundled mount names to tmp paths that exist (see docstring).
    claude_projects = tmp_path / "claude-projects"
    ai_sandbox = tmp_path / "ai-sandbox"
    claude_projects.mkdir()
    ai_sandbox.mkdir()
    (home / "config").mkdir(parents=True, exist_ok=True)
    (home / "config" / "mounts.json").write_text(json.dumps({
        "schema_version": 1,
        "mounts": {
            "claude-projects": {
                "host_path": str(claude_projects),
                "default_mode": "rw",
                "description": "CI-test rebinding of the bundled claude-projects mount",
            },
            "ai-sandbox": {
                "host_path": str(ai_sandbox),
                "default_mode": "rw",
                "description": "CI-test rebinding of the bundled ai-sandbox mount",
            },
        },
    }))
    # Rebind the bundled `hermes-cell` harness's `hermes_home` to an empty
    # tmp dir so the F-C-01 mount-time auth.json check has nothing to
    # refuse. Without this, the real user's `~/.hermes-whizzard-cell`
    # (which may contain auth.lock from prior sessions) would block
    # every dry-run that uses the bundled hermes preset.
    hermes_home = tmp_path / "hermes-home"
    hermes_home.mkdir()
    (home / "config" / "harnesses.json").write_text(json.dumps({
        "schema_version": 1,
        "harnesses": {
            "generic": {"type": "shell", "start_command": "/bin/bash"},
            "hermes-cell": {
                "type": "agent",
                "start_command": "hermes gateway run",
                "wrap_up_command": "/quit",
                "wrap_up_grace_seconds": 30,
                "hermes_home": str(hermes_home),
                "platforms": ["discord"],
            },
        },
    }))
    return home


# --- preset list ----------------------------------------------------------


def test_preset_list_shows_bundled_defaults():
    result = runner.invoke(app, ["preset", "list"])
    assert result.exit_code == 0
    out = result.output
    assert "hermes" in out
    assert "shell" in out
    assert "bundled defaults" in out


def test_preset_list_validates_references():
    """List passes the reference-validation step against bundled
    profiles/harnesses/mounts."""
    result = runner.invoke(app, ["preset", "list"])
    assert result.exit_code == 0


# --- preset show ----------------------------------------------------------


def test_preset_show_known_succeeds():
    result = runner.invoke(app, ["preset", "show", "hermes"])
    assert result.exit_code == 0
    out = result.output
    assert "Profile:" in out
    assert "default" in out
    assert "hermes-cell" in out
    assert "claude-projects" in out
    assert "discord" in out


def test_preset_show_unknown_errors():
    result = runner.invoke(app, ["preset", "show", "nonexistent"])
    assert result.exit_code == 2
    assert "unknown preset" in result.output


# --- preset init ----------------------------------------------------------


def test_preset_init_writes_file(isolated_whizzard_home: Path):
    presets_file = isolated_whizzard_home / "config" / "presets.json"
    assert not presets_file.exists()

    result = runner.invoke(app, ["preset", "init"])
    assert result.exit_code == 0
    assert presets_file.exists()

    data = json.loads(presets_file.read_text())
    assert data["schema_version"] == 1
    assert "hermes" in data["presets"]
    assert "shell" in data["presets"]


def test_preset_init_refuses_to_clobber(isolated_whizzard_home: Path):
    presets_file = isolated_whizzard_home / "config" / "presets.json"
    presets_file.parent.mkdir(parents=True, exist_ok=True)
    presets_file.write_text('{"schema_version": 1, "presets": {}}')

    result = runner.invoke(app, ["preset", "init"])
    assert result.exit_code == 1
    # Console wraps the long path across lines; match the message keywords
    # independently rather than a fragile contiguous substring.
    assert "already" in result.output
    assert "--force" in result.output


def test_preset_init_force_overwrites(isolated_whizzard_home: Path):
    presets_file = isolated_whizzard_home / "config" / "presets.json"
    presets_file.parent.mkdir(parents=True, exist_ok=True)
    presets_file.write_text('{"schema_version": 1, "presets": {}}')

    result = runner.invoke(app, ["preset", "init", "--force"])
    assert result.exit_code == 0
    data = json.loads(presets_file.read_text())
    assert "hermes" in data["presets"]


def test_preset_init_omits_unset_override_fields(isolated_whizzard_home: Path):
    """Bundled presets that don't override duration/idle/allow_broad_mount
    should write those fields OUT of the file, preserving omit-to-inherit."""
    result = runner.invoke(app, ["preset", "init"])
    assert result.exit_code == 0
    presets_file = isolated_whizzard_home / "config" / "presets.json"
    data = json.loads(presets_file.read_text())
    shell = data["presets"]["shell"]
    # shell preset doesn't override these
    assert "duration_seconds" not in shell
    assert "idle_timeout_seconds" not in shell
    assert "allow_broad_mount" not in shell


def test_preset_init_keeps_explicit_override_fields(isolated_whizzard_home: Path):
    """Bundled `hermes` preset explicitly sets duration_seconds=None and
    idle_timeout_seconds=None — those should appear in the written file."""
    result = runner.invoke(app, ["preset", "init"])
    assert result.exit_code == 0
    presets_file = isolated_whizzard_home / "config" / "presets.json"
    data = json.loads(presets_file.read_text())
    hermes = data["presets"]["hermes"]
    assert "duration_seconds" in hermes
    assert hermes["duration_seconds"] is None
    assert "idle_timeout_seconds" in hermes
    assert hermes["idle_timeout_seconds"] is None


# --- preset launch (dry-run path) -----------------------------------------
#
# Hermes adapter's container_env fetches credentials at launch time; dry-run
# still calls it to build the docker argv preview. To avoid requiring a real
# OneCLI install in tests, we monkeypatch the fetch_secret entry point.


@pytest.fixture
def fake_credential_fetch(monkeypatch: pytest.MonkeyPatch):
    """Monkeypatch the adapter's credential-fetch path so Hermes-using
    preset launches work in tests without OneCLI installed."""
    from whizzard.adapters import _credentials
    from whizzard.adapters import hermes as hermes_module

    class _FakeResult:
        def __init__(self, value: str) -> None:
            self.value = value
            self.source = "onecli"

    def fake_fetch(name: str) -> _FakeResult:
        return _FakeResult(f"fake-{name}")

    monkeypatch.setattr(_credentials, "fetch_secret", fake_fetch)
    monkeypatch.setattr(hermes_module, "fetch_secret", fake_fetch)


def test_preset_launch_dry_run_uses_preset_profile_and_mounts(fake_credential_fetch):
    """Dry-run shows the resolved launch — profile from preset, mounts from
    preset, harness from preset. Verifies preset_launch wires through to
    _perform_launch correctly."""
    result = runner.invoke(app, ["preset", "launch", "hermes", "--dry-run"])
    assert result.exit_code == 0, result.output
    out = result.output
    # Profile from preset is "default"
    assert "DEFAULT" in out  # banner uppercases the profile name
    # Mounts from preset
    assert "claude-projects" in out
    assert "ai-sandbox" in out
    # Harness from preset
    assert "hermes-cell" in out


def test_preset_launch_dry_run_shell_preset_no_mounts():
    """Shell preset has no mounts; dry-run should show 'Mounts: none'."""
    result = runner.invoke(app, ["preset", "launch", "shell", "--dry-run"])
    assert result.exit_code == 0, result.output
    out = result.output
    assert "SAFE" in out  # safe profile
    assert "Mounts:" in out
    assert "none" in out


def test_preset_launch_unknown_errors():
    result = runner.invoke(app, ["preset", "launch", "nonexistent", "--dry-run"])
    assert result.exit_code == 2
    assert "unknown preset" in result.output


def test_preset_launch_dry_run_does_not_check_docker(fake_credential_fetch):
    """Dry-run should not require Docker to be present (matches `whiz run`
    dry-run behavior)."""
    result = runner.invoke(app, ["preset", "launch", "hermes", "--dry-run"])
    # Should not error on missing docker — dry-run is informational
    assert result.exit_code == 0, result.output


def test_preset_launch_dry_run_propagates_platform_restriction(
    isolated_whizzard_home: Path,
    fake_credential_fetch,
):
    """Hermes preset declares platforms=['discord']; verify the dry-run
    argv includes the WHIZ env wiring expected when MCP is on (proxy for
    the adapter receiving the restricted platform set)."""
    result = runner.invoke(app, ["preset", "launch", "hermes", "--dry-run"])
    assert result.exit_code == 0, result.output
    out = result.output
    # The Hermes adapter's mcp_env should appear in the docker invocation
    # because the harness type is 'agent' and session_id is present
    assert "WHIZ_SESSION_ID" in out
