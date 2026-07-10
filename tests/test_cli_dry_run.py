"""Stage 4: dry-run tests for the run command."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from rich.console import Console
from typer.testing import CliRunner

from whizzard.cli import _launch, app
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
        result = runner.invoke(app, ["run", "--harness", "generic", "--profile", "default", "--dry-run"])
    assert result.exit_code == 0
    assert mock_run.call_count == 0


def test_dry_run_output_contains_dry_run_banner():
    result = runner.invoke(app, ["run", "--harness", "generic", "--profile", "default", "--dry-run"])
    assert result.exit_code == 0
    assert "DRY RUN" in result.output


def test_dry_run_output_contains_profile_summary():
    result = runner.invoke(app, ["run", "--harness", "generic", "--profile", "build", "--dry-run"])
    assert "BUILD" in result.output
    assert "Network" in result.output
    assert "Duration" in result.output
    assert "Image" in result.output


def test_dry_run_resolves_image_from_harness_when_not_overridden():
    """Harness↔image coupling: with no --image, the launch uses the selected
    harness's default_image (generic → base) rather than a hardcoded CLI
    default. The bug was that the base image was used regardless of harness."""
    from whizzard.images import WHIZZARD_IMAGE

    result = runner.invoke(app, ["run", "--harness", "generic", "--profile", "default", "--dry-run"])
    assert result.exit_code == 0
    assert WHIZZARD_IMAGE in result.output


def test_dry_run_explicit_image_overrides_harness_default():
    result = runner.invoke(
        app, ["run", "--harness", "generic", "--profile", "default", "--image", "custom:tag", "--dry-run"]
    )
    assert result.exit_code == 0
    assert "custom:tag" in result.output


def test_dry_run_output_contains_docker_argv():
    result = runner.invoke(app, ["run", "--harness", "generic", "--profile", "default", "--dry-run"])
    out = result.output
    assert "docker invocation that would run" in out
    assert "docker" in out
    assert "run" in out
    assert "--rm" in out
    assert "--cap-drop=ALL" in out
    assert "/bin/bash" in out


def test_dry_run_includes_mount_in_argv(tmp_path: Path, monkeypatch):
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

    # Pin the dry-run console to a wide width so Rich doesn't line-wrap
    # the docker invocation preview at CI's narrow auto-detected terminal
    # width. `_launch` imports `console` at module load (a bound name),
    # so patching the source module wouldn't reach it — patch the
    # already-bound reference inside `_launch` itself.
    # `highlight=False` keeps Rich from injecting ANSI colour codes inside
    # token text (it would otherwise paint "alpha" yellow inside
    # `test-alpha`, breaking substring matches with embedded escapes).
    monkeypatch.setattr(
        _launch, "console",
        Console(width=200, force_terminal=True, highlight=False),
    )

    result = runner.invoke(
        app,
        ["run", "--harness", "generic", "--profile", "build", "--mount", "test-alpha", "--dry-run"],
    )
    assert result.exit_code == 0
    assert "-v" in result.output
    assert "/mounts/test-alpha:rw" in result.output


def test_dry_run_with_unknown_profile_errors():
    result = runner.invoke(app, ["run", "--harness", "generic", "--profile", "nope", "--dry-run"])
    assert result.exit_code == 2
    assert "Unknown profile" in result.output


def test_dry_run_with_unknown_mount_errors():
    result = runner.invoke(
        app,
        ["run", "--harness", "generic", "--profile", "default", "--mount", "does-not-exist", "--dry-run"],
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
        result = runner.invoke(app, ["run", "--harness", "generic", "--profile", "default"])
    assert mock_run.call_count == 1
    assert result.exit_code == 0


def test_dry_run_shows_broad_mount_override_state():
    """Stage 4 dry-run surfaces broad-mount override status from the profile.

    Per D-157, the bundled `default` profile now has `allow_broad_mount=True`
    (was False). `safe` is used here for the "blocked" assertion since it
    still has `allow_broad_mount=False` as a representative locked-down profile.
    """
    result = runner.invoke(app, ["run", "--harness", "generic", "--profile", "power", "--dry-run"])
    out = result.output
    assert "Broad-mount override" in out
    assert "allowed" in out

    result = runner.invoke(app, ["run", "--harness", "generic", "--profile", "default", "--dry-run"])
    out = result.output
    assert "Broad-mount override" in out
    assert "allowed" in out  # D-157: default flipped to allow_broad_mount=True

    result = runner.invoke(app, ["run", "--harness", "generic", "--profile", "safe", "--dry-run"])
    out = result.output
    assert "Broad-mount override" in out
    assert "blocked" in out


# Stage 5 — session log integration

def test_dry_run_shows_session_id():
    result = runner.invoke(app, ["run", "--harness", "generic", "--profile", "default", "--dry-run"])
    assert "Session ID" in result.output


def test_dry_run_argv_includes_session_label():
    result = runner.invoke(app, ["run", "--harness", "generic", "--profile", "default", "--dry-run"])
    assert "whizzard.session_id" in result.output


def test_dry_run_does_not_write_session_log(tmp_path: Path, monkeypatch):
    """Dry-run must not touch the session log."""
    from whizzard import session_log
    log_path = tmp_path / "sessions.jsonl"
    monkeypatch.setattr(session_log, "SESSIONS_LOG", log_path)
    result = runner.invoke(app, ["run", "--harness", "generic", "--profile", "default", "--dry-run"])
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

    result = runner.invoke(app, ["run", "--harness", "generic", "--profile", "default", "--image", "bogus:nope"])
    assert result.exit_code == 125
    assert "error: image" in result.output
    assert "bogus:nope" in result.output


def test_missing_docker_shows_red_error_via_cli(monkeypatch):
    from whizzard.cli import _launch as cli_launch
    monkeypatch.setattr(cli_launch, "docker_available", lambda: False)
    def _should_not_be_called(*a, **kw):
        raise AssertionError("run_shell should not be reached when docker is missing")
    monkeypatch.setattr(cli_launch, "run_shell", _should_not_be_called)

    result = runner.invoke(app, ["run", "--harness", "generic", "--profile", "default"])
    assert result.exit_code == 127
    assert "docker not found" in result.output


# Stage 7 — adapter / harness flag

def test_dry_run_banner_shows_harness_name():
    result = runner.invoke(app, ["run", "--harness", "generic", "--profile", "default", "--dry-run"])
    assert "Harness" in result.output
    assert "generic" in result.output


def test_dry_run_argv_includes_harness_label():
    result = runner.invoke(app, ["run", "--harness", "generic", "--profile", "default", "--dry-run"])
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


# --- F-C-10: adapter preflight wired into _perform_launch -----------------


def _write_hermes_harness_with_no_home(monkeypatch) -> None:
    """Helper: write a harnesses.json with a Hermes harness missing hermes_home,
    so preflight will refuse unless --allow-ephemeral."""
    import os
    home = Path(os.environ["WHIZZARD_HOME"])
    config_dir = home / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "harnesses.json").write_text(json.dumps({
        "schema_version": 1,
        "harnesses": {
            "generic": {"type": "shell", "start_command": "/bin/bash"},
            "hermes-no-home": {
                "type": "agent",
                "start_command": "hermes gateway run",
            },
        },
    }))


def test_preflight_refuses_hermes_without_home(monkeypatch):
    """F-C-04 + F-C-10: agent harness with no hermes_home fails launch
    with a clear reason, before any docker work."""
    _write_hermes_harness_with_no_home(monkeypatch)
    # Mock credential fetch so the test doesn't shell out to OneCLI.
    from whizzard.adapters import _credentials
    from whizzard.adapters import hermes as hermes_module
    from whizzard.adapters._credentials import SecretFetchResult

    def fake_fetch(name):
        return SecretFetchResult(value=f"v-{name}", source="onecli")
    monkeypatch.setattr(_credentials, "fetch_secret", fake_fetch)
    monkeypatch.setattr(hermes_module, "fetch_secret", fake_fetch)

    result = runner.invoke(app, [
        "run", "--profile", "default", "--harness", "hermes-no-home",
    ])
    assert result.exit_code == 2
    assert "hermes_home" in result.output
    assert "--allow-ephemeral" in result.output


def test_preflight_passes_hermes_when_allow_ephemeral(monkeypatch):
    """F-C-04: --allow-ephemeral is the escape hatch."""
    _write_hermes_harness_with_no_home(monkeypatch)
    from whizzard.adapters import _credentials
    from whizzard.adapters import hermes as hermes_module
    from whizzard.adapters._credentials import SecretFetchResult

    monkeypatch.setattr(
        _credentials, "fetch_secret",
        lambda n: SecretFetchResult(value=f"v-{n}", source="onecli"),
    )
    monkeypatch.setattr(
        hermes_module, "fetch_secret",
        lambda n: SecretFetchResult(value=f"v-{n}", source="onecli"),
    )

    result = runner.invoke(app, [
        "run", "--profile", "default", "--harness", "hermes-no-home",
        "--allow-ephemeral", "--dry-run",
    ])
    # Dry-run gets past preflight; should succeed.
    assert result.exit_code == 0, result.output


# S20.3 / D-133 — fail-closed on snapshot-write failure


def test_launch_aborts_when_snapshot_write_fails(monkeypatch):
    """A failed snapshot write must abort the launch with a clear error.
    Per D-156 the snapshot is the agent's view of its own constraints;
    a launch with no readable snapshot leaves the agent blind to its
    own boundaries — fail-closed, not fail-open."""
    def _exploding_snapshot(*args, **kwargs):
        raise OSError("disk full")

    with patch("whizzard.cli._launch.write_snapshot", side_effect=_exploding_snapshot), \
         patch("whizzard.cli._launch.docker_available", return_value=True), \
         patch("whizzard.cli._launch.image_exists", return_value=True), \
         patch("whizzard.cli._launch.run_shell") as mock_run:
        result = runner.invoke(app, ["run", "--harness", "generic", "--profile", "default"])

    # The launch must NOT have proceeded to run_shell.
    assert mock_run.call_count == 0, (
        "snapshot write failed but run_shell was still called — fail-open!"
    )
    # And the user must see a clear error.
    assert result.exit_code == 2, result.output
    assert "snapshot" in result.output.lower()


# --- --credential-handling override (D-191) --------------------------------


def test_credential_handling_rejects_unknown_value():
    result = runner.invoke(
        app,
        ["run", "--harness", "generic", "--profile", "default",
         "--credential-handling", "bogus", "--dry-run"],
    )
    assert result.exit_code == 2
    assert "native" in result.output and "onecli" in result.output


def test_credential_handling_rejects_internal_name():
    """The internal 'mediated' name is not an accepted alias — 'native' is the
    one user-facing term (D-191 naming)."""
    result = runner.invoke(
        app,
        ["run", "--harness", "generic", "--profile", "default",
         "--credential-handling", "mediated", "--dry-run"],
    )
    assert result.exit_code == 2


def test_credential_handling_onecli_overrides_profile():
    """Override forces the session's credential posture regardless of profile;
    the dry-run banner reflects the overridden mode."""
    result = runner.invoke(
        app,
        ["run", "--harness", "generic", "--profile", "safe",
         "--credential-handling", "onecli", "--dry-run"],
    )
    assert result.exit_code == 0
    # 'safe' is network-off by default; the override flips it to the onecli path.
    assert "onecli gateway" in result.output
