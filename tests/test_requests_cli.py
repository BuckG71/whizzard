"""Stage 14 — `whiz requests` CLI tests (list / approve / deny) + status count."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from whizzard.adjust import AdjustResult
from whizzard.cli import app

runner = CliRunner()


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point WHIZZARD_HOME + the request channel at a temp tree."""
    home = tmp_path / "whizzard-home"
    sessions_dir = home / "sessions"
    logs_dir = home / "logs"
    sessions_dir.mkdir(parents=True)
    logs_dir.mkdir(parents=True)
    sessions_log = logs_dir / "sessions.jsonl"

    monkeypatch.setenv("WHIZZARD_HOME", str(home))
    from whizzard import config, session_log
    from whizzard import requests as reqs_mod
    from whizzard.cli import _session as cli_session
    monkeypatch.setattr(config, "WHIZZARD_HOME", home)
    monkeypatch.setattr(config, "CONFIG_DIR", home / "config")
    monkeypatch.setattr(config, "LOGS_DIR", logs_dir)
    monkeypatch.setattr(config, "STATE_DIR", home / "state")
    monkeypatch.setattr(reqs_mod, "SESSIONS_DIR", sessions_dir)
    monkeypatch.setattr(session_log, "SESSIONS_LOG", sessions_log)
    monkeypatch.setattr(reqs_mod, "SESSIONS_LOG", sessions_log)
    monkeypatch.setattr(cli_session, "SESSIONS_LOG", sessions_log)
    return SimpleNamespace(sessions_dir=sessions_dir, sessions_log=sessions_log)


def _put_request(
    sessions_dir: Path,
    *,
    request_id: str,
    session_id: str = "sess-1",
    kind: str = "mount",
    params: dict | None = None,
    reason: str = "",
    status: str = "pending",
) -> None:
    if params is None:
        params = (
            {"duration": "30m"} if kind == "extend"
            else {"name": "documents", "mode": None}
        )
    rdir = sessions_dir / session_id / "requests"
    rdir.mkdir(parents=True, exist_ok=True)
    (rdir / f"{request_id}.json").write_text(json.dumps({
        "request_id": request_id,
        "session_id": session_id,
        "kind": kind,
        "params": params,
        "reason": reason,
        "status": status,
        "created_at": "2026-05-21T00:00:00+00:00",
        "resolved_at": None,
        "resolution_detail": "",
    }))


def _status_of(sessions_dir: Path, session_id: str, request_id: str) -> str:
    path = sessions_dir / session_id / "requests" / f"{request_id}.json"
    return json.loads(path.read_text())["status"]


# --- list -------------------------------------------------------------------


def test_requests_bare_lists_nothing_when_empty(env):
    result = runner.invoke(app, ["requests"])
    assert result.exit_code == 0
    assert "no pending agent requests" in result.output


def test_requests_lists_a_pending_request(env):
    _put_request(env.sessions_dir, request_id="reqone", reason="need the docs")
    result = runner.invoke(app, ["requests"])
    assert result.exit_code == 0
    assert "reqone" in result.output
    assert "documents" in result.output
    assert "need the docs" in result.output


def test_requests_list_hides_resolved_by_default(env):
    _put_request(env.sessions_dir, request_id="donereq", status="applied")
    result = runner.invoke(app, ["requests", "list"])
    assert "donereq" not in result.output


def test_requests_list_all_includes_resolved(env):
    _put_request(env.sessions_dir, request_id="donereq", status="applied")
    result = runner.invoke(app, ["requests", "list", "--all"])
    assert result.exit_code == 0
    assert "donereq" in result.output


# --- deny -------------------------------------------------------------------


def test_requests_deny_marks_request_denied(env):
    _put_request(env.sessions_dir, request_id="denyme")
    result = runner.invoke(app, ["requests", "deny", "denyme"])
    assert result.exit_code == 0
    assert _status_of(env.sessions_dir, "sess-1", "denyme") == "denied"


def test_requests_deny_records_reason(env):
    _put_request(env.sessions_dir, request_id="denyme")
    runner.invoke(app, ["requests", "deny", "denyme", "--reason", "out of scope"])
    path = env.sessions_dir / "sess-1" / "requests" / "denyme.json"
    assert json.loads(path.read_text())["resolution_detail"] == "out of scope"


def test_requests_deny_missing_request_errors(env):
    result = runner.invoke(app, ["requests", "deny", "ghost"])
    assert result.exit_code == 2


def test_requests_deny_already_resolved_errors(env):
    _put_request(env.sessions_dir, request_id="donereq", status="denied")
    result = runner.invoke(app, ["requests", "deny", "donereq"])
    assert result.exit_code == 1


# --- approve ----------------------------------------------------------------


def test_requests_approve_missing_request_errors(env):
    result = runner.invoke(app, ["requests", "approve", "ghost"])
    assert result.exit_code == 2


def test_requests_approve_already_resolved_errors(env):
    _put_request(env.sessions_dir, request_id="donereq", status="applied")
    result = runner.invoke(app, ["requests", "approve", "donereq"])
    assert result.exit_code == 1


def test_requests_approve_routes_through_process_request(env, monkeypatch):
    _put_request(env.sessions_dir, request_id="okreq", reason="legit need")

    captured = {}

    def _fake_process(req, approver, **kwargs):
        captured["request_id"] = req.request_id
        return AdjustResult(exit_code=0, detail="adjusted")

    from whizzard.cli import requests as cli_requests
    monkeypatch.setattr(cli_requests, "process_request", _fake_process)

    result = runner.invoke(app, ["requests", "approve", "okreq", "--yes"])
    assert result.exit_code == 0
    assert captured["request_id"] == "okreq"
    assert "legit need" in result.output
    assert "adjusted" in result.output


# --- status integration -----------------------------------------------------


def test_status_surfaces_pending_request_count(env):
    env.sessions_log.write_text(json.dumps({
        "event": "session_start", "session_id": "sess-1",
        "profile": "default", "ts": "2026-05-21T00:00:00+00:00",
    }) + "\n")
    _put_request(env.sessions_dir, request_id="waiting")
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "Pending agent requests" in result.output
