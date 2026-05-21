"""Tests for the Whiz MCP server tool functions (Stage 9, D-156).

The four tools are plain Python functions so they can be tested without
spinning up an MCP runtime. The MCP wiring in `main()` is a thin wrapper
and not under test here.
"""

import json

from whizzard.mcp_server import (
    ENV_AUDIT_LOG_PATH,
    ENV_EVENT_LOG_PATH,
    ENV_REQUEST_DIR,
    ENV_SESSION_ID,
    ENV_SNAPSHOT_PATH,
    tool_whiz_audit_self,
    tool_whiz_check_request,
    tool_whiz_emit_event,
    tool_whiz_list_presets,
    tool_whiz_request_extend,
    tool_whiz_request_mount,
    tool_whiz_status,
)

# --- whiz_status ---------------------------------------------------------


def test_status_returns_error_when_env_unset(monkeypatch):
    monkeypatch.delenv(ENV_SNAPSHOT_PATH, raising=False)
    result = tool_whiz_status()
    assert "error" in result
    assert ENV_SNAPSHOT_PATH in result["error"]


def test_status_returns_error_when_snapshot_missing(tmp_path, monkeypatch):
    missing = tmp_path / "no-such-file.json"
    monkeypatch.setenv(ENV_SNAPSHOT_PATH, str(missing))
    result = tool_whiz_status()
    assert "error" in result
    assert "not found" in result["error"]


def test_status_returns_snapshot_content_when_present(tmp_path, monkeypatch):
    payload = {
        "session_id": "abc-123",
        "profile": {"name": "default", "network_enabled": True},
        "mounts": [{"name": "project-alpha", "mode": "rw"}],
        "harness": "hermes-bot",
    }
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(json.dumps(payload))
    monkeypatch.setenv(ENV_SNAPSHOT_PATH, str(snapshot))

    result = tool_whiz_status()
    assert result == payload


def test_status_returns_error_when_snapshot_corrupt(tmp_path, monkeypatch):
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text("not valid json {{{")
    monkeypatch.setenv(ENV_SNAPSHOT_PATH, str(snapshot))

    result = tool_whiz_status()
    assert "error" in result
    assert "unreadable" in result["error"]


# --- whiz_audit_self -----------------------------------------------------


def test_audit_self_returns_empty_when_env_unset(monkeypatch):
    monkeypatch.delenv(ENV_AUDIT_LOG_PATH, raising=False)
    monkeypatch.delenv(ENV_SESSION_ID, raising=False)
    assert tool_whiz_audit_self() == []


def test_audit_self_returns_empty_when_log_missing(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_AUDIT_LOG_PATH, str(tmp_path / "missing.jsonl"))
    monkeypatch.setenv(ENV_SESSION_ID, "abc-123")
    assert tool_whiz_audit_self() == []


def test_audit_self_filters_by_session_id(tmp_path, monkeypatch):
    log = tmp_path / "sessions.jsonl"
    log.write_text(
        json.dumps({"session_id": "abc-123", "event": "session_start"}) + "\n"
        + json.dumps({"session_id": "other", "event": "session_start"}) + "\n"
        + json.dumps({"session_id": "abc-123", "event": "session_end"}) + "\n"
    )
    monkeypatch.setenv(ENV_AUDIT_LOG_PATH, str(log))
    monkeypatch.setenv(ENV_SESSION_ID, "abc-123")

    entries = tool_whiz_audit_self()
    assert len(entries) == 2
    assert all(e["session_id"] == "abc-123" for e in entries)


def test_audit_self_skips_malformed_lines(tmp_path, monkeypatch):
    log = tmp_path / "sessions.jsonl"
    log.write_text(
        json.dumps({"session_id": "abc-123", "event": "ok"}) + "\n"
        + "this line is garbage\n"
        + "\n"  # empty line
        + json.dumps({"session_id": "abc-123", "event": "ok2"}) + "\n"
    )
    monkeypatch.setenv(ENV_AUDIT_LOG_PATH, str(log))
    monkeypatch.setenv(ENV_SESSION_ID, "abc-123")

    entries = tool_whiz_audit_self()
    assert len(entries) == 2


# --- whiz_emit_event -----------------------------------------------------


def test_emit_event_returns_error_when_env_unset(monkeypatch):
    monkeypatch.delenv(ENV_EVENT_LOG_PATH, raising=False)
    monkeypatch.delenv(ENV_SESSION_ID, raising=False)
    result = tool_whiz_emit_event("ping", "hello")
    assert result["ok"] is False


def test_emit_event_appends_to_log(tmp_path, monkeypatch):
    event_log = tmp_path / "events.jsonl"
    monkeypatch.setenv(ENV_EVENT_LOG_PATH, str(event_log))
    monkeypatch.setenv(ENV_SESSION_ID, "session-xyz")

    result = tool_whiz_emit_event("agent_note", "I observe X")
    assert result["ok"] is True
    assert result["logged"]["event_type"] == "agent_note"
    assert result["logged"]["origin"] == "agent"
    assert result["logged"]["session_id"] == "session-xyz"

    # File should contain the entry
    lines = event_log.read_text().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["session_id"] == "session-xyz"
    assert entry["origin"] == "agent"


