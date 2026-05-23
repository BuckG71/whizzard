"""Stage 4: dry-run tests for the run command."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from whizzard.cli import app
from whizzard.docker_cmd import RunResult

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated_whizzard_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point WHIZZARD_HOME at a temp dir so tests don't pollute the user's
    actual ~/.whizzard, and reset module-level paths in dependent modules.
    """
    home = tmp_path / "whizzard-home"
    monkeypatch.setenv("WHIZZARD_HOME", str(home))
    from whizzard import config, harness_config, mounts
    monkeypatch.setattr(config, "WHIZZARD_HOME", home)
    monkeypatch.setattr(config, "CONFIG_DIR", home / "config")
    monkeypatch.setattr(config, "LOGS_DIR", home / "logs")
    monkeypatch.setattr(config, "STATE_DIR", home / "state")
    monkeypatch.setattr(config, "PROFILES_FILE", home / "config" / "profiles.json")
    monkeypatch.setattr(mounts, "MOUNTS_FILE", home / "config" / "mounts.json")
    monkeypatch.setattr(harness_config, "HARNESSES_FILE", home / "config" / "harnesses.json")
    yield


def test_dry_run_does_not_call_run_shell():
    """Dry-run must not invoke run_shell — that's the whole point."""
    with patch("whizzard.cli._launch.run_shell") as mock_run:
        result = runner.invoke(app, ["run", "--profile", "default", "--dry-run"])
    assert result.exit_code == 0
    assert mock_run.call_count == 0


def test_dry_run_output_contains_dry_run_banner():
    result = runner.invoke(app, ["run", "--profile", "default", "--dry-run"])
    assert result.exit_code == 0
    assert "DRY RUN" in result.output


def test_dry_run_output_contains_profile_summary():
    result = runner.invoke(app, ["run", "--profile", "build", "--dry-run"])
    assert "BUILD" in result.output
    assert "Network" in result.output
    assert "Duration" in result.output
    assert "Image" in result.output


def test_dry_run_output_contains_docker_argv():
    result = runner.invoke(app, ["run", "--profile", "default", "--dry-run"])
    out = result.output
    assert "docker invocation that would run" in out
    assert "docker" in out
    assert "run" in out
    assert "--rm" in out
    assert "--cap-drop=ALL" in out
    assert "/bin/bash" in out


def test_dry_run_includes_mount_in_argv(tmp_path: Path):
    """Dry-run with a mount should show the -v line in the argv."""
    target = tmp_path / "alpha"
    target.mkdir()

    home = Path(__import__("os").environ["WHIZZARD_HOME"])
    config_dir = home / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "mounts.json").write_text(json.dumps({
        "schema_version": 1,
        "mounts": {
            "test-alpha": {
                "host_path": str(target),
                "default_mode": "rw",
            },
        },
    }))

    result = runner.invoke(
        app,
        ["run", "--profile", "build", "--mount", "test-alpha", "--dry-run"],
    )
    assert result.exit_code == 0
    assert "-v" in result.output
    # Output is wrap-robustness: rich-rendered docker invocation may line-wrap
    # at narrow terminal widths (CI). Strip whitespace before checking.
    flat = result.output.replace("\n", "").replace(" ", "")
    assert "/mounts/test-alpha:rw" in flat


def test_dry_run_with_unknown_profile_errors():
    result = runner.invoke(app, ["run", "--profile", "nope", "--dry-run"])
    assert result.exit_code == 2
    assert "Unknown profile" in result.output


def test_dry_run_with_unknown_mount_errors():
    result = runner.invoke(
        app,
        ["run", "--profile", "default", "--mount", "does-not-exist", "--dry-run"],
    )
    assert result.exit_code == 2
    assert "unknown mount" in result.output


def test_run_without_dry_run_calls_run_shell():
    """Sanity check: omitting --dry-run still calls run_shell.

    Pre-flight gates (`docker_available`, `image_exists`) run before
    `run_shell`; on CI without a docker daemon they'd short-circuit the
    launch. Patch both so the test exercises the path the assertion is
    actually checking.
    """
    with patch("whizzard.cli._launch.run_shell", return_value=RunResult(None, 0)) as mock_run, \
         patch("whizzard.cli._launch.docker_available", return_value=True), \
         patch("whizzard.cli._launch.image_exists", return_value=True):
        result = runner.invoke(app, ["run", "--profile", "default"])
    assert mock_run.call_count == 1
    assert result.exit_code == 0


