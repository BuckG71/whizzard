"""Stage 14 — host-side agent-request channel tests (`whizzard/requests.py`).

Covers the pure pieces (parsing, listing, request→Changes mapping, the
pre-flight validator) plus `process_request` with `adjust_session` mocked —
real Docker stop+relaunch is the integration tier's job.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import whizzard.requests as reqs
from whizzard.adjust import AdjustResult, Changes
from whizzard.config import Profile
from whizzard.mounts import Mount, MountRegistryError
from whizzard.requests import (
    AgentRequest,
    find_request,
    mark_resolved,
    process_request,
    read_all_requests,
    read_session_requests,
    request_to_changes,
    validate_request,
)
from whizzard.safety import SafetyViolation

# --- Fixtures / helpers -----------------------------------------------------


@pytest.fixture
def sessions_dir(tmp_path, monkeypatch):
    """Redirect the module's SESSIONS_DIR and STATE_DIR at a tmp tree.

    F-D-05: STATE_DIR is where the host-only authoritative resolutions
    store lives. Tests that simulate a "resolved" request need to redirect
    it too so `_resolutions_path` lands inside the tmp tree.
    """
    d = tmp_path / "sessions"
    d.mkdir()
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setattr(reqs, "SESSIONS_DIR", d)
    from whizzard import config as _config
    monkeypatch.setattr(_config, "STATE_DIR", state)
    return d


def _write_request(
    sessions_dir: Path,
    *,
    request_id: str = "reqaaaaaaaaa",
    session_id: str = "sess-1",
    kind: str = "extend",
    params: dict | None = None,
    reason: str = "",
    status: str = "pending",
) -> Path:
    """Write one request JSON file into <sessions_dir>/<sid>/requests/.

    F-D-05: a non-pending ``status`` argument also seeds the host-only
    authoritative resolutions store — the cell-written status field on
    the request file alone is ignored by `_load_request` after the fix.
    """
    if params is None:
        params = (
            {"duration": "30m"} if kind == "extend"
            else {"name": "documents", "mode": None}
        )
    rdir = sessions_dir / session_id / "requests"
    rdir.mkdir(parents=True, exist_ok=True)
    record = {
        "request_id": request_id,
        "session_id": session_id,
        "kind": kind,
        "params": params,
        "reason": reason,
        "status": status,
        "created_at": "2026-05-21T00:00:00+00:00",
        "resolved_at": None,
        "resolution_detail": "",
    }
    path = rdir / f"{request_id}.json"
    path.write_text(json.dumps(record))
    # If the test asks for a resolved status, also write the host-only
    # authoritative record — that's what _load_request actually reads now.
    if status != "pending":
        res = reqs._resolutions_path(session_id, request_id)
        res.parent.mkdir(parents=True, exist_ok=True)
        res.write_text(json.dumps({
            "request_id": request_id,
            "session_id": session_id,
            "kind": kind,
            "status": status,
            "resolution_detail": "",
            "resolved_at": "2026-05-21T00:00:00+00:00",
        }))
    return path


def _load(path: Path) -> AgentRequest:
    req = reqs._load_request(path)
    assert req is not None
    return req


# --- AgentRequest.summary ---------------------------------------------------


def test_summary_mount_with_mode():
    req = AgentRequest(
        request_id="r", session_id="s", kind="mount",
        params={"name": "documents", "mode": "ro"}, reason="", status="pending",
        created_at="", path=Path("/x"),
    )
    assert req.summary() == "add mount documents (ro)"


def test_summary_extend():
    req = AgentRequest(
        request_id="r", session_id="s", kind="extend",
        params={"duration": "1h"}, reason="", status="pending",
        created_at="", path=Path("/x"),
    )
    assert req.summary() == "extend duration by 1h"


# --- _load_request ----------------------------------------------------------


def test_load_request_parses_valid_file(sessions_dir):
    path = _write_request(sessions_dir, reason="please")
    req = _load(path)
    assert req.kind == "extend"
    assert req.reason == "please"
    assert req.path == path


def test_load_request_returns_none_on_corrupt_json(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("not json {{{")
    assert reqs._load_request(bad) is None


def test_load_request_returns_none_on_unknown_kind(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({
        "request_id": "r", "session_id": "s", "kind": "delete_everything",
    }))
    assert reqs._load_request(bad) is None


def test_load_request_returns_none_when_missing_fields(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"kind": "mount"}))  # no request_id / session_id
    assert reqs._load_request(bad) is None


# --- read_session_requests / read_all_requests ------------------------------


def test_read_session_requests_pending_only(sessions_dir):
    _write_request(sessions_dir, request_id="r1", status="pending")
    _write_request(sessions_dir, request_id="r2", status="applied")
    pending = read_session_requests("sess-1")
    assert [r.request_id for r in pending] == ["r1"]


def test_read_session_requests_all(sessions_dir):
    _write_request(sessions_dir, request_id="r1", status="pending")
    _write_request(sessions_dir, request_id="r2", status="applied")
    everything = read_session_requests("sess-1", pending_only=False)
    assert {r.request_id for r in everything} == {"r1", "r2"}


def test_read_session_requests_empty_when_no_dir(sessions_dir):
    assert read_session_requests("never-existed") == []


def test_read_all_requests_spans_sessions(sessions_dir):
    _write_request(sessions_dir, request_id="r1", session_id="sess-a")
    _write_request(sessions_dir, request_id="r2", session_id="sess-b")
    found = read_all_requests()
    assert {r.request_id for r in found} == {"r1", "r2"}


def test_read_all_requests_skips_corrupt_files(sessions_dir):
    _write_request(sessions_dir, request_id="good")
    rdir = sessions_dir / "sess-1" / "requests"
    (rdir / "junk.json").write_text("garbage {{{")
    found = read_all_requests()
    assert [r.request_id for r in found] == ["good"]


def test_read_all_requests_empty_when_no_sessions_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(reqs, "SESSIONS_DIR", tmp_path / "absent")
    assert read_all_requests() == []


# --- find_request -----------------------------------------------------------


def test_find_request_locates_across_sessions(sessions_dir):
    _write_request(sessions_dir, request_id="target", session_id="sess-z")
    found = find_request("target")
    assert found is not None and found.session_id == "sess-z"


def test_find_request_returns_none_when_absent(sessions_dir):
    assert find_request("nope") is None


# --- mark_resolved ----------------------------------------------------------


def test_mark_resolved_rewrites_status_and_detail(sessions_dir):
    path = _write_request(sessions_dir)
    req = _load(path)
    mark_resolved(req, "applied", "all good")
    data = json.loads(path.read_text())
    assert data["status"] == "applied"
    assert data["resolution_detail"] == "all good"
    assert data["resolved_at"]  # populated


def test_mark_resolved_removes_request_from_pending_listing(sessions_dir):
    path = _write_request(sessions_dir)
    mark_resolved(_load(path), "denied", "no")
    assert read_session_requests("sess-1") == []


# --- request_to_changes -----------------------------------------------------


def test_request_to_changes_mount():
    req = AgentRequest(
        request_id="r", session_id="s", kind="mount",
        params={"name": "documents", "mode": "ro"}, reason="", status="pending",
        created_at="", path=Path("/x"),
    )
    changes = request_to_changes(req)
    assert isinstance(changes, Changes)
    assert changes.add_mounts[0].name == "documents"
    assert changes.add_mounts[0].mode == "ro"


def test_request_to_changes_extend():
    req = AgentRequest(
        request_id="r", session_id="s", kind="extend",
        params={"duration": "30m"}, reason="", status="pending",
        created_at="", path=Path("/x"),
    )
    assert request_to_changes(req).extend_seconds == 1800


def test_request_to_changes_rejects_mount_without_name():
    req = AgentRequest(
        request_id="r", session_id="s", kind="mount",
        params={}, reason="", status="pending", created_at="", path=Path("/x"),
    )
    with pytest.raises(ValueError, match="name"):
        request_to_changes(req)


# --- validate_request -------------------------------------------------------


@pytest.fixture
def mount_registry():
    return {
        "documents": Mount(
            name="documents", host_path=Path("/data/docs"),
            default_mode="ro", description="docs",
        ),
    }


def _extend_req(path=Path("/x"), duration="30m"):
    return AgentRequest(
        request_id="r", session_id="sess-1", kind="extend",
        params={"duration": duration}, reason="", status="pending",
        created_at="", path=path,
    )


def _mount_req(name="documents", path=Path("/x")):
    return AgentRequest(
        request_id="r", session_id="sess-1", kind="mount",
        params={"name": name, "mode": None}, reason="", status="pending",
        created_at="", path=path,
    )


def test_validate_request_accepts_valid_extend():
    assert validate_request(_extend_req()) is None


def test_validate_request_rejects_bad_duration():
    assert validate_request(_extend_req(duration="soon")) is not None


def test_validate_request_accepts_registered_in_policy_mount(monkeypatch, mount_registry):
    monkeypatch.setattr(reqs, "load_mounts", lambda: mount_registry)
    monkeypatch.setattr(
        reqs, "get_profile",
        lambda name: Profile("default", True, None, False, ""),
    )
    monkeypatch.setattr(reqs, "check_mount_path", lambda *a, **k: [])
    assert validate_request(_mount_req("documents")) is None


def test_validate_request_rejects_unregistered_mount(monkeypatch, mount_registry):
    monkeypatch.setattr(reqs, "load_mounts", lambda: mount_registry)
    err = validate_request(_mount_req("secrets"))
    assert err is not None
    assert "not registered" in err


def test_validate_request_rejects_broad_mount(monkeypatch, mount_registry):
    monkeypatch.setattr(reqs, "load_mounts", lambda: mount_registry)
    monkeypatch.setattr(
        reqs, "get_profile",
        lambda name: Profile("default", True, None, False, ""),
    )

    def _raise(*a, **k):
        raise SafetyViolation("broad folder")

    monkeypatch.setattr(reqs, "check_mount_path", _raise)
    err = validate_request(_mount_req("documents"))
    assert err is not None
    assert "broad-mount override" in err


def test_validate_request_handles_unloadable_registry(monkeypatch):
    def _raise():
        raise MountRegistryError("bad mounts.json")

    monkeypatch.setattr(reqs, "load_mounts", _raise)
    err = validate_request(_mount_req("documents"))
    assert err is not None
    assert "registry" in err


# --- process_request --------------------------------------------------------


def test_process_request_denies_on_validation_failure(sessions_dir, monkeypatch):
    path = _write_request(sessions_dir, kind="extend", params={"duration": "bad"})
    req = _load(path)

    def _must_not_run(*a, **k):
        raise AssertionError("adjust_session must not run for an invalid request")

    monkeypatch.setattr(reqs, "adjust_session", _must_not_run)
    result = process_request(req, lambda _diff: True)
    assert result.exit_code == 2
    assert json.loads(path.read_text())["status"] == "denied"


def test_process_request_applies_on_success(sessions_dir, monkeypatch):
    path = _write_request(sessions_dir, kind="extend")
    req = _load(path)
    monkeypatch.setattr(
        reqs, "adjust_session",
        lambda *a, **k: AdjustResult(exit_code=0, detail="adjusted"),
    )
    result = process_request(req, lambda _diff: True)
    assert result.exit_code == 0
    assert json.loads(path.read_text())["status"] == "applied"


def test_process_request_marks_denied_when_operator_declines(sessions_dir, monkeypatch):
    path = _write_request(sessions_dir, kind="extend")
    req = _load(path)
    monkeypatch.setattr(
        reqs, "adjust_session",
        lambda *a, **k: AdjustResult(exit_code=1, detail="cancelled"),
    )
    result = process_request(req, lambda _diff: False)
    assert result.exit_code == 1
    assert json.loads(path.read_text())["status"] == "denied"


def test_process_request_marks_error_on_adjust_failure(sessions_dir, monkeypatch):
    path = _write_request(sessions_dir, kind="extend")
    req = _load(path)
    monkeypatch.setattr(
        reqs, "adjust_session",
        lambda *a, **k: AdjustResult(exit_code=2, detail="docker stop failed"),
    )
    result = process_request(req, lambda _diff: True)
    assert result.exit_code == 2
    assert json.loads(path.read_text())["status"] == "error"


def test_process_request_passes_agent_initiated_to_adjust(sessions_dir, monkeypatch):
    path = _write_request(sessions_dir, kind="extend")
    req = _load(path)
    captured = {}

    def _fake_adjust(session_id, changes, approver, **kwargs):
        captured.update(kwargs)
        return AdjustResult(exit_code=0, detail="adjusted")

    monkeypatch.setattr(reqs, "adjust_session", _fake_adjust)
    process_request(req, lambda _diff: True)
    assert captured.get("agent_initiated") is True


# --- F-D-02: session_id derived from directory, not JSON ------------------


def test_load_request_uses_directory_session_id_not_json(sessions_dir):
    """A cell-spoofed session_id in the JSON must not drive request
    routing. The host owns the directory layout; that's the canonical
    binding."""
    # Real session is sess-victim; cell writes request claiming sess-attacker.
    real_session = "sess-victim"
    rdir = sessions_dir / real_session / "requests"
    rdir.mkdir(parents=True, exist_ok=True)
    path = rdir / "spoofreq.json"
    path.write_text(json.dumps({
        "request_id": "spoofreq",
        "session_id": "sess-attacker",  # forged — not what the dir says
        "kind": "extend",
        "params": {"duration": "30m"},
        "reason": "spoof attempt",
        "status": "pending",
    }))

    req = _load(path)
    # Canonical session_id MUST come from the directory, not the JSON.
    assert req.session_id == real_session


# --- F-D-05: cell-supplied status field is ignored -------------------------


def test_load_request_ignores_cell_supplied_applied_status(sessions_dir):
    """A cell that pre-writes status: applied in the request file must NOT
    cause the host to skip operator review. Without a host-side resolution,
    the request is "pending" regardless."""
    rdir = sessions_dir / "sess-1" / "requests"
    rdir.mkdir(parents=True, exist_ok=True)
    path = rdir / "preclaimed.json"
    path.write_text(json.dumps({
        "request_id": "preclaimed",
        "session_id": "sess-1",
        "kind": "extend",
        "params": {"duration": "30m"},
        "reason": "trying to pre-claim applied",
        "status": "applied",  # the forgery
    }))

    req = _load(path)
    # Status must come from the host-only authoritative store, which has
    # nothing for this request → pending.
    assert req.status == "pending"


# --- B4: mark_resolved audit-log race --------------------------------------


def test_mark_resolved_writes_audit_log_even_when_mirror_fails(
    sessions_dir, monkeypatch,
):
    """B4 regression: a cell-mirror write failure (disk-full, cell
    removed its requests/ dir, permission flake) must NOT silence the
    audit log. Previously the order was host → mirror → audit, so a
    mirror exception propagated and the audit-log append never ran.
    After the fix: host → audit → mirror (try/except), so the operator's
    durable record of the decision is preserved regardless."""
    path = _write_request(sessions_dir, request_id="mirror-fails")
    req = _load(path)

    # Redirect the audit log to a tmp file.
    audit_log = sessions_dir.parent / "audit.jsonl"
    from whizzard import session_log
    monkeypatch.setattr(session_log, "SESSIONS_LOG", audit_log)

    # Simulate a mirror-write failure by making the parent directory
    # read-only AFTER the resolutions store write succeeds. The
    # resolutions store lives outside this directory, so it lands; the
    # cell file rename inside this directory raises.
    real_replace = reqs.Path.replace

    def failing_replace(self, target):
        if self == path.with_name(f".{path.name}.tmp"):
            raise OSError("simulated mirror-write failure")
        return real_replace(self, target)

    monkeypatch.setattr(reqs.Path, "replace", failing_replace)

    # Must not raise — mark_resolved swallows the mirror failure now.
    reqs.mark_resolved(req, "denied", "operator declined")

    # Host-only resolution store landed:
    res_path = reqs._resolutions_path(req.session_id, req.request_id)
    assert res_path.exists()
    res_data = json.loads(res_path.read_text())
    assert res_data["status"] == "denied"

    # Audit log entry landed despite the mirror failure (the bug being
    # fixed):
    assert audit_log.exists()
    entry = json.loads(audit_log.read_text().splitlines()[0])
    assert entry["event"] == "session_request_resolved"
    assert entry["status"] == "denied"
    assert entry["request_id"] == "mirror-fails"


def test_mark_resolved_does_not_raise_on_mirror_failure(sessions_dir, monkeypatch):
    """B4: callers should not see a misleading exception from a mirror
    write failure — from the operator's perspective the resolution
    completed (host store + audit log both landed)."""
    path = _write_request(sessions_dir, request_id="silent-mirror-fail")
    req = _load(path)

    audit_log = sessions_dir.parent / "audit.jsonl"
    from whizzard import session_log
    monkeypatch.setattr(session_log, "SESSIONS_LOG", audit_log)

    def failing_write_text(self, *args, **kwargs):
        # Fail only the cell-mirror tmp write (lives under the per-session
        # requests/ dir), not the resolutions-store tmp write (lives under
        # STATE_DIR/request-resolutions/). Both go through atomic_write_text
        # now, so a name-prefix check alone is too broad.
        if self.name.startswith(".") and "requests" in self.parts:
            raise OSError("disk full")
        return original_write_text(self, *args, **kwargs)

    original_write_text = reqs.Path.write_text
    monkeypatch.setattr(reqs.Path, "write_text", failing_write_text)

    # Must not raise.
    reqs.mark_resolved(req, "error", "approve+apply failed")


# --- B3: cell cannot hide a resolved request by mangling kind --------------


def test_load_request_surfaces_resolved_request_when_cell_mangles_kind(sessions_dir):
    """B3 regression: a cell that overwrites its own request file post-
    resolution with `{"kind":"junk"}` previously made the resolved
    request invisible to `whiz request list --all` (the cell-supplied
    `kind` failed the VALID_KINDS gate before the resolutions store
    was consulted). After the fix, the host-only resolutions store is
    consulted first; if a resolution exists, its canonical kind wins
    and the cell-supplied kind is ignored."""
    rdir = sessions_dir / "sess-1" / "requests"
    rdir.mkdir(parents=True, exist_ok=True)
    path = rdir / "denied-request.json"
    # First write the request as it appeared at submission time.
    path.write_text(json.dumps({
        "request_id": "denied-request",
        "session_id": "sess-1",
        "kind": "extend",
        "params": {"duration": "30m"},
        "reason": "needed more time",
        "status": "pending",
        "created_at": "2026-05-21T00:00:00+00:00",
    }))
    # Host records the operator's denial.
    res = reqs._resolutions_path("sess-1", "denied-request")
    res.parent.mkdir(parents=True, exist_ok=True)
    res.write_text(json.dumps({
        "request_id": "denied-request",
        "session_id": "sess-1",
        "kind": "extend",
        "params": {"duration": "30m"},
        "reason": "needed more time",
        "status": "denied",
        "resolution_detail": "operator declined",
        "resolved_at": "2026-05-21T00:00:30+00:00",
    }))
    # Malicious cell repaints its own file to hide the denial from listing.
    path.write_text(json.dumps({
        "request_id": "denied-request",
        "session_id": "sess-1",
        "kind": "junk",
        "params": {"whatever": "tampered"},
        "reason": "tampered",
        "status": "pending",
    }))

    req = _load(path)
    # Host-canonical record wins: kind, params, reason, status all come
    # from the resolutions store, not the cell.
    assert req.kind == "extend"
    assert req.params == {"duration": "30m"}
    assert req.reason == "needed more time"
    assert req.status == "denied"
    assert req.resolution_detail == "operator declined"


def test_load_request_still_rejects_pending_request_with_invalid_kind(sessions_dir):
    """B3: the kind-validity gate still applies to PENDING requests
    (no host resolution exists yet). Cell can't sneak unknown kinds
    past the listing logic for un-resolved requests."""
    rdir = sessions_dir / "sess-1" / "requests"
    rdir.mkdir(parents=True, exist_ok=True)
    path = rdir / "bogus.json"
    path.write_text(json.dumps({
        "request_id": "bogus",
        "session_id": "sess-1",
        "kind": "junk",  # not in VALID_KINDS
        "params": {},
        "reason": "",
        "status": "pending",
    }))
    # No resolution record written → pending request → kind gate applies.
    assert reqs._load_request(path) is None


# --- F-D-03: denials emit a session_request_resolved event ----------------


def test_mark_resolved_denied_emits_audit_event(sessions_dir, monkeypatch):
    """An operator denial must land in the host audit log — the cell can
    edit the request file to reset status, but the audit log is host-only
    and durable."""
    path = _write_request(sessions_dir, request_id="denyme", kind="extend")
    req = _load(path)

    # Redirect the audit log to a tmp file.
    audit_log = sessions_dir.parent / "audit.jsonl"
    from whizzard import session_log
    monkeypatch.setattr(session_log, "SESSIONS_LOG", audit_log)

    reqs.mark_resolved(req, "denied", "operator declined")

    assert audit_log.exists()
    entry = json.loads(audit_log.read_text().splitlines()[0])
    assert entry["event"] == "session_request_resolved"
    assert entry["status"] == "denied"
    assert entry["request_id"] == "denyme"
    assert entry["origin"] == "whizzard"


def test_mark_resolved_applied_does_not_duplicate_audit(sessions_dir, monkeypatch):
    """`adjust._log_adjustment` already logs applied changes; we must not
    duplicate the event from mark_resolved."""
    path = _write_request(sessions_dir, request_id="applyme", kind="extend")
    req = _load(path)

    audit_log = sessions_dir.parent / "audit.jsonl"
    from whizzard import session_log
    monkeypatch.setattr(session_log, "SESSIONS_LOG", audit_log)

    reqs.mark_resolved(req, "applied", "approved and applied")

    # No session_request_resolved event for applied — adjust._log_adjustment
    # is the canonical event source for that path.
    if audit_log.exists():
        for line in audit_log.read_text().splitlines():
            entry = json.loads(line)
            assert entry["event"] != "session_request_resolved"


def test_mark_resolved_writes_to_host_only_resolutions_store(sessions_dir):
    """The resolutions store is under STATE_DIR (host-only) — outside the
    cell-writable /run/whiz mount. mark_resolved must put the authoritative
    record there."""
    path = _write_request(sessions_dir, request_id="storetest", kind="extend")
    req = _load(path)

    reqs.mark_resolved(req, "denied", "policy")

    res_path = reqs._resolutions_path(req.session_id, "storetest")
    assert res_path.exists()
    data = json.loads(res_path.read_text())
    assert data["status"] == "denied"
    assert data["resolution_detail"] == "policy"


# --- F-E-02: cell cannot repaint kind/params after resolution -------------


def test_resolved_request_kind_and_params_come_from_host_store_not_cell_file(
    sessions_dir,
):
    """After a request is resolved, the cell can overwrite its request
    file with a different kind/params payload. The host-side view must
    show the *original* kind/params snapshotted at resolution time, not
    the cell-controlled current content of the file. Closes the
    repaint-on-resolved attack F-E-02."""
    # 1. Cell writes a benign request and the host approves it.
    rdir = sessions_dir / "sess-1" / "requests"
    rdir.mkdir(parents=True, exist_ok=True)
    path = rdir / "repaint.json"
    benign = {
        "request_id": "repaint",
        "kind": "extend",
        "params": {"duration": "30m"},
        "reason": "small bump",
        "status": "pending",
        "created_at": "2026-05-23T00:00:00+00:00",
    }
    path.write_text(json.dumps(benign))

    benign_req = _load(path)
    reqs.mark_resolved(benign_req, "applied", "approved 30m extension")

    # 2. Cell repaints the file with a much larger ask, same request_id.
    repainted = dict(benign)
    repainted["kind"] = "extend"
    repainted["params"] = {"duration": "999h"}  # the forgery
    repainted["reason"] = "see, this is what was approved"
    path.write_text(json.dumps(repainted))

    # 3. Host-side listing must see the original kind/params, not the
    # cell's repaint.
    listed = _load(path)
    assert listed.status == "applied"  # resolution is preserved
    assert listed.params == {"duration": "30m"}  # NOT 999h
    assert listed.reason == "small bump"  # NOT the cell's revised reason
    assert listed.kind == "extend"


def test_pending_request_reads_kind_and_params_from_cell_file(sessions_dir):
    """The host-store override only applies to resolved requests; pending
    requests still use the cell-supplied fields (there's nothing yet
    snapshotted to override against)."""
    rdir = sessions_dir / "sess-1" / "requests"
    rdir.mkdir(parents=True, exist_ok=True)
    path = rdir / "freshreq.json"
    path.write_text(json.dumps({
        "request_id": "freshreq",
        "kind": "mount",
        "params": {"name": "documents", "mode": "ro"},
        "reason": "need to read docs",
        "status": "pending",
        "created_at": "2026-05-23T00:00:00+00:00",
    }))

    req = _load(path)
    assert req.status == "pending"
    assert req.kind == "mount"
    assert req.params == {"name": "documents", "mode": "ro"}
    assert req.reason == "need to read docs"
