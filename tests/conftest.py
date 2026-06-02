"""Shared test fixtures.

The Windows-only fixture below exists because of a collision between two
correct things: (1) the safety policy now hard-blocks the Windows `AppData`
tree (browser creds, DPAPI keys, Credential Manager — see
`safety._windows_exclusions`), and (2) pytest puts `tmp_path` under
`%LOCALAPPDATA%\\Temp`, i.e. *inside* `AppData`. So on Windows, any test that
runs a real `check_mount_path` against a `tmp_path` mount would trip the
AppData hard-block before reaching its actual assertion.

In production that block is correct (you shouldn't mount your AppData into a
sandbox). For tests, we drop just the deep-hard-block entries that are
ancestors of the pytest tmp area, leaving every other block intact. The
Windows AppData block itself is still verified directly by the dedicated
tests in test_safety.py, which construct their own block lists.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _unblock_pytest_tmp_on_windows(tmp_path_factory, monkeypatch):
    if os.name != "nt":
        return  # POSIX pytest tmp (e.g. /private/var/folders) isn't blocked

    from whizzard import safety

    tmp_root = Path(tmp_path_factory.getbasetemp()).resolve()

    kept = []
    for entry in safety._DEEP_HARD_BLOCKS:
        try:
            resolved = entry.resolve()
        except OSError:
            kept.append(entry)
            continue
        try:
            tmp_root.relative_to(resolved)  # resolved is an ancestor of tmp
            # Drop it — it would block every tmp_path-based mount in tests.
        except ValueError:
            kept.append(entry)  # not an ancestor of tmp; keep the block
    monkeypatch.setattr(safety, "_DEEP_HARD_BLOCKS", kept)
