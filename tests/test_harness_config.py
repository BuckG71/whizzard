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


def test_model_credential_valid_loads(tmp_path: Path):
    f = _write(tmp_path / "harnesses.json", {
        "hermes-cell": {
            "type": "agent",
            "start_command": "hermes",
            "model_credential": {
                "provider": "anthropic",
                "secret": "ANTHROPIC_API_KEY",
                "base_url_env": "ANTHROPIC_BASE_URL",
            },
        },
    })
    harnesses = load_harnesses(f)
    assert harnesses["hermes-cell"]["model_credential"]["secret"] == "ANTHROPIC_API_KEY"


def test_model_credential_requires_valid_secret_name(tmp_path: Path):
    f = _write(tmp_path / "harnesses.json", {
        "h": {"type": "agent", "start_command": "hermes", "model_credential": {"secret": "BAD NAME"}},
    })
    with pytest.raises(HarnessConfigError, match="model_credential.secret"):
        load_harnesses(f)


def test_model_credential_must_be_object(tmp_path: Path):
    f = _write(tmp_path / "harnesses.json", {
        "h": {"type": "agent", "start_command": "hermes", "model_credential": "ANTHROPIC_API_KEY"},
    })
    with pytest.raises(HarnessConfigError, match="model_credential must be an object"):
        load_harnesses(f)


def test_model_credential_secret_must_not_also_be_in_secrets(tmp_path: Path):
    # D-185: listing it in both would inject the real value into the cell.
    f = _write(tmp_path / "harnesses.json", {
        "h": {
            "type": "agent",
            "start_command": "hermes",
            "secrets": ["ANTHROPIC_API_KEY"],
            "model_credential": {"secret": "ANTHROPIC_API_KEY"},
        },
    })
    with pytest.raises(HarnessConfigError, match="must not"):
        load_harnesses(f)


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


def test_load_accepts_platforms_list(tmp_path: Path):
    f = _write(tmp_path / "harnesses.json", {
        "hermes-bot": {
            "type": "agent",
            "start_command": "hermes gateway run",
            "platforms": ["discord", "slack"],
        },
    })
    harnesses = load_harnesses(f)
    assert harnesses["hermes-bot"]["platforms"] == ["discord", "slack"]


def test_load_rejects_non_list_platforms(tmp_path: Path):
    f = _write(tmp_path / "harnesses.json", {
        "x": {
            "type": "agent",
            "start_command": "hermes gateway run",
            "platforms": "discord",
        },
    })
    with pytest.raises(HarnessConfigError, match="platforms must be a list of strings"):
        load_harnesses(f)


def test_load_rejects_non_string_platform_entries(tmp_path: Path):
    f = _write(tmp_path / "harnesses.json", {
        "x": {
            "type": "agent",
            "start_command": "hermes gateway run",
            "platforms": ["discord", 42],
        },
    })
    with pytest.raises(HarnessConfigError, match="platforms must be a list of strings"):
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


def test_bundled_hermes_cell_default_is_interactive_not_gateway():
    """D-181: the bundled hermes-cell starts interactive `hermes`, not
    `hermes gateway run`. Gateway is opt-in via a start_command override."""
    hermes_cell = default_harnesses()["hermes-cell"]
    assert hermes_cell["start_command"] == "hermes"
    assert "gateway" not in hermes_cell["start_command"]


def test_bundled_example_file_parses_cleanly():
    """The repo's harnesses.json.example must be a valid config."""
    example = Path(__file__).resolve().parent.parent / "config" / "harnesses.json.example"
    assert example.exists(), f"missing template at {example}"
    harnesses = load_harnesses(example)
    assert "generic" in harnesses
    assert "hermes" in harnesses
    assert harnesses["hermes"]["type"] == "agent"


# --- D-162: secrets field validation ---


def test_load_accepts_secrets_list(tmp_path: Path):
    f = _write(tmp_path / "harnesses.json", {
        "h": {
            "type": "agent",
            "start_command": "hermes gateway run",
            "secrets": ["ANTHROPIC_API_KEY", "OPENROUTER_API_KEY"],
        },
    })
    harnesses = load_harnesses(f)
    assert harnesses["h"]["secrets"] == ["ANTHROPIC_API_KEY", "OPENROUTER_API_KEY"]


def test_load_rejects_non_list_secrets(tmp_path: Path):
    f = _write(tmp_path / "harnesses.json", {
        "h": {
            "type": "agent",
            "start_command": "hermes gateway run",
            "secrets": "ANTHROPIC_API_KEY",  # string, not list
        },
    })
    with pytest.raises(HarnessConfigError, match="secrets must be a list"):
        load_harnesses(f)


