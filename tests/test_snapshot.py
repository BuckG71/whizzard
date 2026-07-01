"""Tests for the per-session state snapshot writer (Stage 9 M2)."""

import json
from pathlib import Path

import pytest

from whizzard.config import Profile
from whizzard.mounts import Mount, MountMode
from whizzard.snapshot import (
    event_log_path,
    request_dir,
    session_dir,
    snapshot_path,
    write_snapshot,
)


@pytest.fixture
def profile() -> Profile:
    return Profile(
        name="build",
        network_enabled=True,
        duration_seconds=7200,
        allow_broad_mount=False,
        description="dev work",
    )


@pytest.fixture
def mounts() -> list[tuple[Mount, MountMode]]:
    return [
        (
            Mount(
                name="project-alpha",
                host_path=Path("/Users/bg/work/alpha"),
                default_mode="rw",
                description="alpha project",
            ),
            "rw",
        ),
        (
            Mount(
                name="docs-ro",
                host_path=Path("/Users/bg/docs"),
                default_mode="ro",
                description="docs",
            ),
            "ro",
        ),
    ]


def test_session_dir_under_whizzard_home(tmp_path):
    d = session_dir("abc-123", whizzard_home=tmp_path)
    assert d == tmp_path / "sessions" / "abc-123"


def test_snapshot_path_under_session_dir(tmp_path):
    p = snapshot_path("abc-123", whizzard_home=tmp_path)
    assert p == tmp_path / "sessions" / "abc-123" / "snapshot.json"


def test_event_log_path_under_session_dir(tmp_path):
    p = event_log_path("abc-123", whizzard_home=tmp_path)
    assert p == tmp_path / "sessions" / "abc-123" / "events.jsonl"


def test_request_dir_under_session_dir(tmp_path):
    d = request_dir("abc-123", whizzard_home=tmp_path)
    assert d == tmp_path / "sessions" / "abc-123" / "requests"


def test_write_snapshot_creates_session_dir(tmp_path, profile, mounts):
    write_snapshot(
        session_id="abc-123",
        profile=profile,
        resolved_mounts=mounts,
        harness_name="hermes-bot",
        whizzard_home=tmp_path,
    )
    assert (tmp_path / "sessions" / "abc-123").is_dir()
    assert (tmp_path / "sessions" / "abc-123" / "snapshot.json").exists()


def test_write_snapshot_returns_path(tmp_path, profile, mounts):
    p = write_snapshot(
        session_id="abc-123",
        profile=profile,
        resolved_mounts=mounts,
        harness_name="hermes-bot",
        whizzard_home=tmp_path,
    )
    assert p == tmp_path / "sessions" / "abc-123" / "snapshot.json"


def test_write_snapshot_content_includes_session_id(tmp_path, profile, mounts):
    p = write_snapshot(
        "abc-123", profile, mounts, "hermes-bot", whizzard_home=tmp_path
    )
    data = json.loads(p.read_text())
    assert data["session_id"] == "abc-123"


def test_write_snapshot_content_includes_profile_fields(tmp_path, profile, mounts):
    p = write_snapshot(
        "abc-123", profile, mounts, "hermes-bot", whizzard_home=tmp_path
    )
    data = json.loads(p.read_text())
    assert data["profile"]["name"] == "build"
    assert data["profile"]["network_enabled"] is True
    assert data["profile"]["duration_seconds"] == 7200
    assert data["profile"]["allow_broad_mount"] is False
    assert data["profile"]["description"] == "dev work"


def test_write_snapshot_content_includes_mounts(tmp_path, profile, mounts):
    p = write_snapshot(
        "abc-123", profile, mounts, "hermes-bot", whizzard_home=tmp_path
    )
    data = json.loads(p.read_text())
    assert len(data["mounts"]) == 2
    alpha = next(m for m in data["mounts"] if m["name"] == "project-alpha")
    assert alpha["host_path"] == "/Users/bg/work/alpha"
    assert alpha["container_path"] == "/mounts/project-alpha"
    assert alpha["mode"] == "rw"
    docs = next(m for m in data["mounts"] if m["name"] == "docs-ro")
    assert docs["mode"] == "ro"


def test_write_snapshot_content_includes_harness_name(tmp_path, profile, mounts):
    p = write_snapshot(
        "abc-123", profile, mounts, "hermes-bot", whizzard_home=tmp_path
    )
    data = json.loads(p.read_text())
    assert data["harness"] == "hermes-bot"


