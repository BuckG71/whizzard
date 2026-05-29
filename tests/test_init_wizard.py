"""Stage 19 / M3 — `whiz init` wizard tests.

Each step's interactive behavior is unit-tested by:
  - patching `input()` to feed pre-scripted user responses
  - patching the docker-build runner so no real docker is invoked
  - using tmp_path-isolated config dirs so no host state leaks

The wizard module is imported lazily inside tests so the autouse fixture
can monkeypatch config-file paths *before* the wizard module reads them
at import time.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from whizzard.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _isolated_whizzard_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect ~/.whizzard/ → tmp_path/whizzard-home for every test.

    Patches the underlying config modules AND the references already
    imported into whizzard.init_wizard, since module-level imports cache
    the original constants.
    """
    home = tmp_path / "whizzard-home"
    config = home / "config"
    logs = home / "logs"
    state = home / "state"

    monkeypatch.setenv("WHIZZARD_HOME", str(home))
    from whizzard import config as cfg
    from whizzard import harness_config as hc
    from whizzard import init_wizard as iw
    from whizzard import mounts as mn
    from whizzard import preset_config as pc

    monkeypatch.setattr(cfg, "WHIZZARD_HOME", home)
    monkeypatch.setattr(cfg, "CONFIG_DIR", config)
    monkeypatch.setattr(cfg, "LOGS_DIR", logs)
    monkeypatch.setattr(cfg, "STATE_DIR", state)
    monkeypatch.setattr(cfg, "PROFILES_FILE", config / "profiles.json")
    monkeypatch.setattr(mn, "MOUNTS_FILE", config / "mounts.json")
    monkeypatch.setattr(hc, "HARNESSES_FILE", config / "harnesses.json")
    monkeypatch.setattr(pc, "PRESETS_FILE", config / "presets.json")

    # init_wizard module captured these at import time; rebind explicitly.
    monkeypatch.setattr(iw, "CONFIG_DIR", config)
    monkeypatch.setattr(iw, "PROFILES_FILE", config / "profiles.json")
    monkeypatch.setattr(iw, "MOUNTS_FILE", config / "mounts.json")
    monkeypatch.setattr(iw, "HARNESSES_FILE", config / "harnesses.json")
    monkeypatch.setattr(iw, "PRESETS_FILE", config / "presets.json")
    monkeypatch.setattr(
        iw, "_CONFIG_FILES",
        (
            config / "profiles.json",
            config / "mounts.json",
            config / "harnesses.json",
            config / "presets.json",
        ),
    )

    # The wizard's run() creates these dirs, but tests that call
    # writer helpers directly need them pre-created.
    config.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    state.mkdir(parents=True, exist_ok=True)

    return home


# ---------- idempotency ----------


def test_init_refuses_when_config_already_exists(_isolated_whizzard_home: Path):
    """The wizard refuses to run if any of the four config files exist —
    so a first-time user can't accidentally clobber a working setup."""
    config = _isolated_whizzard_home / "config"
    config.mkdir(parents=True, exist_ok=True)
    (config / "profiles.json").write_text('{"existing": true}')

    result = runner.invoke(app, ["init", "--yes"])
    assert result.exit_code == 1
    assert "already exists" in result.output


def test_init_force_overrides_idempotency_check(
    _isolated_whizzard_home: Path, monkeypatch: pytest.MonkeyPatch
):
    """--force lets the wizard proceed even when prior config exists."""
    config = _isolated_whizzard_home / "config"
    config.mkdir(parents=True, exist_ok=True)
    (config / "profiles.json").write_text('{"existing": true}')

    # Stub docker so step 1 doesn't actually try to build anything.
    from whizzard import init_wizard as iw

    monkeypatch.setattr(iw, "docker_available", lambda: True)
    monkeypatch.setattr(iw, "_default_build_runner", lambda argv: 0)

    result = runner.invoke(app, ["init", "--yes", "--force"])
    # With --yes + --force, the welcome + step 1 should at least run
    # without raising at idempotency.
    assert "already exists" not in result.output


