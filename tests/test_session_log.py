"""Stage 5: session log tests."""

import json
import os
from pathlib import Path

from whizzard.session_log import (
    append_event,
    log_expiry_warning,
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


def test_append_event_fsyncs_per_write(tmp_path: Path, monkeypatch):
    """F-G-12: each append durable-syncs to disk. The wake + adjust
    paths read the audit log immediately after writing session_start;
    a missing fsync between buffer-flush and disk-commit makes a
    running container an orphan on OS crash."""
    target = tmp_path / "log.jsonl"
    fsync_calls: list[int] = []
    real_fsync = os.fsync

    def _spy_fsync(fd: int) -> None:
        fsync_calls.append(fd)
        real_fsync(fd)

    monkeypatch.setattr("whizzard.session_log.os.fsync", _spy_fsync)
    append_event({"event": "x"}, path=target)
    append_event({"event": "y"}, path=target)
    assert len(fsync_calls) == 2, (
        f"expected one fsync per append; got {len(fsync_calls)}"
    )


def test_append_event_one_object_per_line(tmp_path: Path):
    target = tmp_path / "log.jsonl"
    append_event({"event": "a", "n": 1}, path=target)
    append_event({"event": "b", "n": 2}, path=target)
    lines = target.read_text().splitlines()
    assert len(lines) == 2
    # F-D-10: every line carries a schema-version stamp `v: 1` so a future
    # format change has a robust detection handle.
    p0 = json.loads(lines[0])
    p1 = json.loads(lines[1])
    assert p0["event"] == "a" and p0["n"] == 1 and p0["v"] == 1
    assert p1["event"] == "b" and p1["n"] == 2 and p1["v"] == 1


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


def test_session_log_size_returns_zero_when_missing(tmp_path: Path):
    """A3: session_log_size handles the no-log-yet case gracefully."""
    from whizzard.session_log import session_log_size

    missing = tmp_path / "no-log.jsonl"
    assert session_log_size(missing) == 0


def test_session_log_size_returns_byte_size(tmp_path: Path):
    """A3: session_log_size returns the actual file size."""
    from whizzard.session_log import session_log_size

    target = tmp_path / "sessions.jsonl"
    # write_bytes (not write_text) so the on-disk bytes are exact — text
    # mode would translate "\n"→"\r\n" on Windows and inflate the count.
    target.write_bytes(b"line one\nline two\n")
    assert session_log_size(target) == len(b"line one\nline two\n")


def test_find_session_start_after_offset_returns_none_when_no_log(tmp_path: Path):
    """A3: helper handles the no-log case."""
    from whizzard.session_log import find_session_start_after_offset

    missing = tmp_path / "no-log.jsonl"
    assert find_session_start_after_offset(0, missing) is None


def test_find_session_start_after_offset_returns_none_when_no_match(tmp_path: Path):
    """A3: helper returns None if no session_start event is after the offset.

    This is the "preflight failed; no new container launched" case —
    the audit-log ground truth that the wake / adjust should record
    as a *_failed event instead of *_woken / adjusted."""
    from whizzard.session_log import (
        find_session_start_after_offset,
        log_session_end,
    )

    target = tmp_path / "sessions.jsonl"
    # Pre-existing event written; offset captured AFTER.
    log_session_end(
        session_id="prior",
        container_id="c1",
        exit_status=0,
        end_time=1_700_000_000.0,
        duration_seconds=10.0,
        path=target,
    )
    offset = target.stat().st_size
    # New session_end written, but NO session_start.
    log_session_end(
        session_id="prior2",
        container_id="c2",
        exit_status=0,
        end_time=1_700_000_100.0,
        duration_seconds=10.0,
        path=target,
    )
    assert find_session_start_after_offset(offset, target) is None


def test_find_session_start_after_offset_finds_new_session_id(tmp_path: Path):
    """A3: helper returns the new sid when session_start was logged
    after the offset. This is the "new container started" case — wake
    succeeded (whatever exit code follows). Closes the longstanding TODO
    of recovering the new sid for the audit chain."""
    from whizzard.session_log import (
        find_session_start_after_offset,
        log_session_end,
        log_session_start,
    )

    target = tmp_path / "sessions.jsonl"
    log_session_end(
        session_id="prior",
        container_id="c1",
        exit_status=0,
        end_time=1_700_000_000.0,
        duration_seconds=10.0,
        path=target,
    )
    offset = target.stat().st_size
    log_session_start(
        session_id="new-sid-42",
        profile_name="default",
        network_enabled=True,
        duration_limit_seconds=None,
        allow_broad_mount=False,
        image_tag="x",
        image_id=None,
        mounts=[],
        argv=[],
        start_time=1_700_000_100.0,
        path=target,
    )
    assert find_session_start_after_offset(offset, target) == "new-sid-42"


def test_find_session_start_after_offset_picks_latest_when_multiple(tmp_path: Path):
    """A3: if multiple session_start events appear after the offset,
    return the latest (last written) — that's the one the wake / adjust
    actually produced."""
    from whizzard.session_log import (
        find_session_start_after_offset,
        log_session_start,
    )

    target = tmp_path / "sessions.jsonl"
    log_session_start(
        session_id="old",
        profile_name="default",
        network_enabled=True,
        duration_limit_seconds=None,
        allow_broad_mount=False,
        image_tag="x",
        image_id=None,
        mounts=[],
        argv=[],
        start_time=1.0,
        path=target,
    )
    log_session_start(
        session_id="new",
        profile_name="default",
        network_enabled=True,
        duration_limit_seconds=None,
        allow_broad_mount=False,
        image_tag="x",
        image_id=None,
        mounts=[],
        argv=[],
        start_time=2.0,
        path=target,
    )
    assert find_session_start_after_offset(0, target) == "new"


def test_log_session_start_omits_allow_ephemeral_when_false(tmp_path: Path):
    target = tmp_path / "sessions.jsonl"
    log_session_start(
        session_id="sess-eph-0",
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
    assert "allow_ephemeral" not in record


def test_log_session_start_records_allow_ephemeral_when_true(tmp_path: Path):
    target = tmp_path / "sessions.jsonl"
    log_session_start(
        session_id="sess-eph-1",
        profile_name="default",
        network_enabled=True,
        duration_limit_seconds=None,
        allow_broad_mount=False,
        image_tag="x",
        image_id=None,
        mounts=[],
        argv=[],
        start_time=1_700_000_000.0,
        allow_ephemeral=True,
        path=target,
    )
    record = json.loads(target.read_text())
    assert record["allow_ephemeral"] is True


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


# --- Stage 15: expiry_reason on session_end -------------------------------


def test_session_end_defaults_expiry_reason_to_clean(tmp_path: Path):
    target = tmp_path / "s.jsonl"
    log_session_end("s", "cid", 0, 1_700_000_010.0, 10.0, path=target)
    entry = json.loads(target.read_text().splitlines()[0])
    assert entry["expiry_reason"] == "clean"


def test_session_end_records_expiry_reason(tmp_path: Path):
    target = tmp_path / "s.jsonl"
    log_session_end("s", "cid", 137, 1_700_000_010.0, 10.0, path=target,
                    expiry_reason="idle")
    entry = json.loads(target.read_text().splitlines()[0])
    assert entry["expiry_reason"] == "idle"


def test_log_expiry_warning_writes_event(tmp_path: Path):
    target = tmp_path / "s.jsonl"
    log_expiry_warning("sess-1", 300, path=target)
    entry = json.loads(target.read_text().splitlines()[0])
    assert entry["event"] == "session_expiry_warning"
    assert entry["session_id"] == "sess-1"
    assert entry["seconds_remaining"] == 300


# --- F-D-01: forged origin in cell-supplied event is overridden -----------


def test_merge_agent_events_overrides_forged_whizzard_origin(tmp_path: Path):
    """A cell-written events.jsonl line that claims origin: whizzard must
    be force-rewritten to origin: agent. D-12 invariant: agent-authored
    entries are clearly distinguished from Whizzard-authored entries."""
    event_file = tmp_path / "events.jsonl"
    event_file.write_text(
        json.dumps({
            "session_id": "sess-1",
            "event_type": "forged",
            "origin": "whizzard",  # attempt to claim system authorship
        }) + "\n"
    )
    target = tmp_path / "audit.jsonl"

    merge_agent_events("sess-1", event_file, target_log=target)

    entry = json.loads(target.read_text().splitlines()[0])
    # MUST be rewritten to "agent" — D-12 violation if not.
    assert entry["origin"] == "agent"


# --- F-D-04: size caps prevent cell from DoS-ing the host log ---------------


def test_merge_agent_events_truncates_on_total_lines_overflow(tmp_path: Path):
    """A cell writing many small events triggers the total-lines cap; the
    merge stops and appends a truncation marker."""
    from whizzard import session_log as _sl

    # Drop the per-test caps to a manageable size.
    monkeypatch_value = 5
    saved = _sl._AGENT_EVENT_TOTAL_LINES_MAX
    _sl._AGENT_EVENT_TOTAL_LINES_MAX = monkeypatch_value
    try:
        event_file = tmp_path / "events.jsonl"
        lines = [
            json.dumps({"session_id": "sess-1", "event_type": f"e{i}"})
            for i in range(20)
        ]
        event_file.write_text("\n".join(lines) + "\n")
        target = tmp_path / "audit.jsonl"

        merged = merge_agent_events("sess-1", event_file, target_log=target)

        assert merged == monkeypatch_value
        out_lines = target.read_text().splitlines()
        # First N are merged agent events, last is the truncation marker.
        assert len(out_lines) == monkeypatch_value + 1
        marker = json.loads(out_lines[-1])
        assert marker["event"] == "session_agent_events_truncated"
        assert marker["origin"] == "whizzard"  # legitimately Whizzard-authored
        assert marker["merged_count"] == monkeypatch_value
    finally:
        _sl._AGENT_EVENT_TOTAL_LINES_MAX = saved


def test_merge_agent_events_skips_oversize_lines_but_continues(tmp_path: Path):
    """A single huge line is skipped; smaller lines after it still merge."""
    from whizzard import session_log as _sl
    saved = _sl._AGENT_EVENT_LINE_MAX_BYTES
    _sl._AGENT_EVENT_LINE_MAX_BYTES = 200  # tiny cap for the test
    try:
        event_file = tmp_path / "events.jsonl"
        huge = "x" * 500
        event_file.write_text(
            json.dumps({"session_id": "sess-1", "event_type": "small1"}) + "\n"
            + json.dumps({"session_id": "sess-1", "event_type": "huge", "junk": huge}) + "\n"
            + json.dumps({"session_id": "sess-1", "event_type": "small2"}) + "\n"
        )
        target = tmp_path / "audit.jsonl"

        merged = merge_agent_events("sess-1", event_file, target_log=target)

        # huge dropped; small1 + small2 merged.
        assert merged == 2
        events = [json.loads(line)["event_type"]
                  for line in target.read_text().splitlines()]
        assert events == ["small1", "small2"]
    finally:
        _sl._AGENT_EVENT_LINE_MAX_BYTES = saved


# --- F-D-08: timestamps use microsecond precision -------------------------


def test_session_end_timestamp_has_microsecond_precision(tmp_path: Path):
    """Previously second-precision (`%Y-%m-%dT%H:%M:%SZ`); now ISO with
    microsecond fields so audit sorting doesn't see ties within the same
    second."""
    target = tmp_path / "s.jsonl"
    log_session_end("s", "cid", 0, 1_700_000_010.123456, 10.0, path=target)
    entry = json.loads(target.read_text().splitlines()[0])
    # ISO with microseconds includes a decimal point in the seconds field.
    assert "." in entry["end_time"]


# --- F-D-10: schema_version stamp on every line ---------------------------


def test_session_start_carries_v_stamp(tmp_path: Path):
    """Every audit-log line gets a `v: 1` schema-version stamp so future
    schema changes have a robust detection handle."""
    target = tmp_path / "s.jsonl"
    log_session_start(
        session_id="sess-1",
        profile_name="default",
        network_enabled=True,
        duration_limit_seconds=None,
        allow_broad_mount=False,
        image_tag="x",
        image_id=None,
        mounts=[],
        argv=["docker"],
        start_time=1_700_000_000.0,
        path=target,
    )
    entry = json.loads(target.read_text().splitlines()[0])
    assert entry["v"] == 1