def test_write_snapshot_content_includes_timestamp(tmp_path, profile, mounts):
    p = write_snapshot(
        "abc-123", profile, mounts, "hermes-bot", whizzard_home=tmp_path
    )
    data = json.loads(p.read_text())
    assert "snapshot_written_at" in data
    # ISO 8601 format with Z or +00:00
    assert "T" in data["snapshot_written_at"]


def test_write_snapshot_empty_mounts_renders_empty_list(tmp_path, profile):
    p = write_snapshot(
        "abc-123", profile, [], "hermes-bot", whizzard_home=tmp_path
    )
    data = json.loads(p.read_text())
    assert data["mounts"] == []


def test_write_snapshot_overwrites_existing(tmp_path, profile, mounts):
    p1 = write_snapshot(
        "abc-123", profile, mounts, "hermes-bot", whizzard_home=tmp_path
    )
    # Same session_id, different harness — overwrite
    p2 = write_snapshot(
        "abc-123", profile, mounts, "other-harness", whizzard_home=tmp_path
    )
    assert p1 == p2
    data = json.loads(p2.read_text())
    assert data["harness"] == "other-harness"


# --- F-D-06: snapshot reflects duration override --------------------------


def test_snapshot_records_duration_override_when_set(tmp_path: Path):
    """After `whiz adjust --extend`, the relaunch passes an effective
    duration cap. The snapshot must record that override so the agent's
    whiz_status reports the actual remaining time."""
    from whizzard.config import Profile

    profile = Profile(
        name="default",
        network_enabled=True,
        duration_seconds=3600,  # profile says 1 hour
    )

    path = write_snapshot(
        "sess-1",
        profile,
        [],
        "hermes",
        whizzard_home=tmp_path,
        duration_override_seconds=7200,  # adjust extended to 2 hours
    )

    data = json.loads(path.read_text())
    # The override wins — snapshot shows 7200, not the profile's 3600.
    assert data["profile"]["duration_seconds"] == 7200
    assert data["profile"]["duration_override_active"] is True


def test_snapshot_uses_profile_duration_when_no_override(tmp_path: Path):
    from whizzard.config import Profile

    profile = Profile(
        name="default",
        network_enabled=True,
        duration_seconds=3600,
    )

    path = write_snapshot("sess-1", profile, [], "hermes", whizzard_home=tmp_path)

    data = json.loads(path.read_text())
    assert data["profile"]["duration_seconds"] == 3600
    assert "duration_override_active" not in data["profile"]


# --- F-E-04: absolute expires_at in the snapshot ---------------------------


def test_snapshot_includes_absolute_expires_at_for_bounded_session(tmp_path: Path):
    """The agent shouldn't have to do wall-clock math to compute expiry —
    the snapshot carries an absolute ISO timestamp."""
    from datetime import UTC, datetime

    from whizzard.config import Profile

    profile = Profile(
        name="default",
        network_enabled=True,
        duration_seconds=3600,
    )
    before = datetime.now(UTC)
    path = write_snapshot("sess-1", profile, [], "hermes", whizzard_home=tmp_path)
    after = datetime.now(UTC)

    data = json.loads(path.read_text())
    expires_at = datetime.fromisoformat(data["expires_at"])
    # Should be within [before + 3600s, after + 3600s].
    assert (expires_at - before).total_seconds() >= 3599
    assert (expires_at - after).total_seconds() <= 3601


def test_snapshot_expires_at_is_none_for_unlimited_session(tmp_path: Path):
    """duration_seconds=None means unlimited; expires_at should reflect that."""
    from whizzard.config import Profile

    profile = Profile(
        name="default",
        network_enabled=True,
        duration_seconds=None,  # unlimited
    )
    path = write_snapshot("sess-1", profile, [], "hermes", whizzard_home=tmp_path)

    data = json.loads(path.read_text())
    assert data["expires_at"] is None


def test_snapshot_expires_at_uses_override_when_set(tmp_path: Path):
    """F-D-06 + F-E-04: expires_at base is the effective duration, not the
    underlying profile value."""
    from datetime import UTC, datetime

    from whizzard.config import Profile

    profile = Profile(
        name="default",
        network_enabled=True,
        duration_seconds=3600,  # profile says 1h
    )
    before = datetime.now(UTC)
    path = write_snapshot(
        "sess-1", profile, [], "hermes",
        whizzard_home=tmp_path,
        duration_override_seconds=7200,  # but the relaunch said 2h
    )
    after = datetime.now(UTC)

    data = json.loads(path.read_text())
    expires_at = datetime.fromisoformat(data["expires_at"])
    # Should land ~2h from now, NOT ~1h.
    assert (expires_at - before).total_seconds() >= 7199
    assert (expires_at - after).total_seconds() <= 7201
