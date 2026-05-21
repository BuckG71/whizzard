"""Stage 13 — `oiq adjust` library-layer tests.

Cover the pure-Python pieces (Changes, parse_duration, no-op detection,
diff rendering, agent-denied filter, error-message rendering) plus the
adjust_session orchestration with a stub relauncher and mocked Docker
calls. Real Docker stop+relaunch is exercised by the integration tier.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from whizzard.adjust import (
    AGENT_DENIED_CHANGES,
    Changes,
    MountAddition,
    ResolutionStatus,
    SessionResolution,
    _apply_changes,
    _harness_from_argv,
    _resolution_error_message,
    adjust_session,
    check_agent_allowed,
    detect_noops,
    parse_duration,
    render_diff,
    resolve_session,
)

# --- Changes / MountAddition basics ----------------------------------------


def test_changes_empty_detection():
    assert Changes().is_empty()
    assert not Changes(extend_seconds=60).is_empty()
    assert not Changes(remove_mounts=("foo",)).is_empty()


def test_changes_narrowing_only():
    # remove-only is narrowing
    assert Changes(remove_mounts=("foo",)).is_narrowing_only()
    # adds + removes is NOT narrowing-only
    c = Changes(add_mounts=(MountAddition("x"),), remove_mounts=("foo",))
    assert not c.is_narrowing_only()
    # extend on its own is not narrowing
    assert not Changes(extend_seconds=60).is_narrowing_only()
    # allow-broad-mount on its own is not narrowing
    assert not Changes(allow_broad_mount=True).is_narrowing_only()
    # empty is not narrowing (nothing to narrow)
    assert not Changes().is_narrowing_only()


# --- parse_duration ---------------------------------------------------------


@pytest.mark.parametrize("spec,expected", [
    ("30m", 1800),
    ("30 min", 1800),
    ("90s", 90),
    ("90 sec", 90),
    ("2h", 7200),
    ("2 hr", 7200),
    ("3600", 3600),  # bare int = seconds
])
def test_parse_duration_valid(spec: str, expected: int):
    assert parse_duration(spec) == expected


@pytest.mark.parametrize("spec", ["", "foo", "30x", "30 weeks", "-5m"])
def test_parse_duration_rejects_invalid(spec: str):
    with pytest.raises(ValueError):
        parse_duration(spec)


# --- Agent denied list ------------------------------------------------------


def test_agent_denied_includes_allow_broad_mount():
    assert "allow_broad_mount" in AGENT_DENIED_CHANGES


def test_check_agent_allowed_blocks_broad_mount():
    denied = check_agent_allowed(Changes(allow_broad_mount=True))
    assert denied is not None
    assert denied.field == "allow_broad_mount"


def test_check_agent_allowed_passes_safe_changes():
    safe = Changes(
        add_mounts=(MountAddition("foo"),),
        remove_mounts=("bar",),
        extend_seconds=300,
    )
    assert check_agent_allowed(safe) is None


# --- Harness extraction -----------------------------------------------------


def test_harness_from_argv_parses_label():
    argv = ["docker", "run", "--label", "whizzard.harness=hermes-cell", "image"]
    assert _harness_from_argv(argv) == "hermes-cell"


def test_harness_from_argv_returns_none_when_label_missing():
    assert _harness_from_argv(["docker", "run", "image"]) is None


# --- No-op detection --------------------------------------------------------


def _start_event(*, mounts: list[dict], duration: int | None = None) -> dict:
    return {
        "event": "session_start",
        "session_id": "abcd1234",
        "profile": "default",
        "mounts": mounts,
        "duration_limit_seconds": duration,
        "image_tag": "whizzard-base:latest",
        "argv": ["docker", "run", "--label", "whizzard.harness=generic"],
        "allow_broad_mount": False,
    }


def test_detect_noops_drops_already_attached_add():
    event = _start_event(mounts=[{"name": "foo", "mode": "rw"}])
    changes = Changes(add_mounts=(MountAddition("foo"),))
    effective, warnings = detect_noops(changes, event)
    assert effective.is_empty()
    assert any("already attached" in w for w in warnings)


def test_detect_noops_drops_not_present_remove():
    event = _start_event(mounts=[{"name": "foo", "mode": "rw"}])
    changes = Changes(remove_mounts=("bar",))
    effective, warnings = detect_noops(changes, event)
    assert effective.is_empty()
    assert any("not currently attached" in w for w in warnings)


def test_detect_noops_drops_extend_on_unlimited():
    event = _start_event(mounts=[], duration=None)
    changes = Changes(extend_seconds=300)
    effective, warnings = detect_noops(changes, event)
    assert effective.extend_seconds is None
    assert any("no duration limit" in w for w in warnings)


def test_detect_noops_keeps_effective_changes():
    event = _start_event(
        mounts=[{"name": "foo", "mode": "rw"}],
        duration=3600,
    )
    changes = Changes(
        add_mounts=(MountAddition("bar"),),     # new — keep
        remove_mounts=("foo",),                  # present — keep
        extend_seconds=600,                      # session has limit — keep
    )
    effective, warnings = detect_noops(changes, event)
    assert effective.add_mounts == (MountAddition("bar"),)
    assert effective.remove_mounts == ("foo",)
    assert effective.extend_seconds == 600
    assert warnings == []


# --- _apply_changes ---------------------------------------------------------


def test_apply_changes_merges_mounts_and_carries_harness():
    event = _start_event(
        mounts=[{"name": "alpha", "mode": "ro"}, {"name": "beta", "mode": "rw"}],
        duration=3600,
    )
    event["argv"] = ["docker", "run", "--label", "whizzard.harness=hermes-cell", "img"]
    event["preset"] = "hermes"

    changes = Changes(
        add_mounts=(MountAddition("gamma", "rw"),),
        remove_mounts=("alpha",),
    )

    params = _apply_changes(event, changes)
    assert "alpha:ro" not in params["mount_specs"]
    assert "beta:rw" in params["mount_specs"]
    assert "gamma:rw" in params["mount_specs"]
    assert params["harness"] == "hermes-cell"
    assert params["preset_name"] == "hermes"
    assert params["image"] == "whizzard-base:latest"


def test_apply_changes_propagates_allow_broad_mount():
    event = _start_event(mounts=[])
    event["allow_broad_mount"] = False
    params = _apply_changes(event, Changes(allow_broad_mount=True))
    assert params["allow_broad_mount"] is True


# --- render_diff -----------------------------------------------------------


def test_render_diff_shows_each_change_with_marker():
    changes = Changes(
        add_mounts=(MountAddition("foo", "rw"),),
        remove_mounts=("bar",),
        extend_seconds=1800,
        allow_broad_mount=True,
    )
    diff = render_diff(changes, "abcd1234efgh")
    assert "abcd1234efgh" in diff
    assert "+ mount  foo:rw" in diff
    assert "- mount  bar" in diff
    assert "extend duration by 30m" in diff
    assert "broad-mount" in diff


# --- resolve_session (mocked Docker label lookup) --------------------------


def test_resolve_session_returns_found_on_unique_match(monkeypatch):
    import whizzard.adjust as adj
    monkeypatch.setattr(
        adj, "_docker_label_lookup",
        lambda prefix: [("abcd1234-full-uuid", "container-xyz")],
    )
    result = resolve_session("abcd")
    assert result.status == ResolutionStatus.FOUND
    assert result.session_id == "abcd1234-full-uuid"
    assert result.container_id == "container-xyz"


def test_resolve_session_returns_ambiguous_on_multiple_matches(monkeypatch):
    import whizzard.adjust as adj
    monkeypatch.setattr(
        adj, "_docker_label_lookup",
        lambda prefix: [("aa1", "cid1"), ("aa2", "cid2")],
    )
    result = resolve_session("aa")
    assert result.status == ResolutionStatus.AMBIGUOUS_PREFIX
    assert len(result.candidates) == 2


def test_resolve_session_returns_ended_when_log_has_session_end(monkeypatch, tmp_path: Path):
    import whizzard.adjust as adj
    monkeypatch.setattr(adj, "_docker_label_lookup", lambda prefix: [])
    log = tmp_path / "sessions.jsonl"
    log.write_text(
        json.dumps({"event": "session_start", "session_id": "abcd1234"}) + "\n"
        + json.dumps({"event": "session_end", "session_id": "abcd1234",
                      "end_time": "2026-05-19T22:00Z"}) + "\n"
    )
    monkeypatch.setattr(adj, "SESSIONS_LOG", log)

    result = resolve_session("abcd")
    assert result.status == ResolutionStatus.ENDED
    assert result.session_id == "abcd1234"
    assert "22:00" in (result.ended_at or "")


def test_resolve_session_returns_crashed_when_no_session_end(monkeypatch, tmp_path: Path):
    import whizzard.adjust as adj
    monkeypatch.setattr(adj, "_docker_label_lookup", lambda prefix: [])
    log = tmp_path / "sessions.jsonl"
    log.write_text(json.dumps({"event": "session_start", "session_id": "abcd1234"}) + "\n")
    monkeypatch.setattr(adj, "SESSIONS_LOG", log)

    result = resolve_session("abcd")
    assert result.status == ResolutionStatus.CRASHED


def test_resolve_session_returns_not_found_with_recent_suggestions(monkeypatch, tmp_path: Path):
    import whizzard.adjust as adj
    monkeypatch.setattr(adj, "_docker_label_lookup", lambda prefix: [])
    log = tmp_path / "sessions.jsonl"
    log.write_text(
        json.dumps({"event": "session_start", "session_id": "11111111-aaaa"}) + "\n"
        + json.dumps({"event": "session_start", "session_id": "22222222-bbbb"}) + "\n"
    )
    monkeypatch.setattr(adj, "SESSIONS_LOG", log)

    result = resolve_session("zzz")
    assert result.status == ResolutionStatus.NOT_FOUND
    assert "22222222" in result.candidates[0]
    assert "11111111" in result.candidates[1]


# --- Error message rendering ----------------------------------------------


def test_resolution_error_message_for_ambiguous():
    r = SessionResolution(
        status=ResolutionStatus.AMBIGUOUS_PREFIX,
        candidates=("aaaa1111", "aaaa2222"),
    )
    msg = _resolution_error_message(r, "aaaa")
    assert "ambiguous" in msg
    assert "aaaa1111" in msg


def test_resolution_error_message_for_ended():
    r = SessionResolution(
        status=ResolutionStatus.ENDED,
        session_id="abcd",
        ended_at="2026-05-19T22:00Z",
    )
    msg = _resolution_error_message(r, "abcd")
    assert "ended" in msg
    assert "oiq r" in msg


def test_resolution_error_message_for_not_found_offers_recent():
    r = SessionResolution(
        status=ResolutionStatus.NOT_FOUND,
        candidates=("11111111", "22222222"),
    )
    msg = _resolution_error_message(r, "zzz")
    assert "no session matching" in msg
    assert "11111111" in msg


# --- adjust_session orchestration (end-to-end with stubs) -------------------


def test_adjust_session_rejects_empty_changes():
    result = adjust_session("anything", Changes(), approver=lambda d: True)
    assert result.exit_code == 2
    assert "no changes" in result.detail


def test_adjust_session_rejects_agent_initiated_broad_mount():
    result = adjust_session(
        "anything",
        Changes(allow_broad_mount=True, add_mounts=(MountAddition("foo"),)),
        approver=lambda d: True,
        agent_initiated=True,
    )
    assert result.exit_code == 2
    assert "agent cannot" in result.detail


def test_adjust_session_surfaces_resolution_error_when_not_found(monkeypatch, tmp_path):
    import whizzard.adjust as adj
    monkeypatch.setattr(adj, "_docker_label_lookup", lambda prefix: [])
    monkeypatch.setattr(adj, "SESSIONS_LOG", tmp_path / "sessions.jsonl")

    result = adjust_session(
        "abcd",
        Changes(add_mounts=(MountAddition("foo"),)),
        approver=lambda d: True,
    )
    assert result.exit_code == 2
    assert "no session matching" in result.detail


def test_adjust_session_runs_through_with_stubbed_relauncher(monkeypatch, tmp_path):
    """Full happy-path orchestration with stubbed Docker calls + relauncher."""
    import whizzard.adjust as adj

    # Resolve to a running container
    monkeypatch.setattr(
        adj, "_docker_label_lookup",
        lambda prefix: [("abcd1234", "container-xyz")],
    )
    # Write a matching session_start in the log
    log = tmp_path / "sessions.jsonl"
    log.write_text(json.dumps({
        "event": "session_start",
        "session_id": "abcd1234",
        "profile": "default",
        "mounts": [{"name": "alpha", "mode": "rw"}],
        "duration_limit_seconds": 3600,
        "image_tag": "whizzard-base:latest",
        "argv": ["docker", "run", "--label", "whizzard.harness=generic"],
        "allow_broad_mount": False,
    }) + "\n")
    monkeypatch.setattr(adj, "SESSIONS_LOG", log)
    # Stub out the actual docker stop call
    monkeypatch.setattr(adj, "_stop_container", lambda cid, grace_seconds=30: (0, ""))

    # Capture what params the relauncher receives
    captured: dict = {}

    def fake_relauncher(params: dict) -> int:
        captured.update(params)
        return 0

    result = adjust_session(
        "abcd",
        Changes(add_mounts=(MountAddition("beta", "rw"),)),
        approver=lambda diff: True,
        relauncher=fake_relauncher,
    )
    assert result.exit_code == 0
    assert "beta:rw" in captured["mount_specs"]
    assert "alpha:rw" in captured["mount_specs"]  # carried forward
    assert captured["profile_name"] == "default"
    assert captured["harness"] == "generic"


def test_adjust_session_cancelled_when_approver_returns_false(monkeypatch, tmp_path):
    import whizzard.adjust as adj
    monkeypatch.setattr(
        adj, "_docker_label_lookup",
        lambda prefix: [("abcd1234", "cid")],
    )
    log = tmp_path / "sessions.jsonl"
    log.write_text(json.dumps({
        "event": "session_start",
        "session_id": "abcd1234",
        "profile": "default",
        "mounts": [],
        "duration_limit_seconds": 3600,
        "image_tag": "whizzard-base:latest",
        "argv": ["docker", "run", "--label", "whizzard.harness=generic"],
        "allow_broad_mount": False,
    }) + "\n")
    monkeypatch.setattr(adj, "SESSIONS_LOG", log)
    monkeypatch.setattr(adj, "_stop_container", lambda *a, **kw: (0, ""))

    relauncher_called = False

    def fake_relauncher(params: dict) -> int:
        nonlocal relauncher_called
        relauncher_called = True
        return 0

    result = adjust_session(
        "abcd",
        Changes(add_mounts=(MountAddition("foo"),)),
        approver=lambda d: False,  # USER SAYS NO
        relauncher=fake_relauncher,
    )
    assert result.exit_code == 1
    assert "cancelled" in result.detail
    assert relauncher_called is False, "relauncher should not run when approver denies"


def test_adjust_session_skips_approval_for_narrowing_only(monkeypatch, tmp_path):
    import whizzard.adjust as adj
    monkeypatch.setattr(
        adj, "_docker_label_lookup",
        lambda prefix: [("abcd1234", "cid")],
    )
    log = tmp_path / "sessions.jsonl"
    log.write_text(json.dumps({
        "event": "session_start",
        "session_id": "abcd1234",
        "profile": "default",
        "mounts": [{"name": "alpha", "mode": "rw"}],
        "duration_limit_seconds": 3600,
        "image_tag": "whizzard-base:latest",
        "argv": ["docker", "run", "--label", "whizzard.harness=generic"],
        "allow_broad_mount": False,
    }) + "\n")
    monkeypatch.setattr(adj, "SESSIONS_LOG", log)
    monkeypatch.setattr(adj, "_stop_container", lambda *a, **kw: (0, ""))

    approver_calls: list[str] = []

    def fake_approver(diff: str) -> bool:
        approver_calls.append(diff)
        return True

    result = adjust_session(
        "abcd",
        Changes(remove_mounts=("alpha",)),  # narrowing-only
        approver=fake_approver,
        relauncher=lambda p: 0,
    )
    assert result.exit_code == 0
    assert approver_calls == [], "narrowing-only should skip the approval prompt"


def test_adjust_session_early_exits_when_all_changes_are_noops(monkeypatch, tmp_path):
    import whizzard.adjust as adj
    monkeypatch.setattr(
        adj, "_docker_label_lookup",
        lambda prefix: [("abcd1234", "cid")],
    )
    log = tmp_path / "sessions.jsonl"
    log.write_text(json.dumps({
        "event": "session_start",
        "session_id": "abcd1234",
        "profile": "default",
        "mounts": [{"name": "foo", "mode": "rw"}],
        "duration_limit_seconds": None,  # unlimited
        "image_tag": "whizzard-base:latest",
        "argv": ["docker", "run", "--label", "whizzard.harness=generic"],
        "allow_broad_mount": False,
    }) + "\n")
    monkeypatch.setattr(adj, "SESSIONS_LOG", log)

    relauncher_called = False

    def fake_relauncher(params: dict) -> int:
        nonlocal relauncher_called
        relauncher_called = True
        return 0

    result = adjust_session(
        "abcd",
        Changes(
            add_mounts=(MountAddition("foo"),),  # already attached → no-op
            extend_seconds=300,                  # unlimited session → no-op
        ),
        approver=lambda d: True,
        relauncher=fake_relauncher,
    )
    assert result.exit_code == 0
    assert "already attached" in result.detail or "no duration" in result.detail
    assert relauncher_called is False
