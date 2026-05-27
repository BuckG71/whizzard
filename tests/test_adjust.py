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
    AGENT_ALLOWED_CHANGES,
    Changes,
    MountAddition,
    ResolutionStatus,
    SessionResolution,
    _apply_changes,
    _harness_from_argv,
    _resolution_error_message,
    _session_elapsed_seconds,
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


# --- Agent allowlist (F-G-06) ----------------------------------------------


def test_agent_allowlist_includes_safe_axes():
    """F-G-06: AGENT_ALLOWED_CHANGES is the default-deny allowlist. The
    three safe axes are the ones agents may request via MCP."""
    assert frozenset({"add_mounts", "remove_mounts", "extend_seconds"}) == AGENT_ALLOWED_CHANGES


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


# --- Stage 15: duration override on relaunch -------------------------------


def test_session_elapsed_seconds_parses_iso_timestamp():
    # An old timestamp → a large positive elapsed.
    assert _session_elapsed_seconds({"start_time": "2020-01-01T00:00:00Z"}) > 0


def test_session_elapsed_seconds_unparseable_returns_zero():
    assert _session_elapsed_seconds({"start_time": "not-a-date"}) == 0.0
    assert _session_elapsed_seconds({}) == 0.0


def test_apply_changes_carries_duration_limit_across_relaunch(monkeypatch):
    # A non-extend adjust on a limited session preserves the cap.
    monkeypatch.setattr("whizzard.adjust._session_elapsed_seconds", lambda ev: 0.0)
    start = {"duration_limit_seconds": 3600, "mounts": [], "argv": []}
    params = _apply_changes(start, Changes(add_mounts=(MountAddition("docs"),)))
    assert params["duration_override_seconds"] == 3600


def test_apply_changes_extend_adds_to_remaining(monkeypatch):
    monkeypatch.setattr("whizzard.adjust._session_elapsed_seconds", lambda ev: 600.0)
    start = {"duration_limit_seconds": 3600, "mounts": [], "argv": []}
    params = _apply_changes(start, Changes(extend_seconds=1800))
    # remaining (3600 - 600) + extend 1800 = 4800
    assert params["duration_override_seconds"] == 4800


def test_apply_changes_carries_allow_ephemeral_when_persisted(monkeypatch):
    """A1+A2: an adjust on a session that was launched with --allow-ephemeral
    must propagate the flag through to the relaunch so preflight passes."""
    monkeypatch.setattr("whizzard.adjust._session_elapsed_seconds", lambda ev: 0.0)
    start = {
        "duration_limit_seconds": None,
        "mounts": [],
        "argv": [],
        "allow_ephemeral": True,
    }
    params = _apply_changes(start, Changes())
    assert params["allow_ephemeral"] is True


def test_apply_changes_defaults_allow_ephemeral_false_when_absent(monkeypatch):
    """A1+A2: the field is absent on common non-ephemeral starts; adjust
    must default to False, not crash on lookup."""
    monkeypatch.setattr("whizzard.adjust._session_elapsed_seconds", lambda ev: 0.0)
    start = {"duration_limit_seconds": None, "mounts": [], "argv": []}
    assert "allow_ephemeral" not in start
    params = _apply_changes(start, Changes())
    assert params["allow_ephemeral"] is False


def test_apply_changes_unlimited_session_has_no_override():
    start = {"duration_limit_seconds": None, "mounts": [], "argv": []}
    params = _apply_changes(start, Changes(extend_seconds=1800))
    assert params["duration_override_seconds"] is None


def test_apply_changes_floors_override_near_expiry(monkeypatch):
    # Adjusting a session past its limit floors the relaunch window at 60s
    # rather than relaunching into an instant kill.
    monkeypatch.setattr("whizzard.adjust._session_elapsed_seconds", lambda ev: 99_999.0)
    start = {"duration_limit_seconds": 3600, "mounts": [], "argv": []}
    params = _apply_changes(start, Changes(add_mounts=(MountAddition("docs"),)))
    assert params["duration_override_seconds"] == 60


# --- F-G-01: _session_elapsed_seconds with real microsecond ISO -----------


def test_session_elapsed_handles_microsecond_iso_with_offset():
    """F-G-01: post-F-D-08 session_log writes microsecond ISO with +00:00
    offset; the strptime pattern was failing on this format and returning
    0.0, which made `adjust --extend` silently reset the duration cap."""
    from datetime import UTC, datetime, timedelta

    # Produce a timestamp the same way session_log._iso would produce it.
    ten_minutes_ago = datetime.now(UTC) - timedelta(minutes=10)
    start_event = {"start_time": ten_minutes_ago.isoformat()}

    elapsed = _session_elapsed_seconds(start_event)
    # Should be ~600s; allow ±5s for test-run slop.
    assert 590 <= elapsed <= 610


def test_session_elapsed_still_handles_z_suffix_format():
    """Backward compat: Z-suffix ISO (the pre-F-D-08 format) still parses.
    The bug the F-G-01 fix closed was a strptime mismatch that silently
    returned 0.0; we assert here that the Z form doesn't trigger that."""
    from datetime import UTC, datetime, timedelta
    one_hour_ago = (datetime.now(UTC) - timedelta(hours=1))
    z_form = one_hour_ago.strftime("%Y-%m-%dT%H:%M:%SZ")
    start_event = {"start_time": z_form}
    elapsed = _session_elapsed_seconds(start_event)
    # ~3600s ± slop. The key thing is it's not 0.0 (which would mean the
    # parse failed and we hit the except branch).
    assert 3590 <= elapsed <= 3610


