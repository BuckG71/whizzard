"""Stages 1, 2, 5, 7: docker run argv construction."""

import os
from pathlib import Path

import pytest

from whizzard.adapters import GenericShellAdapter
from whizzard.config import get_profile
from whizzard.docker_cmd import build_run_argv
from whizzard.mounts import Mount


def test_argv_drops_capabilities_and_blocks_root():
    argv = build_run_argv(get_profile("default"))
    joined = " ".join(argv)
    assert "--cap-drop=ALL" in argv
    assert "--user" in argv and "whizzard" in argv
    assert "--security-opt" in argv and "no-new-privileges" in joined
    assert "--read-only" in argv


def test_argv_no_docker_socket():
    argv = build_run_argv(get_profile("default"))
    assert "/var/run/docker.sock" not in " ".join(argv)


def test_argv_no_host_home_mount():
    argv = build_run_argv(get_profile("default"))
    joined = " ".join(argv)
    # No bind mount of typical host paths
    assert "/Users/" not in joined
    assert "/home/" not in joined or "/home/whizzard" in joined  # only the in-container home is allowed


def test_network_disabled_for_safe_profile():
    argv = build_run_argv(get_profile("safe"))
    assert "--network" in argv
    idx = argv.index("--network")
    assert argv[idx + 1] == "none"


def test_network_enabled_for_default_profile():
    """Default profile is network-on; --network none must NOT be present."""
    argv = build_run_argv(get_profile("default"))
    if "--network" in argv:
        idx = argv.index("--network")
        assert argv[idx + 1] != "none"


def _mediated_profile():
    from whizzard.config import Profile

    return Profile(
        name="med",
        network_enabled=True,
        duration_seconds=None,
        network_mode="mediated",
    )


def test_mediated_profile_joins_the_broker_network():
    # D-184: the cell attaches ONLY to the per-session broker network.
    argv = build_run_argv(_mediated_profile(), mediated_network="whiz-int-abc123")
    idx = argv.index("--network")
    assert argv[idx + 1] == "whiz-int-abc123"


def test_mediated_without_broker_network_fails_closed():
    # Building a mediated launch with no broker network is a programming error
    # (the caller must start the broker first) — refuse rather than fall through
    # to open egress.
    with pytest.raises(ValueError):
        build_run_argv(_mediated_profile())


def test_argv_includes_init_and_rm():
    argv = build_run_argv(get_profile("default"))
    assert "--init" in argv
    assert "--rm" in argv


def test_argv_labels_profile_name():
    argv = build_run_argv(get_profile("build"))
    joined = " ".join(argv)
    assert "whizzard.profile=build" in joined


# Stage 2 — mount argv

def test_argv_includes_volume_flag_for_each_resolved_mount():
    m = Mount(name="project-alpha", host_path=Path("/host/alpha"), default_mode="rw")
    argv = build_run_argv(
        get_profile("build"),
        resolved_mounts=[(m, "rw")],
    )
    assert "-v" in argv
    idx = argv.index("-v")
    assert argv[idx + 1] == "/host/alpha:/mounts/project-alpha:rw"


def test_argv_emits_mount_label_with_mode():
    m = Mount(name="research", host_path=Path("/host/research"), default_mode="ro")
    argv = build_run_argv(
        get_profile("default"),
        resolved_mounts=[(m, "ro")],
    )
    assert "whizzard.mount.research=ro" in " ".join(argv)


def test_argv_handles_multiple_mounts():
    a = Mount(name="alpha", host_path=Path("/host/a"), default_mode="rw")
    b = Mount(name="beta", host_path=Path("/host/b"), default_mode="ro")
    argv = build_run_argv(
        get_profile("build"),
        resolved_mounts=[(a, "rw"), (b, "ro")],
    )
    joined = " ".join(argv)
    assert "/host/a:/mounts/alpha:rw" in joined
    assert "/host/b:/mounts/beta:ro" in joined


def test_argv_no_volume_flag_when_no_mounts():
    argv = build_run_argv(get_profile("default"))
    assert "-v" not in argv


# Stage 5 — session id and cidfile

