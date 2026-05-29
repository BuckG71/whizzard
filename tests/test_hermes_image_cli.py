"""Stage 19 / M2: `whiz hermes image build` CLI tests."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from whizzard.cli import app

runner = CliRunner()


def _patch_docker_available(monkeypatch, value: bool = True) -> None:
    from whizzard.cli import hermes as cli_hermes

    monkeypatch.setattr(cli_hermes, "docker_available", lambda: value)


def test_hermes_image_build_exits_127_when_docker_missing(monkeypatch):
    """Same docker-not-found preflight pattern as `whiz image build` (F-H-02)."""
    from whizzard.cli import hermes as cli_hermes

    _patch_docker_available(monkeypatch, False)
    # Sentinel that fails the test if subprocess.run is reached.
    monkeypatch.setattr(
        cli_hermes.subprocess, "run",
        lambda *a, **kw: (_ for _ in ()).throw(
            AssertionError("subprocess.run should not be reached")
        ),
    )

    result = runner.invoke(app, ["hermes", "image", "build"])
    assert result.exit_code == 127
    assert "docker not found" in result.output


def test_hermes_image_build_exits_2_when_dockerfile_missing(
    monkeypatch, tmp_path: Path
):
    """If the bundled Dockerfile.hermes can't be located, fail with a
    clear message rather than handing the bad path to docker."""
    from whizzard.cli import hermes as cli_hermes

    _patch_docker_available(monkeypatch, True)
    monkeypatch.setattr(
        cli_hermes, "_hermes_dockerfile_path", lambda: tmp_path / "nope.hermes"
    )
    monkeypatch.setattr(
        cli_hermes.subprocess, "run",
        lambda *a, **kw: (_ for _ in ()).throw(
            AssertionError("subprocess.run should not be reached")
        ),
    )

    result = runner.invoke(app, ["hermes", "image", "build"])
    assert result.exit_code == 2
    assert "Dockerfile.hermes not found" in result.output


def test_hermes_image_build_invokes_docker_build_with_correct_argv(
    monkeypatch, tmp_path: Path
):
    """Verifies the docker invocation: tag, dockerfile path, and build
    context all reach the subprocess call."""
    from whizzard.cli import hermes as cli_hermes

    fake_dockerfile = tmp_path / "Dockerfile.hermes"
    fake_dockerfile.write_text("FROM whizzard-base:latest\n")
    fake_context = tmp_path

    captured: dict = {}

    class _FakeProc:
        returncode = 0

    def _fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["env"] = kwargs.get("env")
        return _FakeProc()

    _patch_docker_available(monkeypatch, True)
    monkeypatch.setattr(cli_hermes, "_hermes_dockerfile_path", lambda: fake_dockerfile)
    monkeypatch.setattr(cli_hermes, "_hermes_build_context", lambda: fake_context)
    monkeypatch.setattr(cli_hermes.subprocess, "run", _fake_run)

    result = runner.invoke(app, ["hermes", "image", "build"])
    assert result.exit_code == 0

    argv = captured["argv"]
    assert argv[0] == "docker"
    assert argv[1] == "build"
    assert "-t" in argv and "whizzard-hermes:latest" in argv
    assert "-f" in argv
    f_idx = argv.index("-f")
    assert argv[f_idx + 1] == str(fake_dockerfile)
    assert argv[-1] == str(fake_context)


def test_hermes_image_build_honors_custom_image_tag(monkeypatch, tmp_path: Path):
    """--image overrides the default WHIZZARD_HERMES_IMAGE."""
    from whizzard.cli import hermes as cli_hermes

    fake_dockerfile = tmp_path / "Dockerfile.hermes"
    fake_dockerfile.write_text("FROM whizzard-base:latest\n")

    captured: dict = {}

    class _FakeProc:
        returncode = 0

    def _fake_run(argv, **kwargs):
        captured["argv"] = argv
        return _FakeProc()

    _patch_docker_available(monkeypatch, True)
    monkeypatch.setattr(cli_hermes, "_hermes_dockerfile_path", lambda: fake_dockerfile)
    monkeypatch.setattr(cli_hermes, "_hermes_build_context", lambda: tmp_path)
    monkeypatch.setattr(cli_hermes.subprocess, "run", _fake_run)

    result = runner.invoke(
        app, ["hermes", "image", "build", "--image", "my-hermes:dev"]
    )
    assert result.exit_code == 0
    assert "my-hermes:dev" in captured["argv"]


def test_hermes_image_build_returns_docker_exit_code(monkeypatch, tmp_path: Path):
    """Non-zero exit codes from docker propagate up cleanly."""
    from whizzard.cli import hermes as cli_hermes

    fake_dockerfile = tmp_path / "Dockerfile.hermes"
    fake_dockerfile.write_text("FROM whizzard-base:latest\n")

    class _FakeProc:
        returncode = 17

    _patch_docker_available(monkeypatch, True)
    monkeypatch.setattr(cli_hermes, "_hermes_dockerfile_path", lambda: fake_dockerfile)
    monkeypatch.setattr(cli_hermes, "_hermes_build_context", lambda: tmp_path)
    monkeypatch.setattr(cli_hermes.subprocess, "run", lambda *a, **kw: _FakeProc())

    result = runner.invoke(app, ["hermes", "image", "build"])
    assert result.exit_code == 17


def test_hermes_dockerfile_path_resolves_to_bundled_location():
    """Smoke: the bundled Dockerfile.hermes is actually accessible via the
    package-data lookup path, mirroring the test_image_cli check for the
    base Dockerfile."""
    from whizzard.cli.hermes import _hermes_dockerfile_path

    path = _hermes_dockerfile_path()
    assert path.exists(), f"bundled Dockerfile.hermes not found at {path}"
    assert "_dockerfiles" in str(path)


def test_hermes_build_context_is_parent_of_whizzard_package():
    """The build context must be the directory that contains the
    `whizzard/` package — that's how the Dockerfile.hermes's
    `COPY whizzard/mcp_server.py ...` line resolves at build time."""
    import whizzard
    from whizzard.cli.hermes import _hermes_build_context

    context = _hermes_build_context()
    assert (context / "whizzard").is_dir()
    assert (context / "whizzard" / "mcp_server.py").exists()
    assert context == Path(whizzard.__file__).resolve().parent.parent