def test_load_rejects_secrets_with_non_string_entries(tmp_path: Path):
    f = _write(tmp_path / "harnesses.json", {
        "h": {
            "type": "agent",
            "start_command": "hermes gateway run",
            "secrets": ["ANTHROPIC_API_KEY", 42],  # int mixed in
        },
    })
    with pytest.raises(HarnessConfigError, match="secrets must be a list"):
        load_harnesses(f)


def test_load_rejects_secrets_with_invalid_env_var_name(tmp_path: Path):
    # D-162: each entry must be a valid env-var name shape (no spaces, no '=').
    # An '=' in the entry would indicate someone is smuggling plaintext value
    # into the harness config, which the schema is designed to prevent.
    f = _write(tmp_path / "harnesses.json", {
        "h": {
            "type": "agent",
            "start_command": "hermes gateway run",
            "secrets": ["ANTHROPIC_API_KEY=sk-ant-..."],
        },
    })
    with pytest.raises(HarnessConfigError, match="not a valid env-var name"):
        load_harnesses(f)


def test_load_rejects_empty_secret_name(tmp_path: Path):
    f = _write(tmp_path / "harnesses.json", {
        "h": {
            "type": "agent",
            "start_command": "hermes gateway run",
            "secrets": [""],
        },
    })
    with pytest.raises(HarnessConfigError, match="not a valid env-var name"):
        load_harnesses(f)


# --- F-A-03: schema_version enforcement ----------------------------------


def test_load_rejects_unsupported_schema_version(tmp_path: Path):
    f = tmp_path / "harnesses.json"
    f.write_text(json.dumps({
        "schema_version": 2,
        "harnesses": {"generic": {"type": "shell", "start_command": "/bin/bash"}},
    }))
    with pytest.raises(HarnessConfigError, match="schema_version"):
        load_harnesses(f)


# --- F-B-06: empty/whitespace start_command rejected ---------------------


def test_load_rejects_empty_start_command(tmp_path: Path):
    f = _write(tmp_path / "harnesses.json", {
        "broken": {"type": "shell", "start_command": ""},
    })
    with pytest.raises(HarnessConfigError, match="non-empty string"):
        load_harnesses(f)


def test_load_rejects_whitespace_start_command(tmp_path: Path):
    """A start_command of only spaces would shlex-split to [], silently
    falling through to the image's CMD inside the container."""
    f = _write(tmp_path / "harnesses.json", {
        "broken": {"type": "shell", "start_command": "   "},
    })
    with pytest.raises(HarnessConfigError, match="non-empty string"):
        load_harnesses(f)


def test_load_rejects_non_string_start_command(tmp_path: Path):
    f = _write(tmp_path / "harnesses.json", {
        "broken": {"type": "shell", "start_command": ["bash"]},
    })
    with pytest.raises(HarnessConfigError, match="non-empty string"):
        load_harnesses(f)


# --- S20.4 / D-133: env-key denylist for process-loading vars --------------


@pytest.mark.parametrize("denied_key", [
    "LD_PRELOAD",
    "LD_LIBRARY_PATH",
    "LD_AUDIT",
    "DYLD_INSERT_LIBRARIES",
    "DYLD_LIBRARY_PATH",
    "PATH",
    "PYTHONPATH",
    "PYTHONSTARTUP",
    "IFS",
])
def test_load_rejects_denied_env_keys(tmp_path: Path, denied_key: str):
    """Env keys that affect process loading or tool resolution are
    rejected at harness-config parse time. Defense-in-depth: even
    though the cell is non-root with cap-drop=ALL, accepting these
    from harness config is a misconfig footgun."""
    f = _write(tmp_path / "harnesses.json", {
        "evil": {
            "type": "shell",
            "start_command": "/bin/bash",
            "env": {denied_key: "/tmp/attacker.so"},
        },
    })
    with pytest.raises(HarnessConfigError, match="denied"):
        load_harnesses(f)


def test_load_accepts_normal_env_keys(tmp_path: Path):
    """Sanity: normal app-level env keys are fine — only the
    process-loading / tool-resolution ones are denied."""
    f = _write(tmp_path / "harnesses.json", {
        "ok": {
            "type": "shell",
            "start_command": "/bin/bash",
            "env": {
                "HERMES_MODE": "contained",
                "ANTHROPIC_LOG": "info",
                "DEBUG": "1",
            },
        },
    })
    # Must not raise.
    harnesses = load_harnesses(f)
    assert harnesses["ok"]["env"]["HERMES_MODE"] == "contained"