def test_argv_includes_session_id_label():
    argv = build_run_argv(get_profile("default"), session_id="sess-abc")
    assert "whizzard.session_id=sess-abc" in " ".join(argv)


def test_argv_includes_cidfile_when_provided(tmp_path: Path):
    cid = tmp_path / "cid.txt"
    argv = build_run_argv(get_profile("default"), cidfile=cid)
    assert "--cidfile" in argv
    idx = argv.index("--cidfile")
    assert argv[idx + 1] == str(cid)


def test_argv_omits_cidfile_when_not_provided():
    argv = build_run_argv(get_profile("default"))
    assert "--cidfile" not in argv


def test_argv_omits_session_label_when_no_session_id():
    argv = build_run_argv(get_profile("default"))
    assert "whizzard.session_id" not in " ".join(argv)


# Stage 7 — adapter-driven argv

def test_argv_default_adapter_runs_bash():
    argv = build_run_argv(get_profile("default"))
    # Image followed by start_command at the end of argv
    assert argv[-1] == "/bin/bash"


def test_argv_uses_adapter_start_command():
    adapter = GenericShellAdapter(config={"start_command": "/bin/zsh"})
    argv = build_run_argv(get_profile("default"), adapter=adapter)
    assert argv[-1] == "/bin/zsh"


def test_argv_uses_adapter_multi_arg_start_command():
    adapter = GenericShellAdapter(config={"start_command": "/bin/bash -l"})
    argv = build_run_argv(get_profile("default"), adapter=adapter)
    # Last two argv entries should be the split command
    assert argv[-2:] == ["/bin/bash", "-l"]


def test_argv_includes_adapter_env_vars():
    adapter = GenericShellAdapter(config={"env": {"K": "v"}})
    argv = build_run_argv(get_profile("default"), adapter=adapter)
    assert "-e" in argv
    assert "K=v" in argv


def test_argv_includes_adapter_working_dir():
    adapter = GenericShellAdapter(config={"working_dir": "/home/whizzard"})
    argv = build_run_argv(get_profile("default"), adapter=adapter)
    assert "-w" in argv
    idx = argv.index("-w")
    assert argv[idx + 1] == "/home/whizzard"


def test_argv_omits_w_flag_when_no_working_dir():
    argv = build_run_argv(get_profile("default"))
    assert "-w" not in argv


def test_argv_includes_harness_label():
    adapter = GenericShellAdapter(name="custom-harness")
    argv = build_run_argv(get_profile("default"), adapter=adapter)
    assert "whizzard.harness=custom-harness" in " ".join(argv)


def test_argv_default_harness_label_is_generic():
    argv = build_run_argv(get_profile("default"))
    assert "whizzard.harness=generic" in " ".join(argv)


# --- Stage 9: MCP mounts when the adapter opts in ----------------------


def test_argv_no_mcp_mounts_for_generic_adapter(tmp_path, monkeypatch):
    # GenericShellAdapter.mcp_env returns {} — no MCP mounts should appear.
    monkeypatch.setenv("WHIZZARD_HOME", str(tmp_path))
    argv = build_run_argv(get_profile("default"), session_id="sess-1")
    joined = " ".join(argv)
    assert "/run/whiz" not in joined


def test_argv_no_mcp_mounts_when_session_id_absent(tmp_path, monkeypatch):
    # Even with an MCP-capable adapter, without session_id no mounts go in.
    from whizzard.adapters import HermesAdapter
    monkeypatch.setenv("WHIZZARD_HOME", str(tmp_path))
    argv = build_run_argv(get_profile("default"), adapter=HermesAdapter())
    joined = " ".join(argv)
    assert "/run/whiz" not in joined