def test_emit_event_appends_multiple_entries(tmp_path, monkeypatch):
    event_log = tmp_path / "events.jsonl"
    monkeypatch.setenv(ENV_EVENT_LOG_PATH, str(event_log))
    monkeypatch.setenv(ENV_SESSION_ID, "session-xyz")

    tool_whiz_emit_event("first", "1")
    tool_whiz_emit_event("second", "2")

    lines = event_log.read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["event_type"] == "first"
    assert json.loads(lines[1])["event_type"] == "second"


def test_emit_event_creates_parent_dir_if_missing(tmp_path, monkeypatch):
    event_log = tmp_path / "nested" / "dir" / "events.jsonl"
    monkeypatch.setenv(ENV_EVENT_LOG_PATH, str(event_log))
    monkeypatch.setenv(ENV_SESSION_ID, "session-xyz")

    result = tool_whiz_emit_event("test", "")
    assert result["ok"] is True
    assert event_log.exists()


# --- whiz_list_presets ---------------------------------------------------


def test_list_presets_stub_returns_empty():
    # Stage 10 dependency — currently a stub.
    assert tool_whiz_list_presets() == []


# --- Stage 14: whiz_request_mount ----------------------------------------


def test_request_mount_returns_error_when_channel_unconfigured(monkeypatch):
    monkeypatch.delenv(ENV_REQUEST_DIR, raising=False)
    monkeypatch.delenv(ENV_SESSION_ID, raising=False)
    result = tool_whiz_request_mount("documents")
    assert result["ok"] is False
    assert "not configured" in result["error"]


def test_request_mount_requires_a_name(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_REQUEST_DIR, str(tmp_path))
    monkeypatch.setenv(ENV_SESSION_ID, "sess-1")
    result = tool_whiz_request_mount("")
    assert result["ok"] is False
    assert "name" in result["error"]


def test_request_mount_rejects_bad_mode(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_REQUEST_DIR, str(tmp_path))
    monkeypatch.setenv(ENV_SESSION_ID, "sess-1")
    result = tool_whiz_request_mount("documents", mode="exec")
    assert result["ok"] is False
    assert "mode" in result["error"]


def test_request_mount_writes_pending_request_file(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_REQUEST_DIR, str(tmp_path))
    monkeypatch.setenv(ENV_SESSION_ID, "sess-xyz")

    result = tool_whiz_request_mount("documents", mode="ro", reason="need docs")
    assert result["ok"] is True
    assert result["status"] == "pending"
    request_id = result["request_id"]

    written = tmp_path / f"{request_id}.json"
    assert written.exists()
    record = json.loads(written.read_text())
    assert record["kind"] == "mount"
    assert record["params"] == {"name": "documents", "mode": "ro"}
    assert record["reason"] == "need docs"
    assert record["status"] == "pending"
    assert record["session_id"] == "sess-xyz"


def test_request_mount_omitted_mode_stored_as_none(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_REQUEST_DIR, str(tmp_path))
    monkeypatch.setenv(ENV_SESSION_ID, "sess-xyz")
    result = tool_whiz_request_mount("documents")
    record = json.loads((tmp_path / f"{result['request_id']}.json").read_text())
    assert record["params"]["mode"] is None


# --- Stage 14: whiz_request_extend ---------------------------------------


def test_request_extend_requires_a_duration(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_REQUEST_DIR, str(tmp_path))
    monkeypatch.setenv(ENV_SESSION_ID, "sess-1")
    result = tool_whiz_request_extend("")
    assert result["ok"] is False
    assert "duration" in result["error"]


def test_request_extend_writes_pending_request_file(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_REQUEST_DIR, str(tmp_path))
    monkeypatch.setenv(ENV_SESSION_ID, "sess-xyz")
    result = tool_whiz_request_extend("30m", reason="long task")
    assert result["ok"] is True
    record = json.loads((tmp_path / f"{result['request_id']}.json").read_text())
    assert record["kind"] == "extend"
    assert record["params"] == {"duration": "30m"}


# --- Stage 14: whiz_check_request ----------------------------------------


def test_check_request_returns_error_when_channel_unconfigured(monkeypatch):
    monkeypatch.delenv(ENV_REQUEST_DIR, raising=False)
    result = tool_whiz_check_request("abc123")
    assert result["ok"] is False


def test_check_request_reports_missing_request(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_REQUEST_DIR, str(tmp_path))
    result = tool_whiz_check_request("does-not-exist")
    assert result["ok"] is False
    assert "no request" in result["error"]


def test_check_request_round_trips_a_submitted_request(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_REQUEST_DIR, str(tmp_path))
    monkeypatch.setenv(ENV_SESSION_ID, "sess-xyz")
    submitted = tool_whiz_request_mount("documents", reason="why")

    checked = tool_whiz_check_request(submitted["request_id"])
    assert checked["ok"] is True
    assert checked["request"]["request_id"] == submitted["request_id"]
    assert checked["request"]["status"] == "pending"


def test_check_request_reports_unreadable_request(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_REQUEST_DIR, str(tmp_path))
    (tmp_path / "corrupt.json").write_text("not json {{{")
    result = tool_whiz_check_request("corrupt")
    assert result["ok"] is False
    assert "unreadable" in result["error"]
