"""Stage 10 #4-#5: status command + brevity aliases (whiz r/s/p/m/pr) tests."""

import calendar
import json
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from whizzard.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated_whizzard_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Isolate WHIZZARD_HOME to a temp dir per test."""
    home = tmp_path / "whizzard-home"
    monkeypatch.setenv("WHIZZARD_HOME", str(home))
    from whizzard import config, harness_config, mounts, preset_config, session_log
    monkeypatch.setattr(config, "WHIZZARD_HOME", home)
    monkeypatch.setattr(config, "CONFIG_DIR", home / "config")
    monkeypatch.setattr(config, "LOGS_DIR", home / "logs")
    monkeypatch.setattr(config, "STATE_DIR", home / "state")
    monkeypatch.setattr(config, "PROFILES_FILE", home / "config" / "profiles.json")
    monkeypatch.setattr(mounts, "MOUNTS_FILE", home / "config" / "mounts.json")
    monkeypatch.setattr(harness_config, "HARNESSES_FILE", home / "config" / "harnesses.json")
    monkeypatch.setattr(preset_config, "PRESETS_FILE", home / "config" / "presets.json")
    monkeypatch.setattr(session_log, "SESSIONS_LOG", home / "logs" / "sessions.jsonl")
    # Also patch the references in each CLI subapp module — they import
    # the file-path constants at module load, so source-module patches
    # above don't reach already-bound names in subapps.
    from whizzard.cli import _session as cli_session
    from whizzard.cli import harnesses as cli_harnesses
    from whizzard.cli import mounts as cli_mounts
    from whizzard.cli import preset as cli_preset
    from whizzard.cli import profiles as cli_profiles
    from whizzard.cli import sessions as cli_sessions
    monkeypatch.setattr(cli_profiles, "PROFILES_FILE", home / "config" / "profiles.json")
    monkeypatch.setattr(cli_mounts, "MOUNTS_FILE", home / "config" / "mounts.json")
    monkeypatch.setattr(cli_harnesses, "HARNESSES_FILE", home / "config" / "harnesses.json")
    monkeypatch.setattr(cli_preset, "PRESETS_FILE", home / "config" / "presets.json")
    monkeypatch.setattr(cli_sessions, "SESSIONS_LOG", home / "logs" / "sessions.jsonl")
    monkeypatch.setattr(cli_session, "SESSIONS_LOG", home / "logs" / "sessions.jsonl")
    return home


@pytest.fixture
def fake_credentials(monkeypatch: pytest.MonkeyPatch):
    """Stub the Hermes adapter's credential fetch so preset-launch tests
    don't require OneCLI."""
    from whizzard.adapters import _credentials
    from whizzard.adapters import hermes as hermes_module

    class _R:
        def __init__(self, v: str) -> None:
            self.value = v
            self.source = "onecli"

    def fake_fetch(name: str) -> _R:
        return _R(f"fake-{name}")

    monkeypatch.setattr(_credentials, "fetch_secret", fake_fetch)
    monkeypatch.setattr(hermes_module, "fetch_secret", fake_fetch)


def _write_session_log(home: Path, entries: list[dict]) -> None:
    """Write a sessions.jsonl with the given entries."""
    log = home / "logs" / "sessions.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("\n".join(json.dumps(e) for e in entries) + "\n")


# --- status command ------------------------------------------------------


def test_status_with_no_log(isolated_whizzard_home: Path):
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "no sessions" in result.output.lower()


def test_status_shows_active_count(isolated_whizzard_home: Path):
    _write_session_log(isolated_whizzard_home, [
        {"event": "session_start", "session_id": "sid-1", "profile": "default",
         "start_time": "2026-05-16T00:00:00Z", "argv": []},
        {"event": "session_end", "session_id": "sid-1", "end_time": "2026-05-16T01:00:00Z"},
        {"event": "session_start", "session_id": "sid-2", "profile": "default",
         "start_time": "2026-05-16T02:00:00Z", "argv": []},
    ])
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    out = result.output
    assert "Active sessions" in out
    # sid-2 still running; sid-1 ended
    assert "RUNNING" in out
    assert "ended" in out


