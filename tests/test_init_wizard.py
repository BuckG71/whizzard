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

    monkeypatch.setattr(iw, "docker_daemon_status", lambda: ("ok", ""))
    monkeypatch.setattr(iw, "_default_build_runner", lambda argv: 0)
    # Isolate from the dev's real ~/.hermes: force Step 1b's Branch B so the
    # test exercises the --force idempotency override, not a real profile clone
    # (which would touch the host home and, if ~/.hermes-main exists, surface
    # "already exists" — unrelated to what this test asserts).
    monkeypatch.setattr(iw, "_hermes_profile_already_exists", lambda: None)

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

    monkeypatch.setattr(iw, "docker_daemon_status", lambda: ("missing", ""))
    result = runner.invoke(app, ["init", "--yes"])
    assert result.exit_code == 127
    assert "docker not found" in result.output


def test_init_errors_when_docker_daemon_unreachable(
    _isolated_whizzard_home: Path, monkeypatch: pytest.MonkeyPatch
):
    """Docker installed but daemon down: the preflight must say so (not
    falsely claim 'Docker is running') and abort."""
    from whizzard import init_wizard as iw

    monkeypatch.setattr(iw, "docker_daemon_status", lambda: ("unreachable", ""))
    result = runner.invoke(app, ["init", "--yes"])
    assert result.exit_code == 1
    assert "not running" in result.output
    assert "Docker is running" not in result.output


def test_init_errors_on_windows_container_mode(
    _isolated_whizzard_home: Path, monkeypatch: pytest.MonkeyPatch
):
    """Daemon up but in Windows-container mode: our sandbox is a Linux
    container, so abort with the switch-to-Linux guidance."""
    from whizzard import init_wizard as iw

    monkeypatch.setattr(iw, "docker_daemon_status", lambda: ("windows_containers", ""))
    result = runner.invoke(app, ["init", "--yes"])
    assert result.exit_code == 1
    assert "Windows-container mode" in result.output


# ---------- step 1: image build (build_runner mocked) ----------


def test_init_step_1_invokes_two_builds_in_order(
    _isolated_whizzard_home: Path, monkeypatch: pytest.MonkeyPatch
):
    """Step 1 silently chains base + Hermes image builds — the user sees
    one "Building sandbox..." line, the runner is invoked twice."""
    from whizzard import init_wizard as iw

    monkeypatch.setattr(iw, "docker_daemon_status", lambda: ("ok", ""))

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

    monkeypatch.setattr(iw, "docker_daemon_status", lambda: ("ok", ""))

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

    monkeypatch.setattr(iw, "docker_daemon_status", lambda: ("ok", ""))
    monkeypatch.setattr(iw, "_default_build_runner", lambda argv: 0)


