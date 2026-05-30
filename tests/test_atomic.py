"""Tests for whizzard._atomic — the shared atomic-write helper.

The point of the helper is that a crash mid-write leaves the original
file intact; tests below simulate that by raising inside the write
phase and asserting the existing content survives.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from whizzard._atomic import atomic_write_text


def test_writes_new_file(tmp_path: Path) -> None:
    target = tmp_path / "new.json"
    atomic_write_text(target, '{"hello": 1}')
    assert target.read_text() == '{"hello": 1}'


def test_overwrites_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "existing.json"
    target.write_text("old contents")
    atomic_write_text(target, "new contents")
    assert target.read_text() == "new contents"


def test_creates_parent_dir_if_missing(tmp_path: Path) -> None:
    target = tmp_path / "deep" / "nested" / "file.json"
    atomic_write_text(target, "x")
    assert target.read_text() == "x"


def test_crash_mid_write_leaves_original_intact(
    tmp_path: Path, monkeypatch,
) -> None:
    """If write_text raises during the tmp-file phase, the destination
    must still hold its original content — atomicity's whole point."""
    target = tmp_path / "config.json"
    target.write_text("ORIGINAL")

    def _exploding_write_text(self: Path, content: str) -> int:
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_text", _exploding_write_text)

    with pytest.raises(OSError, match="disk full"):
        atomic_write_text(target, "NEW")

    # Restore real write_text to read the file back.
    monkeypatch.undo()
    assert target.read_text() == "ORIGINAL"


def test_no_tmp_file_left_behind_on_success(tmp_path: Path) -> None:
    target = tmp_path / "x.json"
    atomic_write_text(target, "y")
    siblings = list(tmp_path.iterdir())
    assert siblings == [target], f"unexpected leftover files: {siblings}"