def test_argv_includes_mcp_mounts_for_hermes_with_session_id(
    tmp_path, monkeypatch, request,
):
    # Use a fresh WHIZZARD_HOME so the test doesn't write into the user's
    # real ~/.whizzard. The four modules below capture env at import time;
    # reload with the patched env, then reload AGAIN at teardown so the
    # module-level constants don't bleed into later tests in the suite
    # (M5 — caught during the S20 review when this leaked into the
    # safety hard-block list assertion).
    import importlib

    import whizzard.config
    import whizzard.docker_cmd
    import whizzard.session_log
    import whizzard.snapshot
    from whizzard.adapters import HermesAdapter

    _reload_modules = (
        whizzard.config,
        whizzard.snapshot,
        whizzard.session_log,
        whizzard.docker_cmd,
    )

    def _restore_module_state() -> None:
        # monkeypatch already restored the env var; reloading now picks
        # up the original WHIZZARD_HOME the user's environment had.
        for mod in _reload_modules:
            importlib.reload(mod)

    request.addfinalizer(_restore_module_state)

    monkeypatch.setenv("WHIZZARD_HOME", str(tmp_path))
    for mod in _reload_modules:
        importlib.reload(mod)
    from whizzard.docker_cmd import build_run_argv as build_run_argv_reloaded

    argv = build_run_argv_reloaded(
        get_profile("default"),
        adapter=HermesAdapter(),
        session_id="sess-mcp-1",
    )
    joined = " ".join(argv)

    # Per-session dir mounted at /run/whiz (rw)
    assert "/run/whiz:rw" in joined
    assert "sess-mcp-1" in joined  # session dir path contains session_id
    # Audit log mounted at /run/whiz/audit.jsonl (ro)
    assert "/run/whiz/audit.jsonl:ro" in joined
    # MCP env vars present
    assert "WHIZ_SNAPSHOT_PATH=/run/whiz/snapshot.json" in joined
    assert "WHIZ_SESSION_ID=sess-mcp-1" in joined

    # M7 smoke regression (2026-05-19): the audit.jsonl placeholder must be
    # pre-created inside the session dir BEFORE docker run, so the nested
    # bind mount (SESSIONS_LOG → /run/whiz/audit.jsonl, inside sess_dir at
    # /run/whiz) doesn't fail on Docker Desktop macOS with virtiofs.
    from whizzard.snapshot import session_dir as session_dir_reloaded
    audit_placeholder = session_dir_reloaded("sess-mcp-1") / "audit.jsonl"
    assert audit_placeholder.exists(), (
        "audit.jsonl placeholder must be pre-created in session dir to "
        "prevent runc 'mountpoint outside of rootfs' on macOS Docker Desktop"
    )

    # Stage 14: the agent request channel dir must be pre-created inside the
    # session dir so `whiz requests` finds an empty dir, not a missing one.
    request_channel = session_dir_reloaded("sess-mcp-1") / "requests"
    assert request_channel.is_dir()


# --- Stage 8 M6: harness mounts + UID parity ---


def test_argv_emits_hermes_home_mount_when_configured(tmp_path):
    from whizzard.adapters import HermesAdapter
    hermes_home = tmp_path / ".hermes-test"
    hermes_home.mkdir()
    argv = build_run_argv(
        get_profile("default"),
        adapter=HermesAdapter(config={"hermes_home": str(hermes_home)}),
    )
    joined = " ".join(argv)

    # as_posix(): the harness mount renders host paths with forward slashes
    # for Docker on Windows (str() would be backslashes there). Identical on
    # POSIX. Matches ContainerMount.docker_volume_arg.
    assert f"{hermes_home.as_posix()}:/home/whizzard/.hermes:rw" in joined
    assert "whizzard.harness_mount=/home/whizzard/.hermes=rw" in joined


def test_argv_no_harness_mount_for_generic_shell():
    argv = build_run_argv(get_profile("default"), adapter=GenericShellAdapter())
    joined = " ".join(argv)
    assert "whizzard.harness_mount" not in joined
    assert "/home/whizzard/.hermes" not in joined


@pytest.mark.skipif(
    os.name == "nt",
    reason="asserts POSIX uid:gid parity; os.getuid doesn't exist on Windows "
    "(the Windows fallback is covered by "
    "test_argv_uid_parity_falls_back_to_named_user_on_windows)",
)
def test_argv_uid_parity_overrides_user_and_tmpfs_when_hermes_mounted(tmp_path):
    import os

    from whizzard.adapters import HermesAdapter
    hermes_home = tmp_path / ".hermes-uid"
    hermes_home.mkdir()
    argv = build_run_argv(
        get_profile("default"),
        adapter=HermesAdapter(config={"hermes_home": str(hermes_home)}),
    )

    # --user should be host UID:GID, not the named whizzard user.
    user_idx = argv.index("--user")
    expected = f"{os.getuid()}:{os.getgid()}"
    assert argv[user_idx + 1] == expected

    # Home-dir tmpfs uid/gid must follow the --user override so the
    # container user can actually write to /home/whizzard.
    home_tmpfs = next(
        (a for a in argv if a.startswith("/home/whizzard:")), None
    )
    assert home_tmpfs is not None
    assert f"uid={os.getuid()},gid={os.getgid()}" in home_tmpfs