def test_init_step_1b_branch_a_clones_hermes_profile(
    _isolated_whizzard_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """When ~/.hermes/ exists, Branch A triggers and clones to ~/.hermes-main/."""
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
    assert "✓" in result.output and "main" in result.output
    assert len(cloner_calls) == 1
    assert cloner_calls[0][0] == "main"
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
    # Collapse Rich's line wraps so multi-word phrases match regardless of
    # the rendered console width.
    flat = " ".join(result.output.split())
    # Necessity-first framing + honest "not set up yet" state (D-182).
    assert "needs at least one installed and configured" in flat
    assert "isn't set up on this computer yet" in flat
    # Whizzard does not install the harness — it points at Nous' instructions
    # and the profile-create step.
    assert "github.com/NousResearch/hermes-agent" in flat
    assert "whiz hermes profile create main" in flat


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


def test_default_hermes_cloner_clones_host_default_via_name(
    _isolated_whizzard_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """Regression (Windows fresh-install 2026-06-04): the wizard's auto-clone
    must clone the detected host profile (~/.hermes) via the reserved NAME
    'default', not by passing the full path as a profile name — which built a
    garbled ~/.hermes-<path> source and failed with 'clone source not found'.
    Exercises the REAL _default_hermes_cloner (the failure-path test above
    substitutes a fake cloner, so it never caught this)."""
    fake_home = tmp_path / "home"
    (fake_home / ".hermes").mkdir(parents=True)
    (fake_home / ".hermes" / "config.yaml").write_text("model: test\n")
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    from whizzard import init_wizard as iw

    path = iw._default_hermes_cloner("main", fake_home / ".hermes")
    assert path == fake_home / ".hermes-main"
    # The host config came across (auth.json/.env would be excluded per D-80).
    assert (fake_home / ".hermes-main" / "config.yaml").read_text() == "model: test\n"


# ---------- step 2: profiles ----------


def _stub_through_step_1b(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Path:
    """Helper: skip steps 1 + 1b (force Branch B so no Hermes cloner runs)."""
    _stub_step_1_to_succeed(monkeypatch)
    fake_home = tmp_path / "fake-home-step2"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    # Isolate ~ expansion too: Path.expanduser() reads $HOME/$USERPROFILE, not
    # the patched Path.home — so the wizard's mount dir-creation stays in tmp.
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))
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
        "1",       # step 4: bundled hermes preset
        "",        # step 5 Press Enter
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
    fake_home = _stub_through_step_1b(monkeypatch, tmp_path)

    user_input = "\n".join([
        "",                      # welcome Press Enter
        "",                      # step 1 Press Enter
        "",                      # step 1b (Branch B) Press Enter
        "1",                     # step 2: all 5 defaults
        "1",                     # step 3: yes, add a folder
        "~/code/scratch",        # path
        "1",                     # folder doesn't exist → create it
        "scratch",               # name
        "scratch projects",      # description
        "2",                     # mode: read-write
        "2",                     # add another folder? No
        "1",                     # step 4: bundled hermes preset
        "2",                     # attach scratch? No
        "",                      # step 5 Press Enter
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
    # 5c: the missing folder was created on disk after the "create it" prompt.
    assert (fake_home / "code" / "scratch").is_dir()


def test_init_step_3_rejects_hard_blocked_path_then_recovers(
    _isolated_whizzard_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """5c: a hard-blocked path (filesystem root) is rejected in the wizard,
    and the user can re-enter a valid path without restarting."""
    _stub_through_step_1b(monkeypatch, tmp_path)
    valid = tmp_path / "okdir"
    valid.mkdir()                          # exists → no create prompt

    user_input = "\n".join([
        "", "", "",            # welcome, step 1, step 1b
        "1",                   # step 2: all 5 defaults
        "1",                   # step 3: yes, add a folder
        "/",                   # hard-blocked (exact) → rejected, re-prompt path
        str(valid),            # valid existing path
        "okdir",               # name
        "",                    # description
        "1",                   # mode: read-only
        "2",                   # add another folder? No
        "1",                   # step 4: bundled hermes
        "2",                   # attach okdir? No
        "",                    # step 5 Press Enter
    ]) + "\n"

    result = runner.invoke(app, ["init"], input=user_input)
    assert result.exit_code == 0
    assert "hard-blocked" in result.output

    from whizzard import init_wizard as iw

    payload = json.loads(iw.MOUNTS_FILE.read_text())
    # Only the valid folder registered; the blocked root never made it in.
    assert list(payload["mounts"].keys()) == ["okdir"]


def test_init_step_3_pick_uses_folder_dialog(
    _isolated_whizzard_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """Typing 'pick' at the mount-path prompt opens the native folder dialog
    and registers whatever it returns (dialog mocked — no GUI in tests)."""
    fake_home = _stub_through_step_1b(monkeypatch, tmp_path)
    picked = fake_home / "picked"
    picked.mkdir()

    from whizzard import init_wizard as iw

    monkeypatch.setattr(iw, "pick_directory", lambda prompt="": str(picked))

    user_input = "\n".join([
        "", "", "",            # welcome, step 1, step 1b
        "1",                   # step 2: all 5 defaults
        "1",                   # step 3: yes, add a folder
        "pick",                # path → opens the (mocked) dialog
        "pickedmount",         # name
        "",                    # description
        "1",                   # mode: read-only
        "2",                   # add another folder? No
        "1",                   # step 4: bundled hermes
        "2",                   # attach pickedmount? No
        "",                    # step 5 Press Enter
    ]) + "\n"

    result = runner.invoke(app, ["init"], input=user_input)
    assert result.exit_code == 0, result.output
    assert "picked:" in result.output  # confirmation line
    payload = json.loads(iw.MOUNTS_FILE.read_text())
    assert "pickedmount" in payload["mounts"]


# ---------- step 4 + 5 + done ----------


def test_init_yes_mode_full_flow_writes_all_four_config_files(
    _isolated_whizzard_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """End-to-end --yes run produces a valid first-time-user config."""
    _stub_through_step_1b(monkeypatch, tmp_path)

    result = runner.invoke(app, ["init", "--yes"])
    assert result.exit_code == 0
    assert "Setup complete" in result.output

    from whizzard import init_wizard as iw

    assert iw.PROFILES_FILE.exists()
    assert iw.MOUNTS_FILE.exists()
    assert iw.HARNESSES_FILE.exists()
    assert iw.PRESETS_FILE.exists()

    presets = json.loads(iw.PRESETS_FILE.read_text())["presets"]
    assert "hermes" in presets
    assert presets["hermes"]["harness"] == "hermes-cell"
    assert presets["hermes"]["profile"] == "default"
    # No mounts registered in --yes mode, so the preset has no folders.
    assert presets["hermes"]["mounts"] == []

    harnesses = json.loads(iw.HARNESSES_FILE.read_text())["harnesses"]
    assert "hermes-cell" in harnesses
    assert harnesses["hermes-cell"]["hermes_home"] == "~/.hermes-main"
    # D-181: the wizard-written default is interactive `hermes`, not gateway —
    # a fresh `whiz r hermes` should drop into a chat, not an idle gateway.
    assert harnesses["hermes-cell"]["start_command"] == "hermes"


def test_init_step_4_attaches_registered_mount_in_full_interactive(
    _isolated_whizzard_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """Full canonical trajectory: user adds one mount, attaches it to
    the bundled hermes preset."""
    _stub_through_step_1b(monkeypatch, tmp_path)

    user_input = "\n".join([
        "",                      # welcome
        "",                      # step 1
        "",                      # step 1b (Branch B)
        "1",                     # step 2: all 5
        "1",                     # step 3: yes add folder
        "~/code/scratch",        # path
        "1",                     # folder doesn't exist → create it
        "scratch",               # name
        "scratch projects",      # description
        "2",                     # mode: rw
        "2",                     # add another? No
        "1",                     # step 4: bundled hermes
        "1",                     # attach scratch? Yes
        "",                      # step 5 Press Enter
    ]) + "\n"
    result = runner.invoke(app, ["init"], input=user_input)
    assert result.exit_code == 0

    from whizzard import init_wizard as iw

    presets = json.loads(iw.PRESETS_FILE.read_text())["presets"]
    assert "hermes" in presets
    assert presets["hermes"]["mounts"] == ["scratch"]
    assert "scratch attached" in result.output or "scratch" in result.output


def test_init_step_4_skip_writes_empty_presets(
    _isolated_whizzard_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """Step 4 choice 3 (skip) writes an empty presets.json."""
    _stub_through_step_1b(monkeypatch, tmp_path)

    user_input = "\n".join([
        "",        # welcome
        "",        # step 1
        "",        # step 1b
        "1",       # step 2: all 5
        "2",       # step 3: no folders
        "3",       # step 4: skip
        "",        # step 5
    ]) + "\n"
    result = runner.invoke(app, ["init"], input=user_input)
    assert result.exit_code == 0

    from whizzard import init_wizard as iw

    presets = json.loads(iw.PRESETS_FILE.read_text())["presets"]
    assert presets == {}


def test_init_done_summary_mentions_branch_b_state(
    _isolated_whizzard_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """In Branch B (no ~/.hermes/), the Done summary surfaces that
    the user still needs to install Hermes + create a profile."""
    _stub_through_step_1b(monkeypatch, tmp_path)

    result = runner.invoke(app, ["init", "--yes"])
    assert result.exit_code == 0
    assert "install Hermes" in result.output or "not yet" in result.output


def test_init_done_summary_warns_against_running_bare_hermes(
    _isolated_whizzard_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """The Done summary loudly warns that running `hermes` directly (outside
    Whizzard) is uncontained — so users always launch via `whiz r hermes`."""
    _stub_through_step_1b(monkeypatch, tmp_path)

    result = runner.invoke(app, ["init", "--yes"])
    assert result.exit_code == 0
    flat = " ".join(result.output.split())
    assert "UNCONTAINED" in flat
    assert "Always launch Hermes" in flat
    assert "whiz r hermes" in flat


def test_init_step_2_custom_subflow_creates_one_profile(
    _isolated_whizzard_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """Choice 3 (custom) walks the user through a single profile and saves."""
    _stub_through_step_1b(monkeypatch, tmp_path)

    # Scripted user input: full canonical interactive trajectory.
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
        "1",         # step 4: bundled hermes preset
        "",          # step 5 Press Enter
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


# ---------- H3 review-finding tests: atomic-write integrity in the wizard ----


def test_wizard_leaves_no_tmp_files_after_successful_run(
    _isolated_whizzard_home: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The wizard routes every config write through ``atomic_write_text``
    (H1). After a successful run, no ``.<name>.tmp`` siblings should
    remain — they're created during writes and renamed away on success."""
    from whizzard import init_wizard as iw

    monkeypatch.setattr(iw, "docker_daemon_status", lambda: ("ok", ""))
    monkeypatch.setattr(iw, "_default_build_runner", lambda argv: 0)

    result = runner.invoke(app, ["init", "--yes"])
    assert result.exit_code == 0

    config = _isolated_whizzard_home / "config"
    leftover_tmps = [p.name for p in config.iterdir() if p.name.startswith(".")]
    assert leftover_tmps == [], (
        f"atomic-write tmp files left behind in config dir: {leftover_tmps}"
    )


def test_wizard_crash_mid_config_write_leaves_original_intact(
    _isolated_whizzard_home: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the atomic helper raises mid-write, the destination file
    keeps its previous content (or stays absent). Belt for the helper-
    level test in test_atomic.py — proves the wizard's call sites
    actually go through the helper rather than direct write_text.

    Plant a sentinel ``profiles.json`` before the run, make every
    ``atomic_write_text`` call raise, confirm the sentinel survived."""
    from whizzard import init_wizard as iw

    config = _isolated_whizzard_home / "config"
    config.mkdir(parents=True, exist_ok=True)
    sentinel = '{"sentinel": "survived"}'
    iw.PROFILES_FILE.write_text(sentinel)

    monkeypatch.setattr(iw, "docker_daemon_status", lambda: ("ok", ""))
    monkeypatch.setattr(iw, "_default_build_runner", lambda argv: 0)

    def _exploding_atomic(path: Path, content: str) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(iw, "atomic_write_text", _exploding_atomic)

    # --force lets the wizard past the idempotency check; it'll then
    # crash on the first config write. The sentinel must survive.
    runner.invoke(app, ["init", "--yes", "--force"])
    assert iw.PROFILES_FILE.read_text() == sentinel


def test_wizard_eof_during_prompt_does_not_traceback(
    _isolated_whizzard_home: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Ctrl-D / closed stdin during an interactive prompt must not
    surface a raw Python traceback to the user — the wizard either
    exits cleanly or surfaces a user-readable error.

    Drive the interactive (non-`--yes`) flow with an input string
    that ends abruptly (no terminating newline for the last prompt).
    CliRunner's behavior with truncated input mirrors stdin closing."""
    from whizzard import init_wizard as iw

    monkeypatch.setattr(iw, "docker_daemon_status", lambda: ("ok", ""))
    monkeypatch.setattr(iw, "_default_build_runner", lambda argv: 0)

    # Empty input → first prompt hits EOFError immediately.
    result = runner.invoke(app, ["init"], input="")

    # Acceptable: any non-zero exit code OR clean exit, but NO Python
    # traceback noise in the user-facing output.
    assert "Traceback" not in result.output, (
        f"raw traceback surfaced to the user:\n{result.output}"
    )


def test_wizard_image_build_failure_leaves_no_partial_config(
    _isolated_whizzard_home: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the docker build subprocess fails in step 1, the wizard
    aborts before any config files land. Re-running after a fix is
    clean (no leftover config trips the idempotency refusal)."""
    from whizzard import init_wizard as iw

    monkeypatch.setattr(iw, "docker_daemon_status", lambda: ("ok", ""))
    # Base build fails immediately.
    monkeypatch.setattr(iw, "_default_build_runner", lambda argv: 1)

    result = runner.invoke(app, ["init", "--yes"])
    assert result.exit_code != 0

    config = _isolated_whizzard_home / "config"
    # No config files should have been written.
    written = [
        p.name for p in config.iterdir()
        if p.is_file() and not p.name.startswith(".")
    ] if config.exists() else []
    assert written == [], (
        f"failed image build still landed config files: {written}"
    )


# ---------- OS-aware guidance (windows-portability) ----------


def test_host_platform_detection(monkeypatch):
    from whizzard import init_wizard as iw
    monkeypatch.setattr(iw.platform, "system", lambda: "Windows")
    assert iw._host_platform() == "windows"
    monkeypatch.setattr(iw.platform, "system", lambda: "Darwin")
    assert iw._host_platform() == "macos"
    monkeypatch.setattr(iw.platform, "system", lambda: "Linux")
    assert iw._host_platform() == "linux"


def test_example_mount_path_is_os_idiomatic(monkeypatch):
    from whizzard import init_wizard as iw
    monkeypatch.setattr(iw, "_host_platform", lambda: "windows")
    assert "C:\\Users" in iw._example_mount_path()
    monkeypatch.setattr(iw, "_host_platform", lambda: "macos")
    assert iw._example_mount_path().startswith("~")


def test_docker_install_hint_windows_mentions_linux_container(monkeypatch):
    from whizzard import init_wizard as iw
    monkeypatch.setattr(iw, "_host_platform", lambda: "windows")
    hint = iw._docker_install_hint()
    assert "Windows" in hint and "Linux-container" in hint
    monkeypatch.setattr(iw, "_host_platform", lambda: "macos")
    assert "Mac" in iw._docker_install_hint()


def test_step_1_shows_windows_linux_container_note(
    _isolated_whizzard_home: Path, monkeypatch: pytest.MonkeyPatch
):
    """On Windows the Docker step warns about the Linux-container backend
    (the #1 silent-failure mode); on macOS it doesn't."""
    from whizzard import init_wizard as iw

    monkeypatch.setattr(iw, "docker_daemon_status", lambda: ("ok", ""))
    monkeypatch.setattr(iw, "_default_build_runner", lambda argv: 0)

    monkeypatch.setattr(iw, "_host_platform", lambda: "windows")
    result = runner.invoke(app, ["init", "--yes"])
    assert "Linux-container backend (WSL2)" in result.output

    monkeypatch.setattr(iw, "_host_platform", lambda: "macos")
    result = runner.invoke(app, ["init", "--yes"])
    assert "Linux-container backend (WSL2)" not in result.output
