"""Stage 6: safety policy tests."""

from pathlib import Path

import pytest

from whizzard.config import Profile
from whizzard.safety import (
    OverrideRecord,
    SafetyViolation,
    check_mount_path,
)


# Fixture profiles

def _profile(allow_broad_mount: bool, name: str = "test") -> Profile:
    return Profile(
        name=name,
        network_enabled=True,
        duration_seconds=600,
        allow_broad_mount=allow_broad_mount,
        description="",
    )


PROFILE_STRICT = _profile(allow_broad_mount=False, name="strict")
PROFILE_PERMISSIVE = _profile(allow_broad_mount=True, name="permissive")


# Existence and root-mount checks

def test_rejects_nonexistent_path(tmp_path: Path):
    with pytest.raises(SafetyViolation, match="does not exist"):
        check_mount_path(
            tmp_path / "definitely-not-here", PROFILE_PERMISSIVE, True
        )


def test_rejects_filesystem_root_exact_match():
    with pytest.raises(SafetyViolation, match="hard-blocked"):
        check_mount_path(Path("/"), PROFILE_PERMISSIVE, True)


def test_rejects_home_directory_exact_match():
    home = Path.home()
    with pytest.raises(SafetyViolation, match="hard-blocked"):
        check_mount_path(home, PROFILE_PERMISSIVE, True)


def test_allows_normal_subpath_inside_home(tmp_path: Path):
    """A regular path inside HOME should be allowed (no overrides needed)."""
    # tmp_path on macOS resolves to /private/var/folders/... — outside ~,
    # but the test still validates the "no overrides triggered" path.
    overrides = check_mount_path(tmp_path, PROFILE_STRICT, False)
    assert overrides == []


# Deep hard-block intersection (both directions)

def test_rejects_ssh_directory(tmp_path: Path, monkeypatch):
    fake_ssh = tmp_path / ".ssh"
    fake_ssh.mkdir()
    monkeypatch.setattr("whizzard.safety._DEEP_HARD_BLOCKS", [fake_ssh])
    with pytest.raises(SafetyViolation, match="hard-blocked"):
        check_mount_path(fake_ssh, PROFILE_PERMISSIVE, True)


def test_rejects_descendant_of_hard_block(tmp_path: Path, monkeypatch):
    fake_ssh = tmp_path / ".ssh"
    fake_ssh.mkdir()
    inside = fake_ssh / "keys"
    inside.mkdir()
    monkeypatch.setattr("whizzard.safety._DEEP_HARD_BLOCKS", [fake_ssh])
    with pytest.raises(SafetyViolation, match="hard-blocked"):
        check_mount_path(inside, PROFILE_PERMISSIVE, True)


def test_rejects_ancestor_that_contains_hard_block(tmp_path: Path, monkeypatch):
    """Mounting a parent that contains a hard-blocked path is still blocked.

    e.g., mounting / (parent of ~/.ssh) is rejected because it would
    expose the hard-blocked path.
    """
    fake_ssh = tmp_path / "user" / ".ssh"
    fake_ssh.mkdir(parents=True)
    monkeypatch.setattr("whizzard.safety._DEEP_HARD_BLOCKS", [fake_ssh])
    with pytest.raises(SafetyViolation, match="hard-blocked"):
        check_mount_path(tmp_path / "user", PROFILE_PERMISSIVE, True)


# Override-required: broad folders

def test_broad_folder_blocked_when_profile_disallows(tmp_path: Path, monkeypatch):
    fake_docs = tmp_path / "Documents"
    fake_docs.mkdir()
    monkeypatch.setattr("whizzard.safety._BROAD_FOLDERS", [fake_docs])
    with pytest.raises(SafetyViolation, match="profile 'strict' blocks"):
        check_mount_path(fake_docs, PROFILE_STRICT, True)


def test_broad_folder_blocked_when_flag_missing(tmp_path: Path, monkeypatch):
    fake_docs = tmp_path / "Documents"
    fake_docs.mkdir()
    monkeypatch.setattr("whizzard.safety._BROAD_FOLDERS", [fake_docs])
    with pytest.raises(SafetyViolation, match="--allow-broad-mount"):
        check_mount_path(fake_docs, PROFILE_PERMISSIVE, False)


def test_broad_folder_allowed_with_both_gates(tmp_path: Path, monkeypatch):
    fake_docs = tmp_path / "Documents"
    fake_docs.mkdir()
    monkeypatch.setattr("whizzard.safety._BROAD_FOLDERS", [fake_docs])
    overrides = check_mount_path(fake_docs, PROFILE_PERMISSIVE, True)
    assert len(overrides) == 1
    assert "broad folder" in overrides[0].reason


