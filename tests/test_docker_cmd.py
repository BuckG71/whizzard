"""Stage 1: docker run argv construction."""

from warlock.config import get_profile
from warlock.docker_cmd import build_run_argv


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