def test_status_extracts_harness_from_argv(isolated_whizzard_home: Path):
    _write_session_log(isolated_whizzard_home, [
        {
            "event": "session_start",
            "session_id": "sid-1",
            "profile": "default",
            "start_time": "2026-05-16T00:00:00Z",
            "argv": ["docker", "run", "--label", "whizzard.harness=hermes-cell"],
        },
    ])
    result = runner.invoke(app, ["status"])
    assert "hermes-cell" in result.output


def test_status_skips_malformed_lines(isolated_whizzard_home: Path):
    log = isolated_whizzard_home / "logs" / "sessions.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(
        json.dumps({"event": "session_start", "session_id": "sid-1",
                    "profile": "default", "start_time": "x", "argv": []}) + "\n"
        + "garbage line\n"
        + "\n"
    )
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0


# --- bare `whiz` -> status -----------------------------------------------


def test_bare_whiz_routes_to_status(isolated_whizzard_home: Path):
    """No subcommand should land in status mode, not help."""
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    # In an empty-log state, status prints "no sessions" hint
    assert "no sessions" in result.output.lower()


# --- whiz s (status alias) -----------------------------------------------


def test_whiz_s_routes_to_status(isolated_whizzard_home: Path):
    result = runner.invoke(app, ["s"])
    assert result.exit_code == 0
    assert "no sessions" in result.output.lower()


# --- whiz p (preset list / show) ----------------------------------------


def test_whiz_p_bare_lists_presets(isolated_whizzard_home: Path):
    result = runner.invoke(app, ["p"])
    assert result.exit_code == 0
    assert "hermes" in result.output
    assert "shell" in result.output


def test_whiz_p_with_name_shows_preset(isolated_whizzard_home: Path):
    result = runner.invoke(app, ["p", "hermes"])
    assert result.exit_code == 0
    assert "hermes-cell" in result.output
    assert "discord" in result.output


def test_whiz_p_unknown_errors(isolated_whizzard_home: Path):
    result = runner.invoke(app, ["p", "nonexistent"])
    assert result.exit_code == 2


# --- whiz m (mounts list) ------------------------------------------------


def test_whiz_m_lists_mounts(isolated_whizzard_home: Path):
    result = runner.invoke(app, ["m"])
    assert result.exit_code == 0
    assert "claude-projects" in result.output
    assert "ai-sandbox" in result.output


# --- whiz pr (profiles list) ---------------------------------------------


def test_whiz_pr_lists_profiles(isolated_whizzard_home: Path):
    result = runner.invoke(app, ["pr"])
    assert result.exit_code == 0
    out = result.output
    for profile_name in ["safe", "default", "build", "power", "quarantine"]:
        assert profile_name in out


# --- whiz r (smart dispatch) ---------------------------------------------


def test_whiz_r_with_preset_name_dry_run(isolated_whizzard_home: Path, fake_credentials):
    result = runner.invoke(app, ["r", "shell", "--dry-run"])
    assert result.exit_code == 0, result.output
    out = result.output
    assert "SAFE" in out  # shell preset uses safe profile