# ---------- step 1: image build (no docker) ----------


def test_init_exits_127_when_docker_missing(
    _isolated_whizzard_home: Path, monkeypatch: pytest.MonkeyPatch
):
    """Step 1's pre-flight surfaces the docker-not-found case clearly."""
    from whizzard import init_wizard as iw

    monkeypatch.setattr(iw, "docker_available", lambda: False)
    result = runner.invoke(app, ["init", "--yes"])
    assert result.exit_code == 127
    assert "docker not found" in result.output


# ---------- step 1: image build (build_runner mocked) ----------


def test_init_step_1_invokes_two_builds_in_order(
    _isolated_whizzard_home: Path, monkeypatch: pytest.MonkeyPatch
):
    """Step 1 silently chains base + Hermes image builds — the user sees
    one "Building sandbox..." line, the runner is invoked twice."""
    from whizzard import init_wizard as iw

    monkeypatch.setattr(iw, "docker_available", lambda: True)

    invocations: list[list[str]] = []

    def _fake_build(argv: list[str]) -> int:
        invocations.append(argv)
        return 0

    monkeypatch.setattr(iw, "_default_build_runner", _fake_build)

    result = runner.invoke(app, ["init", "--yes"])
    # Step 1 succeeds; later steps not yet implemented so the wizard
    # currently ends after step 1 with the welcome + step-1 output.
    assert "sandbox built" in result.output
    assert len(invocations) == 2

    # First build = base image; second = hermes image. Verify tag args.
    base_argv = invocations[0]
    hermes_argv = invocations[1]
    assert "whizzard-base:latest" in base_argv
    assert "whizzard-hermes:latest" in hermes_argv


def test_init_step_1_propagates_base_build_failure(
    _isolated_whizzard_home: Path, monkeypatch: pytest.MonkeyPatch
):
    """If the base build fails, the Hermes build is NOT attempted and
    the wizard exits with the docker exit code."""
    from whizzard import init_wizard as iw

    monkeypatch.setattr(iw, "docker_available", lambda: True)

    invocations: list[list[str]] = []

    def _fake_build(argv: list[str]) -> int:
        invocations.append(argv)
        return 13  # arbitrary non-zero

    monkeypatch.setattr(iw, "_default_build_runner", _fake_build)

    result = runner.invoke(app, ["init", "--yes"])
    assert result.exit_code == 13
    assert len(invocations) == 1, "Hermes build should not run if base fails"
    assert "docker build failed" in result.output


# ---------- writers (used by later steps; tested early so the
# Step-2/3/4 commits can rely on them) ----------


def test_write_default_profiles_emits_valid_json(_isolated_whizzard_home: Path):
    from whizzard import init_wizard as iw

    names = iw._write_default_profiles()
    assert "default" in names and "safe" in names
    assert iw.PROFILES_FILE.exists()
    import json

    payload = json.loads(iw.PROFILES_FILE.read_text())
    assert payload["schema_version"] == 1
    assert "profiles" in payload
    assert payload["profiles"]["default"]["network_enabled"] is True
    assert payload["profiles"]["default"]["duration_seconds"] is None  # unlimited


def test_write_default_harnesses_emits_valid_json(_isolated_whizzard_home: Path):
    from whizzard import init_wizard as iw

    count = iw._write_default_harnesses()
    assert count >= 1
    assert iw.HARNESSES_FILE.exists()
    import json

    payload = json.loads(iw.HARNESSES_FILE.read_text())
    assert payload["schema_version"] == 1
    assert "harnesses" in payload


# ---------- hermes detection ----------


def test_hermes_profile_detection_returns_path_when_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """When ~/.hermes/ exists, the detection helper returns its path."""
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    (fake_home / ".hermes").mkdir()

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    from whizzard import init_wizard as iw

    detected = iw._hermes_profile_already_exists()
    assert detected == fake_home / ".hermes"


