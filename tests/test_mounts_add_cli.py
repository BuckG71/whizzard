"""Tests for `whiz mounts add` (the registry-write CLI path)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from whizzard.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated_whizzard_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    home = tmp_path / "whizzard-home"
    (home / "config").mkdir(parents=True)
    # Start from an explicit empty registry so the bundled-default fallback
    # (load_mounts returns defaults only when the file is absent) doesn't mix in.
    (home / "config" / "mounts.json").write_text(
        '{"schema_version": 1, "mounts": {}}\n'
    )
    monkeypatch.setenv("WHIZZARD_HOME", str(home))
    from whizzard import config, mounts

    monkeypatch.setattr(config, "WHIZZARD_HOME", home)
    monkeypatch.setattr(config, "CONFIG_DIR", home / "config")
    monkeypatch.setattr(mounts, "MOUNTS_FILE", home / "config" / "mounts.json")
    yield home


def _registry(home: Path) -> dict:
    return json.loads((home / "config" / "mounts.json").read_text())["mounts"]


def test_add_registers_existing_folder(isolated_whizzard_home: Path, tmp_path: Path):
    proj = tmp_path / "proj"
    proj.mkdir()
    result = runner.invoke(app, ["mounts", "add", str(proj), "--name", "proj", "--mode", "rw"])
    assert result.exit_code == 0, result.output
    m = _registry(isolated_whizzard_home)
    assert "proj" in m
    assert m["proj"]["default_mode"] == "rw"


def test_add_derives_lowercased_name_from_folder(isolated_whizzard_home: Path, tmp_path: Path):
    (tmp_path / "MyProject").mkdir()
    result = runner.invoke(app, ["mounts", "add", str(tmp_path / "MyProject")])
    assert result.exit_code == 0, result.output
    assert "myproject" in _registry(isolated_whizzard_home)


def test_add_rejects_hard_blocked_path(isolated_whizzard_home: Path):
    result = runner.invoke(app, ["mounts", "add", "/"])
    assert result.exit_code == 2
    assert "hard-blocked" in result.output
    assert _registry(isolated_whizzard_home) == {}


def test_add_missing_folder_needs_create_flag(isolated_whizzard_home: Path, tmp_path: Path):
    missing = tmp_path / "nope"
    r1 = runner.invoke(app, ["mounts", "add", str(missing)])
    assert r1.exit_code == 2
    assert "does not exist" in r1.output
    assert _registry(isolated_whizzard_home) == {}

    r2 = runner.invoke(app, ["mounts", "add", str(missing), "--create"])
    assert r2.exit_code == 0, r2.output
    assert missing.is_dir()
    assert "nope" in _registry(isolated_whizzard_home)


def test_add_rejects_duplicate_name(isolated_whizzard_home: Path, tmp_path: Path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    runner.invoke(app, ["mounts", "add", str(tmp_path / "a"), "--name", "dup"])
    result = runner.invoke(app, ["mounts", "add", str(tmp_path / "b"), "--name", "dup"])
    assert result.exit_code == 2
    assert "already exists" in result.output


def test_add_preserves_existing_entries_verbatim(isolated_whizzard_home: Path, tmp_path: Path):
    """Adding a mount must NOT canonicalize other entries' stored host_path —
    a load_mounts round-trip would rewrite ~/code → /abs/code. Existing entries
    stay byte-for-byte as written."""
    (isolated_whizzard_home / "config" / "mounts.json").write_text(
        '{"schema_version": 1, "mounts": '
        '{"existing": {"host_path": "~/code", "default_mode": "ro", "description": ""}}}\n'
    )
    (tmp_path / "new").mkdir()
    result = runner.invoke(app, ["mounts", "add", str(tmp_path / "new"), "--name", "newm"])
    assert result.exit_code == 0, result.output
    m = _registry(isolated_whizzard_home)
    assert m["existing"]["host_path"] == "~/code"  # untouched, not resolved
    assert "newm" in m


def test_add_rejects_bad_mode(isolated_whizzard_home: Path, tmp_path: Path):
    (tmp_path / "p").mkdir()
    result = runner.invoke(app, ["mounts", "add", str(tmp_path / "p"), "--mode", "weird"])
    assert result.exit_code == 2
    assert "'ro'" in result.output and "'rw'" in result.output


def test_add_pick_uses_dialog_result(
    isolated_whizzard_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    picked = tmp_path / "picked"
    picked.mkdir()
    from whizzard import _platform

    monkeypatch.setattr(_platform, "pick_directory", lambda prompt="": str(picked))
    result = runner.invoke(app, ["mounts", "add", "--pick", "--name", "pk"])
    assert result.exit_code == 0, result.output
    assert "pk" in _registry(isolated_whizzard_home)


def test_add_pick_cancelled_exits_cleanly(
    isolated_whizzard_home: Path, monkeypatch: pytest.MonkeyPatch
):
    from whizzard import _platform

    monkeypatch.setattr(_platform, "pick_directory", lambda prompt="": None)
    result = runner.invoke(app, ["mounts", "add", "--pick"])
    assert result.exit_code == 1
    assert "no folder selected" in result.output
