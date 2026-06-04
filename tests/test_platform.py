"""Tests for the dependency-free platform/Docker primitives."""

from __future__ import annotations

import os

from whizzard._platform import (
    DAEMON_DOWN_INDICATORS,
    is_windows,
    looks_like_daemon_error,
)


def test_is_windows_matches_os_name():
    assert is_windows() == (os.name == "nt")


def test_looks_like_daemon_error_matches_each_indicator():
    for token in DAEMON_DOWN_INDICATORS:
        assert looks_like_daemon_error(f"docker: {token} (is it running?)")


def test_looks_like_daemon_error_real_mac_message():
    stderr = (
        "Cannot connect to the Docker daemon at unix:///var/run/docker.sock. "
        "Is the docker daemon running?"
    )
    assert looks_like_daemon_error(stderr)


def test_looks_like_daemon_error_ignores_unrelated_stderr():
    assert not looks_like_daemon_error("Error: No such image: whizzard:latest")
    assert not looks_like_daemon_error("")