def test_argv_no_uid_parity_for_generic_shell_keeps_named_user():
    argv = build_run_argv(get_profile("default"), adapter=GenericShellAdapter())
    user_idx = argv.index("--user")
    assert argv[user_idx + 1] == "whizzard"
    home_tmpfs = next(
        (a for a in argv if a.startswith("/home/whizzard:")), None
    )
    assert home_tmpfs is not None
    assert "uid=1000,gid=1000" in home_tmpfs


def test_argv_uid_parity_falls_back_to_named_user_on_windows(tmp_path, monkeypatch):
    """Windows portability: `os.getuid` doesn't exist on Windows, and the
    UID-parity trick doesn't apply (Docker Desktop/WSL2 maps ownership).
    With os.name == 'nt', a uid_parity mount must fall back to the named
    `whizzard` user instead of calling os.getuid (which would crash)."""
    import whizzard.docker_cmd as dc
    from whizzard.adapters import HermesAdapter

    hermes_home = tmp_path / ".hermes-win"
    hermes_home.mkdir()

    # Simulate Windows via the host-platform indirection rather than the
    # global os.name. Monkeypatching os.name leaks into pytest's own path
    # handling: on a failing assertion, pytest's failure-repr instantiates
    # Path(os.getcwd()) -> WindowsPath, which raises NotImplementedError on
    # POSIX and turns a clean test failure into an INTERNALERROR (seen on
    # the 3.11 CI legs). Forcing the helper keeps the rest of the call under
    # the real platform. If the guard regresses, os.getuid() is still
    # present on this macOS/Linux test host, so also assert it isn't called.
    monkeypatch.setattr(dc, "is_windows", lambda: True)
    called = {"getuid": False}
    if hasattr(dc.os, "getuid"):
        real = dc.os.getuid
        def _tracking_getuid():
            called["getuid"] = True
            return real()
        monkeypatch.setattr(dc.os, "getuid", _tracking_getuid)

    argv = build_run_argv(
        get_profile("default"),
        adapter=HermesAdapter(config={"hermes_home": str(hermes_home)}),
    )

    user_idx = argv.index("--user")
    assert argv[user_idx + 1] == "whizzard", "should fall back to named user on Windows"
    assert called["getuid"] is False, "os.getuid must not be called on Windows"
    # Home tmpfs falls back to the baked-in 1000:1000.
    home_tmpfs = next((a for a in argv if a.startswith("/home/whizzard:")), None)
    assert home_tmpfs is not None and "uid=1000,gid=1000" in home_tmpfs


def test_is_pid_alive_posix_unaffected():
    """Regression: the POSIX liveness path still works after the Windows
    branch was added. (Windows ctypes branch is validated on the box.)"""
    import os

    from whizzard.adapters.hermes import _is_pid_alive

    assert _is_pid_alive(os.getpid()) is True
    # A pid that's almost certainly dead/unused.
    assert _is_pid_alive(2_000_000_000) is False


def test_argv_harness_mount_comes_after_user_mounts(tmp_path):
    """User mounts appear first; harness mounts emitted after, so a hostile
    or accidental user mount can't shadow a harness path."""
    from whizzard.adapters import HermesAdapter
    hermes_home = tmp_path / ".hermes-order"
    hermes_home.mkdir()
    user_mount = Mount(
        name="alpha", host_path=Path("/host/alpha"), default_mode="rw"
    )

    argv = build_run_argv(
        get_profile("default"),
        resolved_mounts=[(user_mount, "rw")],
        adapter=HermesAdapter(config={"hermes_home": str(hermes_home)}),
    )

    # Find positions of the two -v args; user mount must precede harness mount.
    v_positions = [i for i, a in enumerate(argv) if a == "-v"]
    user_pos = next(
        i for i in v_positions if "/host/alpha:" in argv[i + 1]
    )
    harness_pos = next(
        i for i in v_positions if hermes_home.as_posix() in argv[i + 1]
    )
    assert user_pos < harness_pos