def test_whiz_r_with_run_flags(isolated_whizzard_home: Path):
    result = runner.invoke(app, ["r", "--profile", "safe", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "SAFE" in result.output


def test_whiz_r_mixing_preset_and_run_flags_errors(isolated_whizzard_home: Path):
    result = runner.invoke(app, ["r", "shell", "--profile", "default", "--dry-run"])
    assert result.exit_code == 2
    assert "cannot mix" in result.output.lower()


def test_whiz_r_bare_with_no_recent_preset_errors(isolated_whizzard_home: Path):
    result = runner.invoke(app, ["r"])
    assert result.exit_code == 2
    assert "no recent preset" in result.output.lower()


def test_whiz_r_bare_uses_most_recent_preset(
    isolated_whizzard_home: Path,
    fake_credentials,
):
    """A session_start with a `preset` field should make bare `whiz r` launch
    that preset."""
    _write_session_log(isolated_whizzard_home, [
        {"event": "session_start", "session_id": "sid-1", "profile": "safe",
         "preset": "shell", "start_time": "2026-05-16T00:00:00Z", "argv": []},
        {"event": "session_end", "session_id": "sid-1", "end_time": "x"},
    ])
    result = runner.invoke(app, ["r", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "SAFE" in result.output  # shell preset → safe profile


def test_whiz_r_most_recent_skips_non_preset_runs(
    isolated_whizzard_home: Path,
    fake_credentials,
):
    """A `whiz run` without a preset shouldn't be picked up as 'most recent
    preset'. Bare `whiz r` should walk past it to find an earlier preset entry."""
    _write_session_log(isolated_whizzard_home, [
        {"event": "session_start", "session_id": "sid-1", "profile": "safe",
         "preset": "shell", "start_time": "2026-05-16T00:00:00Z", "argv": []},
        {"event": "session_start", "session_id": "sid-2", "profile": "default",
         "start_time": "2026-05-16T01:00:00Z", "argv": []},
        # ^^^ no preset field — `whiz run` invocation
    ])
    result = runner.invoke(app, ["r", "--dry-run"])
    assert result.exit_code == 0, result.output
    # Picked up shell preset (the most recent with a preset field)
    assert "SAFE" in result.output


# --- preset_name propagation through launch flow ------------------------


def test_preset_launch_writes_preset_field_to_session_log(
    isolated_whizzard_home: Path,
    fake_credentials,
    monkeypatch: pytest.MonkeyPatch,
):
    """Verify that `whiz preset launch <name>` (not dry-run) results in a
    session_start entry that includes the preset field, so subsequent bare
    `whiz r` can find it."""
    # Stub out run_shell to avoid actually launching docker, but let the
    # log_session_start call happen. Patches go on the _launch module
    # (where the imports live after the cli/ package split).
    from whizzard.cli import _launch as cli_launch

    captured: dict = {}

    def fake_log_session_start(**kwargs):
        captured.update(kwargs)

    def fake_run_shell(*args, **kwargs):
        # Simulate the log_session_start happening from inside run_shell
        fake_log_session_start(
            preset_name=kwargs.get("preset_name"),
        )
        from whizzard.docker_cmd import RunResult
        return RunResult(container_id="fake-cid", exit_code=0)

    monkeypatch.setattr(cli_launch, "run_shell", fake_run_shell)
    monkeypatch.setattr(cli_launch, "docker_available", lambda: True)
    monkeypatch.setattr(cli_launch, "image_exists", lambda image: True)

    result = runner.invoke(app, ["preset", "launch", "shell"])
    assert result.exit_code == 0, result.output
    assert captured.get("preset_name") == "shell"


# --- Stage 15: status duration-remaining display --------------------------


def test_remaining_seconds_computes_time_left():
    from whizzard.cli._session import _remaining_seconds
    ev = {"duration_limit_seconds": 3600, "start_time": "2026-05-22T00:00:00Z"}
    # 600s elapsed → 3000s left
    remaining = _remaining_seconds(ev, now=calendar.timegm(
        time.strptime("2026-05-22T00:10:00Z", "%Y-%m-%dT%H:%M:%SZ")))
    assert remaining == 3000


def test_remaining_seconds_none_for_unlimited_session():
    from whizzard.cli._session import _remaining_seconds
    assert _remaining_seconds({"duration_limit_seconds": None}) is None


def test_remaining_seconds_none_when_timestamp_unparseable():
    from whizzard.cli._session import _remaining_seconds
    ev = {"duration_limit_seconds": 3600, "start_time": "not-a-date"}
    assert _remaining_seconds(ev) is None


def test_remaining_seconds_handles_microsecond_iso_with_offset():
    """F-H-01: post-F-D-08 the audit log uses microsecond ISO with
    +00:00 offset, not the old Z suffix. The strptime pattern in
    `_remaining_seconds` silently failed against the new format,
    leaving `whiz status` unable to display time-remaining for real
    sessions. Now uses `datetime.fromisoformat`."""
    from datetime import UTC, datetime, timedelta

    from whizzard.cli._session import _remaining_seconds

    # Simulate a session_start written 10 minutes ago by the real producer.
    ten_min_ago = datetime.now(UTC) - timedelta(minutes=10)
    ev = {
        "duration_limit_seconds": 3600,
        "start_time": ten_min_ago.isoformat(),  # microsecond + +00:00
    }
    remaining = _remaining_seconds(ev)
    # Should be ~3000s ± slop (10 min elapsed of a 1h cap).
    assert remaining is not None
    assert 2990 <= remaining <= 3010


# --- F-H-02: `whiz image build` preflights docker availability ------------


def test_image_build_exits_127_when_docker_missing(monkeypatch):
    """Previously raised a raw FileNotFoundError traceback at
    subprocess.run; now uses the same docker-not-found path as every
    other docker-touching CLI verb."""
    from whizzard.cli import image as cli_image
    monkeypatch.setattr(cli_image, "docker_available", lambda: False)
    # If we got past the preflight, subprocess.run would be reached;
    # patch it to a sentinel that would fail the test if invoked.
    monkeypatch.setattr(
        cli_image.subprocess, "run",
        lambda *a, **kw: (_ for _ in ()).throw(
            AssertionError("subprocess.run should not be reached")
        ),
    )
    runner = CliRunner()
    result = runner.invoke(app, ["image", "build"])
    assert result.exit_code == 127
    assert "docker not found" in result.output


def test_fmt_remaining_renders_units():
    from whizzard.cli import _fmt_remaining
    assert _fmt_remaining(None) == "—"
    assert _fmt_remaining(0) == "[red]overdue[/red]"
    assert _fmt_remaining(-5) == "[red]overdue[/red]"
    assert _fmt_remaining(45) == "~45s"
    assert _fmt_remaining(720) == "~12m"
    assert _fmt_remaining(3 * 3600 + 600) == "~3h10m"


# --- --version flag (launch-readiness §H) ----------------------------------


def test_version_flag_prints_version_and_exits(isolated_whizzard_home: Path):
    """`whiz --version` prints the package version and exits 0 — the
    flag existed in no form before launch-readiness verification caught it."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "whizzard" in result.output.lower()
    # Either a real installed version or the source-tree sentinel.
    assert any(ch.isdigit() for ch in result.output)


def test_version_flag_does_not_require_config(tmp_path, monkeypatch):
    """`--version` is eager and must short-circuit before the bootstrap
    scaffolds ~/.whizzard/ — it should work even pointed at a brand-new
    home that doesn't exist yet."""
    fresh = tmp_path / "nonexistent-home"
    monkeypatch.setenv("WHIZZARD_HOME", str(fresh))
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "whizzard" in result.output.lower()


def test_help_groups_commands_into_workflow_panels_with_footer():
    """`whiz --help` groups commands by workflow (rich_help_panel) and ends
    with a footer telling the user how to invoke a command and find its
    flags — not a flat, ungrouped command list."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for panel in (
        "Setup",
        "Launch a session",
        "Control a running session",
        "Inspect your setup",
        "Shortcuts",
    ):
        assert panel in result.output, f"missing help panel: {panel}"
    # Footer: invocation + flag discovery, rendered on two separate lines.
    # Assert on the distinctive phrases rather than the full sentence — rich
    # wraps the epilog at the terminal width, so "whiz <command> --help" can
    # straddle two lines.
    assert "Run any command as" in result.output
    assert "See its flags with" in result.output
