"""Packaging guards: every build resource `whiz init` needs at runtime must be
declared in pyproject package-data, or a `pip install` wheel ships without it
and the affected image build fails. The bar-C broker (Dockerfile.broker +
broker/proxy.py) was exactly this miss — shipped in-tree but not packaged, so a
wheel install couldn't build the broker and mediated/hybrid modes broke."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_DOCKERFILES = _REPO / "whizzard" / "_dockerfiles"


def _packaged_dockerfile_resources() -> set[str]:
    data = tomllib.loads((_REPO / "pyproject.toml").read_text())
    return set(
        data["tool"]["setuptools"]["package-data"]["whizzard._dockerfiles"]
    )


def test_broker_build_assets_are_packaged():
    listed = _packaged_dockerfile_resources()
    assert "Dockerfile.broker" in listed
    assert "broker/proxy.py" in listed


def test_every_dockerfile_resource_is_packaged():
    """Regression guard for the whole class: any Dockerfile* on disk must be in
    package-data (catches a new Dockerfile added without updating pyproject)."""
    listed = _packaged_dockerfile_resources()
    for f in sorted(_DOCKERFILES.glob("Dockerfile*")):
        assert f.name in listed, (
            f"{f.name} exists in whizzard/_dockerfiles but is not in pyproject "
            f"package-data — a wheel install would ship without it"
        )


def test_packaged_resources_exist_on_disk():
    """Every declared resource must actually exist (no stale package-data)."""
    for rel in _packaged_dockerfile_resources():
        assert (_DOCKERFILES / rel).is_file(), f"packaged resource missing: {rel}"


def test_profiles_example_validates_and_is_secure_by_default():
    """The copy-paste profile template must load AND embody the secure default
    (network_mode present on `default`), not the old boolean-only shape."""
    from whizzard.config import _parse_profile

    prof = json.loads((_REPO / "config" / "profiles.json.example").read_text())
    for name, spec in prof["profiles"].items():
        _parse_profile(name, spec)  # raises on invalid
    assert prof["profiles"]["default"].get("network_mode") == "mediated"


def test_harnesses_example_validates_and_shows_model_credential():
    """The harness template must load through the real validator and show the
    current credential shape (model_credential), not the pre-mediation example."""
    from whizzard.harness_config import load_harnesses

    h = load_harnesses(_REPO / "config" / "harnesses.json.example")
    assert "model_credential" in h["hermes"]
    assert "hermes_home" in h["hermes"]
