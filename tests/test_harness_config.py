"""Stage 7: harnesses.json loader tests."""

import json
from pathlib import Path

import pytest

from whizzard.harness_config import (
    HarnessConfigError,
    default_harnesses,
    get_harness_config,
    load_harnesses,
)


def _write(path: Path, harnesses: dict) -> Path:
    payload = {"schema_version": 1, "harnesses": harnesses}
    path.write_text(json.dumps(payload))
    return path


def test_load_returns_defaults_when_file_absent(tmp_path: Path):
    harnesses = load_harnesses(tmp_path / "missing.json")
    assert "generic" in harnesses
    assert harnesses["generic"]["type"] == "shell"


def test_load_parses_valid_config(tmp_path: Path):
    f = _write(tmp_path / "harnesses.json", {
        "generic": {"type": "shell", "start_command": "/bin/bash"},
        "hermes": {
            "type": "agent",
            "start_command": "hermes chat",
            "wrap_up_command": "/quit",
            "wrap_up_grace_seconds": 30,
        },
    })
    harnesses = load_harnesses(f)
    assert set(harnesses.keys()) == {"generic", "hermes"}
    assert harnesses["hermes"]["wrap_up_command"] == "/quit"


def test_load_rejects_invalid_json(tmp_path: Path):
    bad = tmp_path / "harnesses.json"
    bad.write_text("{not json")
    with pytest.raises(HarnessConfigError):
        load_harnesses(bad)


def test_load_rejects_missing_type(tmp_path: Path):
    f = _write(tmp_path / "harnesses.json", {
        "x": {"start_command": "/bin/bash"},
    })
    with pytest.raises(HarnessConfigError, match="missing required field 'type'"):
        load_harnesses(f)


def test_load_rejects_invalid_type(tmp_path: Path):
    f = _write(tmp_path / "harnesses.json", {
        "x": {"type": "alien", "start_command": "/bin/bash"},
    })
    with pytest.raises(HarnessConfigError, match="must be 'shell' or 'agent'"):
        load_harnesses(f)


def test_load_rejects_missing_start_command(tmp_path: Path):
    f = _write(tmp_path / "harnesses.json", {
        "x": {"type": "shell"},
    })
    with pytest.raises(HarnessConfigError, match="start_command"):
        load_harnesses(f)


def test_load_rejects_non_int_grace_seconds(tmp_path: Path):
    f = _write(tmp_path / "harnesses.json", {
        "x": {
            "type": "agent",
            "start_command": "x",
            "wrap_up_grace_seconds": "thirty",
        },
    })
    with pytest.raises(HarnessConfigError, match="wrap_up_grace_seconds"):
        load_harnesses(f)


def test_load_rejects_non_dict_env(tmp_path: Path):
    f = _write(tmp_path / "harnesses.json", {
        "x": {
            "type": "shell",
            "start_command": "/bin/bash",
            "env": "not a dict",
        },
    })
    with pytest.raises(HarnessConfigError, match="env must be an object"):
        load_harnesses(f)


def test_load_rejects_empty_harnesses(tmp_path: Path):
    f = _write(tmp_path / "harnesses.json", {})
    with pytest.raises(HarnessConfigError, match="at least one"):
        load_harnesses(f)


def test_get_harness_config_returns_known(tmp_path: Path):
    f = _write(tmp_path / "harnesses.json", {
        "alpha": {"type": "shell", "start_command": "/bin/bash"},
    })
    cfg = get_harness_config("alpha", path=f)
    assert cfg["type"] == "shell"


def test_get_harness_config_unknown_raises(tmp_path: Path):
    f = _write(tmp_path / "harnesses.json", {
        "alpha": {"type": "shell", "start_command": "/bin/bash"},
    })
    with pytest.raises(HarnessConfigError, match="unknown harness"):
        get_harness_config("bravo", path=f)


def test_default_harnesses_returns_copy():
    a = default_harnesses()
    b = default_harnesses()
    assert a == b
    assert a is not b
    a["generic"]["start_command"] = "tampered"
    assert b["generic"]["start_command"] != "tampered"


def test_bundled_example_file_parses_cleanly():
    """The repo's harnesses.json.example must be a valid config."""
    example = Path(__file__).resolve().parent.parent / "config" / "harnesses.json.example"
    assert example.exists(), f"missing template at {example}"
    harnesses = load_harnesses(example)
    assert "generic" in harnesses
    assert "hermes" in harnesses
    assert harnesses["hermes"]["type"] == "agent"
