"""Stages 1, 2, 5, 7: docker run argv construction."""

from pathlib import Path

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


def test_argv_includes_mcp_mounts_for_hermes_with_session_id(tmp_path, monkeypatch):
    from whizzard.adapters import HermesAdapter
    # Use a fresh WHIZZARD_HOME so the test doesn't write into the user's
    # real ~/.whizzard. Reload modules that captured the env at import time.
    import importlib
    import whizzard.config
    import whizzard.snapshot
    import whizzard.session_log
    import whizzard.docker_cmd
    monkeypatch.setenv("WHIZZARD_HOME", str(tmp_path))
    importlib.reload(whizzard.config)
    importlib.reload(whizzard.snapshot)
    importlib.reload(whizzard.session_log)
    importlib.reload(whizzard.docker_cmd)
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