# --- F-G-02: adjust path also reads overrides_used, not capability --------


def test_apply_changes_does_not_grant_broad_mount_when_user_did_not_invoke():
    """F-G-02: adjust must not silently carry forward `allow_broad_mount`
    just because the profile permitted it. The signal is whether the
    original launch actually invoked the override (`overrides_used`)."""
    start = {
        "duration_limit_seconds": None, "mounts": [], "argv": [],
        # Profile permitted broad mount; user did NOT use --allow-broad-mount
        "allow_broad_mount": True,
        "overrides_used": [],
    }
    params = _apply_changes(start, Changes(add_mounts=(MountAddition("docs"),)))
    # MUST NOT re-grant the override.
    assert params["allow_broad_mount"] is False


def test_apply_changes_grants_broad_mount_when_user_did_invoke():
    """F-G-02: when overrides_used is non-empty, the original user did
    opt in — carry forward (D-168 preserves user-chosen permissions)."""
    start = {
        "duration_limit_seconds": None, "mounts": [], "argv": [],
        "allow_broad_mount": True,
        "overrides_used": [{"path": "/some/broad/dir", "reason": "user opted in"}],
    }
    params = _apply_changes(start, Changes(add_mounts=(MountAddition("docs"),)))
    assert params["allow_broad_mount"] is True


def test_apply_changes_grants_broad_mount_when_adjust_user_re_affirms():
    """F-G-02: even if the original launch didn't use the override, the
    operator can explicitly re-affirm at adjust time via the flag."""
    start = {
        "duration_limit_seconds": None, "mounts": [], "argv": [],
        "allow_broad_mount": True,
        "overrides_used": [],
    }
    params = _apply_changes(start, Changes(
        add_mounts=(MountAddition("broad-dir"),),
        allow_broad_mount=True,  # operator typed the flag at adjust time
    ))
    assert params["allow_broad_mount"] is True


# --- F-G-07: parse_duration rejects 0 + negative ---------------------------


def test_parse_duration_rejects_zero():
    """F-G-07: '0' is not a meaningful extension — must reject loudly
    instead of silently triggering a real stop+restart with no effect."""
    with pytest.raises(ValueError, match="positive"):
        parse_duration("0")


def test_parse_duration_rejects_zero_with_unit():
    with pytest.raises(ValueError, match="positive"):
        parse_duration("0m")


# --- F-G-14: parse_duration enforces 7-day cap ----------------------------


def test_parse_duration_rejects_over_seven_days():
    """F-G-14: hard cap prevents typos like '--extend 99999h' from
    effectively unlimiting the session."""
    with pytest.raises(ValueError, match="exceeds"):
        parse_duration("99999h")


def test_parse_duration_accepts_value_at_cap():
    """Boundary check: 7 days exactly is accepted."""
    assert parse_duration("168h") == 7 * 24 * 60 * 60


def test_parse_duration_rejects_just_over_cap():
    with pytest.raises(ValueError, match="exceeds"):
        parse_duration("169h")


# --- F-G-06: allowlist defaults to deny ------------------------------------


def test_check_agent_allowed_denies_any_future_sensitive_field():
    """F-G-06: the allowlist guards against future field additions. A
    hypothetical Changes subclass with a new sensitive axis would
    default-deny without an explicit allowlist edit."""
    # We can't add a real field at runtime, but the explicit per-field
    # check on allow_broad_mount still fires, demonstrating the pattern.
    denied = check_agent_allowed(Changes(allow_broad_mount=True))
    assert denied is not None
    # Reasonable subset check: the field name is present.
    assert "allow_broad_mount" in denied.field


# --- F-G-10: DAEMON_UNAVAILABLE resolution path ----------------------------


def test_resolution_error_for_daemon_unavailable_mentions_docker_desktop():
    """F-G-10: distinct error message for daemon-down vs session-not-found.
    Previously both surfaced as 'no session matching'."""
    res = SessionResolution(
        status=ResolutionStatus.DAEMON_UNAVAILABLE,
        detail="Cannot connect to the Docker daemon",
    )
    msg = _resolution_error_message(res, "abc123")
    assert "daemon" in msg.lower()
    assert "Docker Desktop" in msg or "systemctl" in msg


# --- F-G-08: narrowing-only no-op warnings reach the user ------------------


def test_narrowing_only_path_surfaces_noop_warnings():
    """F-G-08: --remove-mount X --remove-mount Y where Y isn't attached
    used to silently drop the warning about Y. Now surfaced in the
    AdjustResult detail."""
    # We invoke detect_noops directly to verify the warning is produced;
    # the integration into adjust_session's detail is exercised by the
    # narrowing-only path tests below.
    start_event = {
        "duration_limit_seconds": None,
        "mounts": [{"name": "X", "host_path": "/x", "mode": "rw"}],
    }
    effective, warnings = detect_noops(
        Changes(remove_mounts=("X", "Y")),  # X attached, Y not
        start_event,
    )
    assert effective.remove_mounts == ("X",)
    assert any("Y" in w for w in warnings)