def test_subpath_of_broad_folder_also_requires_override(tmp_path: Path, monkeypatch):
    fake_docs = tmp_path / "Documents"
    inside = fake_docs / "specific-project"
    inside.mkdir(parents=True)
    monkeypatch.setattr("whizzard.safety._BROAD_FOLDERS", [fake_docs])
    # Without flag → blocked
    with pytest.raises(SafetyViolation):
        check_mount_path(inside, PROFILE_PERMISSIVE, False)
    # With both gates → allowed
    overrides = check_mount_path(inside, PROFILE_PERMISSIVE, True)
    assert len(overrides) == 1


# Override-required: cloud sync

def test_cloud_sync_root_blocked_when_strict_profile(tmp_path: Path, monkeypatch):
    fake_dropbox = tmp_path / "Dropbox"
    fake_dropbox.mkdir()
    monkeypatch.setattr("whizzard.safety._CLOUD_SYNC_ROOTS", [fake_dropbox])
    monkeypatch.setattr("whizzard.safety._BROAD_FOLDERS", [])
    with pytest.raises(SafetyViolation, match="profile 'strict'"):
        check_mount_path(fake_dropbox, PROFILE_STRICT, True)


def test_cloud_sync_subdir_requires_override(tmp_path: Path, monkeypatch):
    fake_dropbox = tmp_path / "Dropbox"
    sub = fake_dropbox / "work"
    sub.mkdir(parents=True)
    monkeypatch.setattr("whizzard.safety._CLOUD_SYNC_ROOTS", [fake_dropbox])
    monkeypatch.setattr("whizzard.safety._BROAD_FOLDERS", [])
    with pytest.raises(SafetyViolation, match="--allow-broad-mount"):
        check_mount_path(sub, PROFILE_PERMISSIVE, False)
    overrides = check_mount_path(sub, PROFILE_PERMISSIVE, True)
    assert len(overrides) == 1
    assert "cloud sync" in overrides[0].reason


# Override-required: parent of registered mount

def test_parent_of_registered_requires_override(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("whizzard.safety._BROAD_FOLDERS", [])
    monkeypatch.setattr("whizzard.safety._CLOUD_SYNC_ROOTS", [])
    parent = tmp_path / "projects"
    child = parent / "alpha"
    child.mkdir(parents=True)
    # Trying to mount the parent of an already-registered child
    with pytest.raises(SafetyViolation, match="parent of registered"):
        check_mount_path(parent, PROFILE_PERMISSIVE, False, other_registered_paths=[child])


def test_parent_of_registered_allowed_with_override(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("whizzard.safety._BROAD_FOLDERS", [])
    monkeypatch.setattr("whizzard.safety._CLOUD_SYNC_ROOTS", [])
    parent = tmp_path / "projects"
    child = parent / "alpha"
    child.mkdir(parents=True)
    overrides = check_mount_path(parent, PROFILE_PERMISSIVE, True, other_registered_paths=[child])
    assert len(overrides) >= 1
    assert any("parent of registered" in o.reason for o in overrides)


def test_registered_mount_itself_does_not_self_trigger(tmp_path: Path, monkeypatch):
    """Mounting a registered path while it's also in the 'others' list must
    not flag itself as a parent of itself."""
    monkeypatch.setattr("whizzard.safety._BROAD_FOLDERS", [])
    monkeypatch.setattr("whizzard.safety._CLOUD_SYNC_ROOTS", [])
    project = tmp_path / "project"
    project.mkdir()
    overrides = check_mount_path(project, PROFILE_STRICT, False, other_registered_paths=[project])
    assert overrides == []


def test_sibling_does_not_count_as_parent_or_descendant(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("whizzard.safety._BROAD_FOLDERS", [])
    monkeypatch.setattr("whizzard.safety._CLOUD_SYNC_ROOTS", [])
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    overrides = check_mount_path(a, PROFILE_STRICT, False, other_registered_paths=[b])
    assert overrides == []


# Override accumulation

def test_multiple_overrides_accumulated_when_relevant(tmp_path: Path, monkeypatch):
    """A path that triggers multiple override reasons reports all of them."""
    fake_docs = tmp_path / "Documents"
    fake_docs.mkdir()
    monkeypatch.setattr("whizzard.safety._BROAD_FOLDERS", [fake_docs])
    monkeypatch.setattr("whizzard.safety._CLOUD_SYNC_ROOTS", [])
    child = fake_docs / "registered-project"
    child.mkdir()
    overrides = check_mount_path(
        fake_docs, PROFILE_PERMISSIVE, True, other_registered_paths=[child]
    )
    # broad folder + parent of registered
    reasons = " ".join(o.reason for o in overrides)
    assert "broad folder" in reasons
    assert "parent of registered" in reasons


# OverrideRecord shape

def test_override_record_is_frozen():
    o = OverrideRecord(path="/a", reason="x")
    with pytest.raises(Exception):
        o.path = "/b"  # type: ignore[misc]