# --- Stage 15: run_shell duration / idle enforcement wiring ---


def _isolated_run_shell_env(tmp_path, monkeypatch):
    """Stub out Docker + the monitor so run_shell can be exercised without a
    real container. Returns the temp session log path."""
    import json  # noqa: F401 -- used by callers via the returned log

    import whizzard.docker_cmd as dc
    from whizzard import session_log

    log = tmp_path / "sessions.jsonl"
    monkeypatch.setattr(session_log, "SESSIONS_LOG", log)
    monkeypatch.setattr(dc, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(dc, "docker_available", lambda: True)
    monkeypatch.setattr(dc, "image_exists", lambda *a, **k: True)
    monkeypatch.setattr(dc, "get_image_id", lambda *a, **k: "sha256:abc")

    class _FakeProc:
        def __init__(self, *a, **k):
            self.returncode = None

    monkeypatch.setattr(dc.subprocess, "Popen", _FakeProc)
    return dc, log


def test_run_shell_records_expiry_reason(tmp_path, monkeypatch):
    import json

    from whizzard.config import Profile
    dc, log = _isolated_run_shell_env(tmp_path, monkeypatch)

    def _stub_monitor(proc, **kwargs):
        proc.returncode = 137
        return "idle"

    monkeypatch.setattr(dc, "monitor_and_enforce", _stub_monitor)

    prof = Profile("safe", network_enabled=False, duration_seconds=1800,
                   idle_timeout_seconds=600)
    result = dc.run_shell(prof, adapter=GenericShellAdapter(), session_id="sess-15")

    assert result.exit_code == 137
    end = json.loads(log.read_text().splitlines()[-1])
    assert end["event"] == "session_end"
    assert end["expiry_reason"] == "idle"


def test_run_shell_logs_effective_duration_override(tmp_path, monkeypatch):
    import json

    from whizzard.config import Profile
    dc, log = _isolated_run_shell_env(tmp_path, monkeypatch)

    captured = {}

    def _stub_monitor(proc, **kwargs):
        captured.update(kwargs)
        proc.returncode = 0
        return "clean"

    monkeypatch.setattr(dc, "monitor_and_enforce", _stub_monitor)

    prof = Profile("build", network_enabled=True, duration_seconds=7200)
    dc.run_shell(prof, adapter=GenericShellAdapter(), session_id="sess-x",
                 duration_override_seconds=9000)

    # The --extend override wins over the profile's duration in both the
    # session_start log and the limit handed to the monitor.
    start = json.loads(log.read_text().splitlines()[0])
    assert start["duration_limit_seconds"] == 9000
    assert captured["duration_limit"] == 9000


# --- non-interactive launch flag ---


def test_argv_includes_it_by_default():
    argv = build_run_argv(get_profile("default"))
    assert "-it" in argv


def test_argv_omits_it_when_not_interactive():
    argv = build_run_argv(get_profile("default"), interactive=False)
    assert "-it" not in argv
    # the TTY toggle must not disturb the containment flags
    assert "--cap-drop=ALL" in argv
    assert "--read-only" in argv
    assert "--security-opt" in argv


# --- F-B-01: image_exists distinguishes daemon-down from image-missing ----


def test_image_exists_raises_when_daemon_unreachable(monkeypatch):
    """Daemon-down used to look identical to image-missing — silent UX bug."""
    import whizzard.docker_cmd as dc

    def fake_run(argv, **kwargs):
        return type("R", (), {
            "returncode": 1,
            "stdout": "",
            "stderr": "Cannot connect to the Docker daemon at "
                      "unix:///var/run/docker.sock. Is the docker daemon running?",
        })()

    monkeypatch.setattr(dc, "docker_available", lambda: True)
    monkeypatch.setattr(dc.subprocess, "run", fake_run)
    import pytest
    with pytest.raises(dc.DockerDaemonError, match="daemon is not reachable"):
        dc.image_exists("any:tag")


def _fake_info(returncode: int, stdout: str = "", stderr: str = ""):
    def run(argv, **kwargs):
        return type("R", (), {
            "returncode": returncode, "stdout": stdout, "stderr": stderr
        })()
    return run


def test_docker_daemon_status_classifies_states(monkeypatch):
    """The wizard preflight relies on a verified daemon state, not a PATH
    check. 'not running' must be distinguished from other docker failures
    (e.g. permission denied) so the wizard doesn't misadvise."""
    import whizzard.docker_cmd as dc

    monkeypatch.setattr(dc, "docker_available", lambda: False)
    assert dc.docker_daemon_status()[0] == "missing"

    monkeypatch.setattr(dc, "docker_available", lambda: True)

    # daemon-down signature → unreachable
    monkeypatch.setattr(dc.subprocess, "run", _fake_info(
        1, stderr="Cannot connect to the Docker daemon. Is the docker daemon running?"))
    assert dc.docker_daemon_status()[0] == "unreachable"

    # other non-zero (e.g. permission denied) → daemon_error, surfacing stderr
    monkeypatch.setattr(dc.subprocess, "run", _fake_info(
        1, stderr="permission denied while trying to connect to the Docker daemon socket"))
    status, detail = dc.docker_daemon_status()
    assert status == "daemon_error"
    assert "permission denied" in detail

    monkeypatch.setattr(dc.subprocess, "run", _fake_info(0, stdout="windows\n"))
    assert dc.docker_daemon_status()[0] == "windows_containers"

    monkeypatch.setattr(dc.subprocess, "run", _fake_info(0, stdout="linux\n"))
    assert dc.docker_daemon_status()[0] == "ok"

    # unexpected OSType is not silently accepted as ok
    monkeypatch.setattr(dc.subprocess, "run", _fake_info(0, stdout="freebsd\n"))
    assert dc.docker_daemon_status()[0] == "daemon_error"


def test_docker_daemon_status_timeout_is_unreachable(monkeypatch):
    """A mid-startup or unreachable-remote daemon must not hang the wizard."""
    import whizzard.docker_cmd as dc

    monkeypatch.setattr(dc, "docker_available", lambda: True)

    def _timeout(argv, **kwargs):
        raise dc.subprocess.TimeoutExpired(argv, 15)

    monkeypatch.setattr(dc.subprocess, "run", _timeout)
    status, detail = dc.docker_daemon_status()
    assert status == "unreachable"
    assert "timed out" in detail


def test_image_exists_returns_false_for_missing_image(monkeypatch):
    """Image-missing case still returns False — caller knows to suggest build."""
    import whizzard.docker_cmd as dc

    def fake_run(argv, **kwargs):
        return type("R", (), {
            "returncode": 1,
            "stdout": "",
            "stderr": "Error: No such image: whizzard:latest",
        })()

    monkeypatch.setattr(dc, "docker_available", lambda: True)
    monkeypatch.setattr(dc.subprocess, "run", fake_run)
    assert dc.image_exists("whizzard:latest") is False


def test_get_image_id_raises_when_daemon_unreachable(monkeypatch):
    import whizzard.docker_cmd as dc

    def fake_run(argv, **kwargs):
        return type("R", (), {
            "returncode": 1,
            "stdout": "",
            "stderr": "Cannot connect to the Docker daemon",
        })()

    monkeypatch.setattr(dc, "docker_available", lambda: True)
    monkeypatch.setattr(dc.subprocess, "run", fake_run)
    import pytest
    with pytest.raises(dc.DockerDaemonError):
        dc.get_image_id("any:tag")


# --- Stage 18: image_inspect helper ---


def test_image_inspect_parses_id_and_created(monkeypatch):
    import whizzard.docker_cmd as dc

    def fake_run(argv, **kwargs):
        return type("R", (), {
            "returncode": 0,
            "stdout": "sha256:abc123\t2025-09-12T18:42:11.123456789Z\n",
            "stderr": "",
        })()

    monkeypatch.setattr(dc, "docker_available", lambda: True)
    monkeypatch.setattr(dc.subprocess, "run", fake_run)
    meta = dc.image_inspect("whizzard-base:latest")
    assert meta is not None
    assert meta.id == "sha256:abc123"
    assert meta.created.year == 2025
    assert meta.created.month == 9
    assert meta.created.tzinfo is not None


def test_image_inspect_returns_none_when_image_missing(monkeypatch):
    import whizzard.docker_cmd as dc

    def fake_run(argv, **kwargs):
        return type("R", (), {
            "returncode": 1,
            "stdout": "",
            "stderr": "Error: No such image: whizzard:latest",
        })()

    monkeypatch.setattr(dc, "docker_available", lambda: True)
    monkeypatch.setattr(dc.subprocess, "run", fake_run)
    assert dc.image_inspect("whizzard:latest") is None


def test_image_inspect_raises_on_daemon_down(monkeypatch):
    import whizzard.docker_cmd as dc

    def fake_run(argv, **kwargs):
        return type("R", (), {
            "returncode": 1,
            "stdout": "",
            "stderr": "Cannot connect to the Docker daemon",
        })()

    monkeypatch.setattr(dc, "docker_available", lambda: True)
    monkeypatch.setattr(dc.subprocess, "run", fake_run)
    import pytest
    with pytest.raises(dc.DockerDaemonError):
        dc.image_inspect("whizzard:latest")


def test_image_inspect_handles_iso_without_fractional_seconds(monkeypatch):
    import whizzard.docker_cmd as dc

    def fake_run(argv, **kwargs):
        return type("R", (), {
            "returncode": 0,
            "stdout": "sha256:xyz\t2025-01-02T03:04:05Z\n",
            "stderr": "",
        })()

    monkeypatch.setattr(dc, "docker_available", lambda: True)
    monkeypatch.setattr(dc.subprocess, "run", fake_run)
    meta = dc.image_inspect("any:tag")
    assert meta is not None
    assert meta.created.hour == 3


# --- F-B-09: cidfile is unlinked even when the session path raises ---


def test_run_shell_cleans_cidfile_when_monitor_raises(tmp_path, monkeypatch):
    """If monitor_and_enforce raises, the cidfile must still be removed."""
    import pytest

    from whizzard.adapters import GenericShellAdapter
    from whizzard.config import Profile

    dc, _log = _isolated_run_shell_env(tmp_path, monkeypatch)

    def _boom(proc, **kwargs):
        # Simulate a host-side cidfile that docker has already created.
        cid_path = next((tmp_path / "state").glob("cid-*.txt"), None)
        if cid_path is not None:
            cid_path.write_text("ffeedd")
        raise KeyboardInterrupt

    monkeypatch.setattr(dc, "monitor_and_enforce", _boom)

    prof = Profile("safe", network_enabled=False, duration_seconds=60)
    with pytest.raises(KeyboardInterrupt):
        dc.run_shell(prof, adapter=GenericShellAdapter(), session_id="sess-fb09")

    # The cidfile must be gone — no orphans in STATE_DIR.
    orphans = list((tmp_path / "state").glob("cid-*.txt"))
    assert orphans == [], f"orphaned cidfiles: {orphans}"


def test_run_shell_cleans_cidfile_on_clean_exit(tmp_path, monkeypatch):
    """Cleanup path on the happy path is unchanged by the try/finally wrap."""
    from whizzard.adapters import GenericShellAdapter
    from whizzard.config import Profile

    dc, _log = _isolated_run_shell_env(tmp_path, monkeypatch)

    def _ok(proc, **kwargs):
        cid_path = next((tmp_path / "state").glob("cid-*.txt"), None)
        if cid_path is not None:
            cid_path.write_text("ddcc")
        proc.returncode = 0
        return "clean"

    monkeypatch.setattr(dc, "monitor_and_enforce", _ok)

    prof = Profile("safe", network_enabled=False, duration_seconds=60)
    dc.run_shell(prof, adapter=GenericShellAdapter(), session_id="sess-clean")

    orphans = list((tmp_path / "state").glob("cid-*.txt"))
    assert orphans == []