def test_dry_run_shows_broad_mount_override_state():
    """Stage 4 dry-run surfaces broad-mount override status from the profile.

    Per D-157, the bundled `default` profile now has `allow_broad_mount=True`
    (was False). `safe` is used here for the "blocked" assertion since it
    still has `allow_broad_mount=False` as a representative locked-down profile.
    """
    result = runner.invoke(app, ["run", "--profile", "power", "--dry-run"])
    out = result.output
    assert "Broad-mount override" in out
    assert "allowed" in out

    result = runner.invoke(app, ["run", "--profile", "default", "--dry-run"])
    out = result.output
    assert "Broad-mount override" in out
    assert "allowed" in out  # D-157: default flipped to allow_broad_mount=True

    result = runner.invoke(app, ["run", "--profile", "safe", "--dry-run"])
    out = result.output
    assert "Broad-mount override" in out
    assert "blocked" in out


# Stage 5 — session log integration

def test_dry_run_shows_session_id():
    result = runner.invoke(app, ["run", "--profile", "default", "--dry-run"])
    assert "Session ID" in result.output


def test_dry_run_argv_includes_session_label():
    result = runner.invoke(app, ["run", "--profile", "default", "--dry-run"])
    assert "whizzard.session_id" in result.output


def test_dry_run_does_not_write_session_log(tmp_path: Path, monkeypatch):
    """Dry-run must not touch the session log."""
    from whizzard import session_log
    log_path = tmp_path / "sessions.jsonl"
    monkeypatch.setattr(session_log, "SESSIONS_LOG", log_path)
    result = runner.invoke(app, ["run", "--profile", "default", "--dry-run"])
    assert result.exit_code == 0
    assert not log_path.exists()


# Pre-flight error formatting (red, in CLI not in run_shell)

def test_missing_image_shows_red_error_via_cli(monkeypatch):
    """Image-not-found error must come from the CLI red-error path,
    not from a plain stderr print in docker_cmd."""
    from whizzard.cli import _launch as cli_launch
    monkeypatch.setattr(cli_launch, "docker_available", lambda: True)
    monkeypatch.setattr(cli_launch, "image_exists", lambda img: False)
    # If run_shell got called, that's a regression — pre-flight should stop us.
    def _should_not_be_called(*a, **kw):
        raise AssertionError("run_shell should not be reached when image is missing")
    monkeypatch.setattr(cli_launch, "run_shell", _should_not_be_called)

    result = runner.invoke(app, ["run", "--profile", "default", "--image", "bogus:nope"])
    assert result.exit_code == 125
    assert "error: image" in result.output
    assert "bogus:nope" in result.output


def test_missing_docker_shows_red_error_via_cli(monkeypatch):
    from whizzard.cli import _launch as cli_launch
    monkeypatch.setattr(cli_launch, "docker_available", lambda: False)
    def _should_not_be_called(*a, **kw):
        raise AssertionError("run_shell should not be reached when docker is missing")
    monkeypatch.setattr(cli_launch, "run_shell", _should_not_be_called)

    result = runner.invoke(app, ["run", "--profile", "default"])
    assert result.exit_code == 127
    assert "docker not found" in result.output


# Stage 7 — adapter / harness flag

def test_dry_run_banner_shows_harness_name():
    result = runner.invoke(app, ["run", "--profile", "default", "--dry-run"])
    assert "Harness" in result.output
    assert "generic" in result.output


def test_dry_run_argv_includes_harness_label():
    result = runner.invoke(app, ["run", "--profile", "default", "--dry-run"])
    assert "whizzard.harness=generic" in result.output


def test_unknown_harness_is_rejected():
    result = runner.invoke(app, [
        "run", "--profile", "default", "--harness", "nope", "--dry-run",
    ])
    assert result.exit_code == 2
    assert "unknown harness" in result.output


def test_custom_harness_via_user_config(tmp_path: Path):
    """A user-defined shell harness in harnesses.json should work end-to-end."""
    import json
    home = Path(__import__("os").environ["WHIZZARD_HOME"])
    config_dir = home / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "harnesses.json").write_text(json.dumps({
        "schema_version": 1,
        "harnesses": {
            "zsh-flavored": {
                "type": "shell",
                "start_command": "/bin/zsh",
                "working_dir": "/home/whizzard",
            },
        },
    }))
    result = runner.invoke(app, [
        "run", "--profile", "default", "--harness", "zsh-flavored", "--dry-run",
    ])
    assert result.exit_code == 0
    assert "zsh-flavored" in result.output
    assert "/bin/zsh" in result.output
