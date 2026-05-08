"""Stage 1 + Stage 2: docker run argv construction."""

from pathlib import Path

from warlock.config import get_profile
from warlock.docker_cmd import build_run_argv
from warlock.mounts import Mount


def test_argv_drops_capabilities_and_blocks_root():
    argv = build_run_argv(get_profile("default"))
    joined = " ".join(argv)
    assert "--cap-drop=ALL" in argv
    assert "--user" in argv and "warlock" in argv
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
    assert "/home/" not in joined or "/home/warlock" in joined  # only the in-container home is allowed


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
    assert "warlock.profile=build" in joined


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
    assert "warlock.mount.research=ro" in " ".join(argv)


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
