"""Stage 19 / M3.5 — `whiz init` end-to-end smoke against real Docker.

Closes the integration coverage gap left by M3: unit tests mock both
the docker-build runner and the Hermes cloner, so a regression in the
real subprocess wiring would slip past `make check`. This smoke runs
``whiz init --yes --force`` as a subprocess against a real Docker
daemon, with isolated ``HOME`` and ``WHIZZARD_HOME``, and asserts:

  - The four config files are written and parse as JSON
  - whizzard-base:latest and whizzard-hermes:latest both exist after
    the run (built or rebuilt as needed)
  - Branch B is exercised (the smoke uses a HOME with no ~/.hermes/
    so it doesn't depend on the maintainer's host Hermes state)

Gated on the integration marker (`pytest -m integration`); skipped
when no Docker daemon is reachable.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def _image_present(image: str) -> bool:
    result = subprocess.run(
        ["docker", "image", "inspect", image],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def test_whiz_init_yes_force_end_to_end(tmp_path: Path) -> None:
    """`whiz init --yes --force` runs cleanly against real Docker and
    produces a valid first-time-user config in an isolated HOME."""
    isolated_home = tmp_path / "fake-home"
    isolated_home.mkdir()
    whizzard_home = isolated_home / ".whizzard"

    # Run with HOME pointed at the isolated dir (so no real ~/.hermes/
    # check influences which branch the wizard takes — Branch B) and
    # WHIZZARD_HOME isolated so we don't touch the maintainer's config.
    env = {
        "PATH": __import__("os").environ.get("PATH", ""),
        "HOME": str(isolated_home),
        "WHIZZARD_HOME": str(whizzard_home),
    }

    result = subprocess.run(
        ["whiz", "init", "--yes", "--force"],
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )

    assert result.returncode == 0, (
        f"`whiz init --yes --force` failed (exit {result.returncode}):\n"
        f"stdout: {result.stdout[-2000:]}\n"
        f"stderr: {result.stderr[-2000:]}"
    )

    # Verify the four config files exist and parse.
    config_dir = whizzard_home / "config"
    for name in ("profiles.json", "mounts.json", "harnesses.json", "presets.json"):
        path = config_dir / name
        assert path.exists(), f"{name} not written by wizard"
        try:
            parsed = json.loads(path.read_text())
        except json.JSONDecodeError as e:
            pytest.fail(f"{name} is not valid JSON: {e}")
        assert parsed.get("schema_version") == 1, f"{name} missing schema_version"

    # Verify the bundled hermes preset landed with the expected wiring.
    presets = json.loads((config_dir / "presets.json").read_text())["presets"]
    assert "hermes" in presets
    assert presets["hermes"]["harness"] == "hermes-cell"
    assert presets["hermes"]["profile"] == "default"

    # Verify the customized harnesses entry points at ~/.hermes-whizz.
    harnesses = json.loads((config_dir / "harnesses.json").read_text())["harnesses"]
    assert "hermes-cell" in harnesses
    assert harnesses["hermes-cell"]["hermes_home"] == "~/.hermes-whizz"

    # Verify both images exist after the run (built or cache-hit).
    assert _image_present("whizzard-base:latest"), (
        "whizzard-base:latest not present after wizard run"
    )
    assert _image_present("whizzard-hermes:latest"), (
        "whizzard-hermes:latest not present after wizard run"
    )

    # Verify the wizard surfaced Branch B (no ~/.hermes/ in isolated HOME)
    # — the Done summary should mention that Hermes profile setup is pending.
    assert "Hermes is not yet installed" in result.stdout or \
           "not yet" in result.stdout, (
        "Branch B install-instructions not surfaced in --yes run"
    )
