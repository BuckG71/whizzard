"""Stage 5: session log tests."""

import json
from pathlib import Path

import pytest

from whizzard.session_log import (
    append_event,
    log_session_end,
    log_session_start,
    merge_agent_events,
    new_session_id,
)


def test_new_session_ids_are_unique():
    seen = {new_session_id() for _ in range(50)}
    assert len(seen) == 50


def test_new_session_id_is_uuid_format():
    sid = new_session_id()
    # 8-4-4-4-12 hex pattern
    parts = sid.split("-")
    assert len(parts) == 5
    assert [len(p) for p in parts] == [8, 4, 4, 4, 12]


def test_append_event_creates_parent_dir(tmp_path: Path):
    target = tmp_path / "deep" / "nested" / "log.jsonl"
    append_event({"event": "x"}, path=target)
    assert target.exists()


def test_append_event_one_object_per_line(tmp_path: Path):
    target = tmp_path / "log.jsonl"
    append_event({"event": "a", "n": 1}, path=target)
    append_event({"event": "b", "n": 2}, path=target)
    lines = target.read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"event": "a", "n": 1}
    assert json.loads(lines[1]) == {"event": "b", "n": 2}


def test_log_session_start_writes_expected_fields(tmp_path: Path):
    target = tmp_path / "sessions.jsonl"
    log_session_start(
        session_id="sess-1",
        profile_name="build",
        network_enabled=True,
        duration_limit_seconds=7200,
        allow_broad_mount=False,
        image_tag="whizzard-base:latest",
        image_id="sha256:abc123",
        mounts=[{"name": "alpha", "mode": "rw", "host_path": "/h/a", "container_path": "/mounts/alpha"}],
        argv=["docker", "run", "--rm"],
        start_time=1_700_000_000.0,
        path=target,
    )
    line = target.read_text().strip()
    record = json.loads(line)
    assert record["event"] == "session_start"
    assert record["session_id"] == "sess-1"
    assert record["profile"] == "build"
    assert record["network_enabled"] is True
    assert record["duration_limit_seconds"] == 7200
    assert record["allow_broad_mount"] is False
    assert record["image_tag"] == "whizzard-base:latest"
    assert record["image_id"] == "sha256:abc123"
    assert record["mounts"][0]["name"] == "alpha"
    assert record["argv"] == ["docker", "run", "--rm"]
    assert "start_time" in record
    assert "ts" in record
    assert record["overrides_used"] == []  # default empty list


def test_log_session_start_records_overrides_used(tmp_path: Path):
    target = tmp_path / "sessions.jsonl"
    log_session_start(
        session_id="sess-7",
        profile_name="power",
        network_enabled=True,
        duration_limit_seconds=3600,
        allow_broad_mount=True,
        image_tag="x",
        image_id=None,
        mounts=[],
        argv=[],
        start_time=1_700_000_000.0,
        overrides_used=[
            {"path": "/Users/me/Documents", "reason": "broad folder (/Users/me/Documents)"},
        ],
        path=target,
    )
    record = json.loads(target.read_text())
    assert len(record["overrides_used"]) == 1
    assert record["overrides_used"][0]["path"] == "/Users/me/Documents"
    assert "broad folder" in record["overrides_used"][0]["reason"]


def test_log_session_start_handles_unlimited_duration(tmp_path: Path):
    target = tmp_path / "sessions.jsonl"
    log_session_start(
        session_id="sess-2",
        profile_name="default",
        network_enabled=True,
        duration_limit_seconds=None,
        allow_broad_mount=False,
        image_tag="x",
        image_id=None,
        mounts=[],
        argv=[],
        start_time=1_700_000_000.0,
        path=target,
    )
    record = json.loads(target.read_text())
    assert record["duration_limit_seconds"] is None
    assert record["image_id"] is None


def test_log_session_end_writes_expected_fields(tmp_path: Path):
    target = tmp_path / "sessions.jsonl"
    log_session_end(
        session_id="sess-1",
        container_id="abc1234567",
        exit_status=0,
        end_time=1_700_000_042.5,
        duration_seconds=42.5,
        path=target,
    )
    record = json.loads(target.read_text())
    assert record["event"] == "session_end"
    assert record["session_id"] == "sess-1"
    assert record["container_id"] == "abc1234567"
    assert record["exit_status"] == 0
    assert record["duration_seconds"] == 42.5
    assert "end_time" in record


