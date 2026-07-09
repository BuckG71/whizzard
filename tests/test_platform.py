"""Tests for the dependency-free platform/Docker primitives."""

from __future__ import annotations

import os
from pathlib import PurePosixPath, PureWindowsPath

from whizzard._platform import (
    DAEMON_DOWN_INDICATORS,
    docker_host_path,
    is_windows,
    looks_like_daemon_error,
)


def test_is_windows_matches_os_name():
    assert is_windows() == (os.name == "nt")


def test_docker_host_path_uses_forward_slashes():
    # A Windows-style path renders with forward slashes for the -v spec.
    assert docker_host_path(PureWindowsPath(r"C:\Users\me\code")) == "C:/Users/me/code"
    # POSIX paths are unchanged.
    assert docker_host_path(PurePosixPath("/home/me/code")) == "/home/me/code"


def test_looks_like_daemon_error_matches_each_indicator():
    for token in DAEMON_DOWN_INDICATORS:
        assert looks_like_daemon_error(f"docker: {token} (is it running?)")


def test_looks_like_daemon_error_real_mac_message():
    stderr = (
        "Cannot connect to the Docker daemon at unix:///var/run/docker.sock. "
        "Is the docker daemon running?"
    )
    assert looks_like_daemon_error(stderr)


def test_looks_like_daemon_error_bad_docker_host_unix_socket():
    # Newer Docker CLIs (≥28) emit this verbatim when DOCKER_HOST points at a
    # missing unix socket. Regression: this used to fall through the matcher
    # and surface as "image not found — build it" instead of "start Docker".
    stderr = (
        "failed to connect to the docker API at "
        "unix:///nonexistent/docker.sock; check if the path is correct and "
        "if the daemon is running: dial unix /nonexistent/docker.sock: "
        "connect: no such file or directory"
    )
    assert looks_like_daemon_error(stderr)


def test_looks_like_daemon_error_ignores_unrelated_stderr():
    assert not looks_like_daemon_error("Error: No such image: whizzard:latest")
    assert not looks_like_daemon_error("")


# --- pick_directory: dispatch / parse / fallback (no real dialog opens) ----


class _Result:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _force_darwin(monkeypatch):
    from whizzard import _platform

    monkeypatch.setattr(_platform, "is_windows", lambda: False)
    monkeypatch.setattr(_platform.sys, "platform", "darwin")


def test_pick_directory_returns_chosen_path(monkeypatch):
    from whizzard import _platform

    _force_darwin(monkeypatch)
    monkeypatch.setattr(_platform.subprocess, "run", lambda *a, **k: _Result(0, "/Users/me/proj\n"))
    assert _platform.pick_directory() == "/Users/me/proj"


def test_pick_directory_none_on_cancel(monkeypatch):
    from whizzard import _platform

    _force_darwin(monkeypatch)
    monkeypatch.setattr(_platform.subprocess, "run", lambda *a, **k: _Result(1, "", "User canceled"))
    assert _platform.pick_directory() is None


def test_pick_directory_none_on_error(monkeypatch):
    from whizzard import _platform

    _force_darwin(monkeypatch)

    def boom(*a, **k):
        raise OSError("osascript missing")

    monkeypatch.setattr(_platform.subprocess, "run", boom)
    assert _platform.pick_directory() is None


def test_pick_directory_linux_without_dialog_tool_returns_none(monkeypatch):
    from whizzard import _platform

    monkeypatch.setattr(_platform, "is_windows", lambda: False)
    monkeypatch.setattr(_platform.sys, "platform", "linux")
    monkeypatch.setattr(_platform.shutil, "which", lambda name: None)
    assert _platform.pick_directory() is None