def test_hermes_profile_detection_returns_none_when_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """When ~/.hermes/ does not exist, returns None (→ Branch B)."""
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()  # ~/ exists but ~/.hermes/ doesn't

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    from whizzard import init_wizard as iw

    detected = iw._hermes_profile_already_exists()
    assert detected is None


# ---------- step 1b: Hermes profile setup ----------


def _stub_step_1_to_succeed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Helper: skip Step 1 so a test can focus on later steps."""
    from whizzard import init_wizard as iw

    monkeypatch.setattr(iw, "docker_available", lambda: True)
    monkeypatch.setattr(iw, "_default_build_runner", lambda argv: 0)


def test_init_step_1b_branch_a_clones_hermes_profile(
    _isolated_whizzard_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """When ~/.hermes/ exists, Branch A triggers and clones to ~/.hermes-whizz/."""
    _stub_step_1_to_succeed(monkeypatch)

    # Fake host with ~/.hermes/ present.
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    hermes = fake_home / ".hermes"
    hermes.mkdir()

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    from whizzard import init_wizard as iw

    # Mock the cloner so no real Hermes adapter primitive runs.
    cloner_calls: list[tuple[str, Path]] = []

    def _fake_cloner(name: str, source: Path) -> Path:
        cloner_calls.append((name, source))
        return fake_home / f".hermes-{name}"

    monkeypatch.setattr(iw, "_default_hermes_cloner", _fake_cloner)

    result = runner.invoke(app, ["init", "--yes"])
    assert result.exit_code == 0
    assert "Hermes detected" in result.output
    assert "✓" in result.output and "whizz" in result.output
    assert len(cloner_calls) == 1
    assert cloner_calls[0][0] == "whizz"
    assert cloner_calls[0][1] == hermes


def test_init_step_1b_branch_b_shows_install_instructions(
    _isolated_whizzard_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """When ~/.hermes/ is absent, Branch B shows the install link
    and the wizard continues without cloning."""
    _stub_step_1_to_succeed(monkeypatch)

    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()  # no ~/.hermes/

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    from whizzard import init_wizard as iw

    def _cloner_should_not_run(name: str, source: Path) -> Path:
        raise AssertionError("cloner should not run in Branch B")

    monkeypatch.setattr(iw, "_default_hermes_cloner", _cloner_should_not_run)

    result = runner.invoke(app, ["init", "--yes"])
    assert result.exit_code == 0
    assert "Hermes is not yet installed" in result.output
    assert "github.com/NousResearch/hermes-agent" in result.output
    assert "whiz hermes profile create whizz" in result.output


def test_init_step_1b_clone_failure_does_not_abort_wizard(
    _isolated_whizzard_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """If the clone raises, the wizard logs the error and continues —
    the user can retry the profile clone later."""
    _stub_step_1_to_succeed(monkeypatch)

    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    (fake_home / ".hermes").mkdir()

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    from whizzard import init_wizard as iw

    def _failing_cloner(name: str, source: Path) -> Path:
        raise RuntimeError("simulated clone failure")

    monkeypatch.setattr(iw, "_default_hermes_cloner", _failing_cloner)

    result = runner.invoke(app, ["init", "--yes"])
    # The wizard should NOT crash with the cloner's exception.
    assert result.exit_code == 0
    assert "profile clone failed" in result.output
    assert "simulated clone failure" in result.output


# ---------- step 2: profiles ----------


def _stub_through_step_1b(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Path:
    """Helper: skip steps 1 + 1b (force Branch B so no Hermes cloner runs)."""
    _stub_step_1_to_succeed(monkeypatch)
    fake_home = tmp_path / "fake-home-step2"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    return fake_home


def test_init_step_2_yes_writes_all_five_default_profiles(
    _isolated_whizzard_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """In --yes mode, Step 2 takes option 1 (use all 5 defaults)."""
    _stub_through_step_1b(monkeypatch, tmp_path)

    result = runner.invoke(app, ["init", "--yes"])
    assert result.exit_code == 0
    assert "wrote" in result.output and "profiles.json" in result.output

    from whizzard import init_wizard as iw

    payload = json.loads(iw.PROFILES_FILE.read_text())
    names = set(payload["profiles"].keys())
    assert names == {"default", "safe", "build", "power", "quarantine"}


def test_init_step_2_minimal_writes_safe_and_default(
    _isolated_whizzard_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """Choice 2 (minimal) writes only safe + default."""
    _stub_through_step_1b(monkeypatch, tmp_path)

    user_input = "\n".join([
        "",        # welcome Press Enter
        "",        # step 1 Press Enter
        "",        # step 1b (Branch B) Press Enter
        "2",       # step 2: minimal subset
        "2",       # step 3: no folders
    ]) + "\n"
    result = runner.invoke(app, ["init"], input=user_input)
    assert result.exit_code == 0

    from whizzard import init_wizard as iw

    payload = json.loads(iw.PROFILES_FILE.read_text())
    names = set(payload["profiles"].keys())
    assert names == {"safe", "default"}


def test_init_step_3_yes_writes_empty_mount_registry(
    _isolated_whizzard_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """--yes mode skips the add-folder loop and writes an empty registry."""
    _stub_through_step_1b(monkeypatch, tmp_path)

    result = runner.invoke(app, ["init", "--yes"])
    assert result.exit_code == 0

    from whizzard import init_wizard as iw

    payload = json.loads(iw.MOUNTS_FILE.read_text())
    assert payload["mounts"] == {}


def test_init_step_3_interactive_adds_one_folder(
    _isolated_whizzard_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """Interactive mode collects path/name/description/mode and saves."""
    _stub_through_step_1b(monkeypatch, tmp_path)

    user_input = "\n".join([
        "",                      # welcome Press Enter
        "",                      # step 1 Press Enter
        "",                      # step 1b (Branch B) Press Enter
        "1",                     # step 2: all 5 defaults
        "1",                     # step 3: yes, add a folder
        "~/code/scratch",        # path
        "scratch",               # name
        "scratch projects",      # description
        "2",                     # mode: read-write
        "2",                     # add another? No
    ]) + "\n"

    result = runner.invoke(app, ["init"], input=user_input)
    assert result.exit_code == 0

    from whizzard import init_wizard as iw

    payload = json.loads(iw.MOUNTS_FILE.read_text())
    assert "scratch" in payload["mounts"]
    mount = payload["mounts"]["scratch"]
    assert mount["host_path"] == "~/code/scratch"
    assert mount["default_mode"] == "rw"
    assert mount["description"] == "scratch projects"


def test_init_step_2_custom_subflow_creates_one_profile(
    _isolated_whizzard_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """Choice 3 (custom) walks the user through a single profile and saves."""
    _stub_through_step_1b(monkeypatch, tmp_path)

    # Scripted user input: welcome-Enter, step1-Enter, step1b-Enter (Branch B),
    # step2-choose-3, custom-profile sub-flow, then step 3 "no folders".
    user_input = "\n".join([
        "",          # welcome Press Enter
        "",          # step 1 Press Enter
        "",          # step 1b (Branch B) Press Enter
        "3",         # step 2: define your own
        "work",      # profile name
        "1",         # internet: Yes
        "2",         # time limit: Yes
        "2",         # how many hours: 2
        "2",         # idle limit: Yes
        "30",        # idle minutes: 30
        "my work",   # description
        "1",         # save? Yes
        "2",         # add another profile? No
        "2",         # step 3: add a folder? No
    ]) + "\n"

    result = runner.invoke(app, ["init"], input=user_input)
    assert result.exit_code == 0

    from whizzard import init_wizard as iw

    payload = json.loads(iw.PROFILES_FILE.read_text())
    assert "work" in payload["profiles"]
    work = payload["profiles"]["work"]
    assert work["network_enabled"] is True
    assert work["duration_seconds"] == 7200  # 2 hours
    assert work["idle_timeout_seconds"] == 1800  # 30 min
    assert work["description"] == "my work"