def test_log_session_end_handles_missing_container_id(tmp_path: Path):
    """Container ID may be None if cidfile was never written (e.g. docker
    failed before the container started). Log it as null, not as a crash."""
    target = tmp_path / "sessions.jsonl"
    log_session_end(
        session_id="sess-3",
        container_id=None,
        exit_status=125,
        end_time=1_700_000_001.0,
        duration_seconds=1.0,
        path=target,
    )
    record = json.loads(target.read_text())
    assert record["container_id"] is None
    assert record["exit_status"] == 125


def test_start_and_end_appear_in_order(tmp_path: Path):
    """A complete session writes start then end as separate JSONL lines."""
    target = tmp_path / "sessions.jsonl"
    log_session_start(
        session_id="sess-1",
        profile_name="default",
        network_enabled=True,
        duration_limit_seconds=None,
        allow_broad_mount=False,
        image_tag="x",
        image_id=None,
        mounts=[],
        argv=[],
        start_time=1_700_000_000.0,
        path=target,
    )
    log_session_end(
        session_id="sess-1",
        container_id="cid",
        exit_status=0,
        end_time=1_700_000_010.0,
        duration_seconds=10.0,
        path=target,
    )
    lines = target.read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["event"] == "session_start"
    assert json.loads(lines[1])["event"] == "session_end"
    assert json.loads(lines[0])["session_id"] == json.loads(lines[1])["session_id"]


# --- merge_agent_events (Stage 9 M4) --------------------------------------


def test_merge_agent_events_returns_zero_when_file_missing(tmp_path: Path):
    missing = tmp_path / "no-events.jsonl"
    target = tmp_path / "audit.jsonl"
    merged = merge_agent_events("sess-1", missing, target_log=target)
    assert merged == 0
    assert not target.exists()  # nothing was written


def test_merge_agent_events_appends_entries_to_audit_log(tmp_path: Path):
    event_file = tmp_path / "events.jsonl"
    event_file.write_text(
        json.dumps({"session_id": "sess-1", "event_type": "ping", "origin": "agent"}) + "\n"
        + json.dumps({"session_id": "sess-1", "event_type": "pong", "origin": "agent"}) + "\n"
    )
    target = tmp_path / "audit.jsonl"

    merged = merge_agent_events("sess-1", event_file, target_log=target)

    assert merged == 2
    lines = target.read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["event_type"] == "ping"
    assert json.loads(lines[1])["event_type"] == "pong"


def test_merge_agent_events_skips_wrong_session_id(tmp_path: Path):
    event_file = tmp_path / "events.jsonl"
    event_file.write_text(
        json.dumps({"session_id": "sess-1", "event_type": "mine", "origin": "agent"}) + "\n"
        + json.dumps({"session_id": "OTHER", "event_type": "leak", "origin": "agent"}) + "\n"
    )
    target = tmp_path / "audit.jsonl"

    merged = merge_agent_events("sess-1", event_file, target_log=target)

    assert merged == 1
    lines = target.read_text().splitlines()
    assert json.loads(lines[0])["event_type"] == "mine"


def test_merge_agent_events_skips_malformed_lines(tmp_path: Path):
    event_file = tmp_path / "events.jsonl"
    event_file.write_text(
        json.dumps({"session_id": "sess-1", "event_type": "ok"}) + "\n"
        + "this is garbage\n"
        + "\n"  # empty line
        + json.dumps({"session_id": "sess-1", "event_type": "also-ok"}) + "\n"
    )
    target = tmp_path / "audit.jsonl"

    merged = merge_agent_events("sess-1", event_file, target_log=target)

    assert merged == 2


def test_merge_agent_events_enforces_origin_marker(tmp_path: Path):
    """Entries written without `origin` get `agent` added defensively."""
    event_file = tmp_path / "events.jsonl"
    event_file.write_text(
        # No origin field — should be added on merge
        json.dumps({"session_id": "sess-1", "event_type": "no-origin"}) + "\n"
    )
    target = tmp_path / "audit.jsonl"

    merge_agent_events("sess-1", event_file, target_log=target)

    entry = json.loads(target.read_text().splitlines()[0])
    assert entry["origin"] == "agent"


def test_merge_agent_events_preserves_existing_origin(tmp_path: Path):
    event_file = tmp_path / "events.jsonl"
    event_file.write_text(
        json.dumps({"session_id": "sess-1", "event_type": "tagged", "origin": "agent"}) + "\n"
    )
    target = tmp_path / "audit.jsonl"

    merge_agent_events("sess-1", event_file, target_log=target)

    entry = json.loads(target.read_text().splitlines()[0])
    assert entry["origin"] == "agent"
