"""Tests for the per-session state snapshot writer (Stage 9 M2)."""

import json
from pathlib import Path

import pytest

from whizzard.config import Profile
from whizzard.mounts import Mount, MountMode
from whizzard.snapshot import (
    event_log_path,
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
