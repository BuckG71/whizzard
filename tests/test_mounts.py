"""Stage 2: mount registry tests."""

import json
from pathlib import Path

import pytest

from whizzard.mounts import (
    CONTAINER_MOUNT_ROOT,
    Mount,
    MountRegistryError,
    default_mounts,
    load_mounts,
    resolve_mount_spec,
)


@pytest.fixture
def mounts_file(tmp_path: Path) -> Path:
    """Build a mounts.json with realistic entries pointing at tmp_path."""
    target_dir = tmp_path / "alpha"
    target_dir.mkdir()
    research_dir = tmp_path / "research"
    research_dir.mkdir()
    file_path = tmp_path / "mounts.json"
    file_path.write_text(json.dumps({
        "schema_version": 1,
        "mounts": {
            "project-alpha": {
                "host_path": str(target_dir),
                "default_mode": "rw",
                "description": "alpha workspace",
            },
            "research-notes": {
                "host_path": str(research_dir),
                "default_mode": "ro",
                "description": "read-only notes",
            },
        },
    }))
    return file_path


def test_load_returns_bundled_defaults_when_file_absent(tmp_path: Path):
    """Stage 10 / D-157-pattern: mounts.py now has bundled defaults for fresh
    installs (claude-projects, ai-sandbox). load_mounts returns them when no
    user file exists, matching the profiles.py pattern."""
    registry = load_mounts(tmp_path / "missing.json")
    assert set(registry.keys()) == {"claude-projects", "ai-sandbox"}
    assert registry["claude-projects"].default_mode == "rw"
    assert registry["ai-sandbox"].default_mode == "rw"


def test_default_mounts_returns_bundled_set():
    registry = default_mounts()
    assert set(registry.keys()) == {"claude-projects", "ai-sandbox"}


def test_default_mounts_returns_fresh_dict():
    a = default_mounts()
    b = default_mounts()
    assert a == b
    assert a is not b


def test_load_parses_well_formed_registry(mounts_file: Path):
    registry = load_mounts(mounts_file)
    assert set(registry.keys()) == {"project-alpha", "research-notes"}
    assert registry["project-alpha"].default_mode == "rw"
    assert registry["research-notes"].default_mode == "ro"


def test_load_rejects_invalid_json(tmp_path: Path):
    bad = tmp_path / "mounts.json"
    bad.write_text("{this is not json")
    with pytest.raises(MountRegistryError):
        load_mounts(bad)


def test_load_rejects_missing_host_path(tmp_path: Path):
    bad = tmp_path / "mounts.json"
    bad.write_text(json.dumps({
        "mounts": {"oops": {"default_mode": "ro"}}
    }))
    with pytest.raises(MountRegistryError, match="missing host_path"):
        load_mounts(bad)


def test_load_rejects_invalid_default_mode(tmp_path: Path):
    bad = tmp_path / "mounts.json"
    bad.write_text(json.dumps({
        "mounts": {"x": {"host_path": "/tmp", "default_mode": "rwx"}}
    }))
    with pytest.raises(MountRegistryError, match="default_mode"):
        load_mounts(bad)


def test_resolve_uses_default_mode_when_none_specified(mounts_file: Path):
    registry = load_mounts(mounts_file)
    mount, mode = resolve_mount_spec("project-alpha", registry)
    assert mount.name == "project-alpha"
    assert mode == "rw"


def test_resolve_explicit_mode_overrides_default_when_compatible(mounts_file: Path):
    registry = load_mounts(mounts_file)
    mount, mode = resolve_mount_spec("project-alpha:ro", registry)
    assert mode == "ro"


def test_resolve_caps_ro_default_against_rw_request(mounts_file: Path):
    registry = load_mounts(mounts_file)
    with pytest.raises(MountRegistryError, match="cannot request 'rw'"):
        resolve_mount_spec("research-notes:rw", registry)


def test_resolve_unknown_mount_raises(mounts_file: Path):
    registry = load_mounts(mounts_file)
    with pytest.raises(MountRegistryError, match="unknown mount"):
        resolve_mount_spec("nope", registry)


def test_resolve_invalid_mode_raises(mounts_file: Path):
    registry = load_mounts(mounts_file)
    with pytest.raises(MountRegistryError, match="must be 'ro' or 'rw'"):
        resolve_mount_spec("project-alpha:weird", registry)


def test_container_path_is_under_mount_root():
    m = Mount(name="x", host_path=Path("/tmp"), default_mode="ro")
    assert m.container_path() == f"{CONTAINER_MOUNT_ROOT}/x"


def test_docker_volume_arg_uses_effective_mode():
    m = Mount(name="alpha", host_path=Path("/host/alpha"), default_mode="rw")
    assert m.docker_volume_arg() == "/host/alpha:/mounts/alpha:rw"
    assert m.docker_volume_arg(mode="ro") == "/host/alpha:/mounts/alpha:ro"
