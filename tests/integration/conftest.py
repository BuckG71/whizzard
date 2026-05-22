"""Fixtures for the integration tier.

Integration tests require real Docker on the host. They are deselected from
the default `pytest` run via the `-m 'not integration'` addopts in
`pyproject.toml`; run them explicitly with `pytest -m integration` or
`make integration`. The fixtures here handle:

- Skipping cleanly when Docker isn't available (so a contributor without
  Docker installed doesn't see hard failures).
- Building the `whizzard-base:latest` image once per test session if it
  isn't already present.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
WHIZZARD_BASE_IMAGE = "whizzard-base:latest"


def _docker_available() -> bool:
    """True iff `docker info` works (daemon reachable, not just binary on PATH)."""
    if shutil.which("docker") is None:
        return False
    result = subprocess.run(
        ["docker", "info"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def _image_present(image: str) -> bool:
    result = subprocess.run(
        ["docker", "image", "inspect", image],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


@pytest.fixture(scope="session", autouse=True)
def _require_docker() -> None:
    """Skip the whole integration tier when Docker isn't available."""
    if not _docker_available():
        pytest.skip("docker daemon not reachable — skipping integration tier", allow_module_level=True)


@pytest.fixture(scope="session")
def whizzard_base_image() -> str:
    """Ensure `whizzard-base:latest` exists; build it from docker/Dockerfile
    if not. Returns the image tag for use in tests."""
    if _image_present(WHIZZARD_BASE_IMAGE):
        return WHIZZARD_BASE_IMAGE

    dockerfile = REPO_ROOT / "docker" / "Dockerfile"
    if not dockerfile.exists():
        pytest.skip(f"Dockerfile not found at {dockerfile}", allow_module_level=True)

    result = subprocess.run(
        [
            "docker", "build",
            "-t", WHIZZARD_BASE_IMAGE,
            "-f", str(dockerfile),
            str(dockerfile.parent),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(
            f"failed to build {WHIZZARD_BASE_IMAGE}:\n"
            f"stdout: {result.stdout[-2000:]}\n"
            f"stderr: {result.stderr[-2000:]}"
        )
    return WHIZZARD_BASE_IMAGE


@pytest.fixture
def run_in_cell(whizzard_base_image: str):
    """Launch a real contained cell and run a command in it non-interactively.

    Returns a callable `run(cmd, *, profile=..., timeout=...)` that goes
    through the real `build_run_argv` launch path — so the containment flags
    under test are the actual ones OIQ applies — strips `-it` (pytest has no
    TTY), runs `cmd` in place of the harness start-command, and returns the
    `CompletedProcess`. Shared harness for the real-Docker smoke + adversarial
    probe tests.
    """
    from whizzard.config import get_profile
    from whizzard.docker_cmd import build_run_argv

    def _run(cmd: list[str], *, profile: str = "default", timeout: int = 60):
        argv = build_run_argv(get_profile(profile), image=whizzard_base_image)
        # build_run_argv's argv tail is [image, *start_command]. Find the
        # image, drop `-it`, and replace the start-command tail with `cmd`.
        image_idx = next(
            i for i, a in enumerate(argv) if a == whizzard_base_image
        )
        launch = [a for a in argv[:image_idx] if a != "-it"]
        launch.append(whizzard_base_image)
        launch.extend(cmd)
        return subprocess.run(launch, capture_output=True, text=True, timeout=timeout)

    return _run
