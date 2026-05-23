"""Stage 10 #2: preset machinery + bundled defaults tests."""

import json
from pathlib import Path

import pytest

from whizzard.preset_config import (
    PresetConfigError,
    default_presets,
    get_preset,
    list_presets,
    load_presets,
    validate_references,
)


def _write_presets_json(path: Path, presets: dict) -> Path:
    payload = {"schema_version": 1, "presets": presets}
    path.write_text(json.dumps(payload))
    return path


# --- bundled defaults ----------------------------------------------------


def test_default_presets_includes_hermes_and_shell():
    p = default_presets()
    assert set(p.keys()) == {"hermes", "shell"}


def test_default_presets_returns_fresh_dict():
    a = default_presets()
    b = default_presets()
    assert a == b
    assert a is not b


def test_default_hermes_preset_shape():
    p = default_presets()["hermes"]
    assert p.profile == "default"
    assert p.harness == "hermes-cell"
    assert set(p.mounts) == {"claude-projects", "ai-sandbox"}
    assert p.platforms == ("discord",)
    assert p.duration_seconds is None
    assert p.idle_timeout_seconds is None


def test_default_shell_preset_shape():
    p = default_presets()["shell"]
    assert p.profile == "safe"
    assert p.harness == "generic"
    assert p.mounts == ()
    assert p.platforms == ()


# --- load_presets --------------------------------------------------------


def test_load_returns_bundled_defaults_when_file_absent(tmp_path: Path):
    presets = load_presets(tmp_path / "missing.json")
    assert set(presets.keys()) == {"hermes", "shell"}


def test_load_parses_well_formed_file(tmp_path: Path):
    f = _write_presets_json(tmp_path / "presets.json", {
        "custom": {
            "profile": "default",
            "harness": "generic",
            "mounts": ["alpha"],
            "platforms": [],
            "description": "custom preset",
        },
    })
    presets = load_presets(f)
    assert "custom" in presets
    assert presets["custom"].mounts == ("alpha",)


def test_load_rejects_missing_profile_field(tmp_path: Path):
    f = _write_presets_json(tmp_path / "presets.json", {
        "bad": {"harness": "generic"},
    })
    with pytest.raises(PresetConfigError, match="required field 'profile'"):
        load_presets(f)


def test_load_rejects_missing_harness_field(tmp_path: Path):
    f = _write_presets_json(tmp_path / "presets.json", {
        "bad": {"profile": "default"},
    })
    with pytest.raises(PresetConfigError, match="required field 'harness'"):
        load_presets(f)


def test_load_rejects_non_list_mounts(tmp_path: Path):
    f = _write_presets_json(tmp_path / "presets.json", {
        "bad": {"profile": "default", "harness": "generic", "mounts": "not-a-list"},
    })
    with pytest.raises(PresetConfigError, match="'mounts' must be a list"):
        load_presets(f)


def test_load_rejects_non_list_platforms(tmp_path: Path):
    f = _write_presets_json(tmp_path / "presets.json", {
        "bad": {"profile": "default", "harness": "generic", "platforms": "not-a-list"},
    })
    with pytest.raises(PresetConfigError, match="'platforms' must be a list"):
        load_presets(f)


def test_load_rejects_non_int_duration(tmp_path: Path):
    f = _write_presets_json(tmp_path / "presets.json", {
        "bad": {"profile": "default", "harness": "generic", "duration_seconds": "soon"},
    })
    with pytest.raises(PresetConfigError, match="duration_seconds"):
        load_presets(f)


# F-A-01: preset overrides previously slipped past validation that the
# profile loader enforced. These four tests cover the gap.


def test_load_rejects_bool_duration(tmp_path: Path):
    """bool is an int subclass; must be rejected (not silently coerced to 1)."""
    f = _write_presets_json(tmp_path / "presets.json", {
        "bad": {"profile": "default", "harness": "generic", "duration_seconds": True},
    })
    with pytest.raises(PresetConfigError, match="duration_seconds"):
        load_presets(f)


def test_load_rejects_zero_duration(tmp_path: Path):
    """0 would mean 'immediate kill on launch' — clearly wrong."""
    f = _write_presets_json(tmp_path / "presets.json", {
        "bad": {"profile": "default", "harness": "generic", "duration_seconds": 0},
    })
    with pytest.raises(PresetConfigError, match="positive"):
        load_presets(f)


def test_load_rejects_negative_duration(tmp_path: Path):
    f = _write_presets_json(tmp_path / "presets.json", {
        "bad": {"profile": "default", "harness": "generic", "duration_seconds": -60},
    })
    with pytest.raises(PresetConfigError, match="positive"):
        load_presets(f)


def test_load_rejects_zero_idle_timeout(tmp_path: Path):
    f = _write_presets_json(tmp_path / "presets.json", {
        "bad": {"profile": "default", "harness": "generic", "idle_timeout_seconds": 0},
    })
    with pytest.raises(PresetConfigError, match="positive"):
        load_presets(f)


def test_load_rejects_non_bool_allow_broad_mount(tmp_path: Path):
    f = _write_presets_json(tmp_path / "presets.json", {
        "bad": {"profile": "default", "harness": "generic", "allow_broad_mount": "yes"},
    })
    with pytest.raises(PresetConfigError, match="allow_broad_mount"):
        load_presets(f)


def test_load_rejects_invalid_json(tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text("this is not json {{{")
    with pytest.raises(PresetConfigError):
        load_presets(bad)


def test_load_rejects_unsupported_schema_version(tmp_path: Path):
    """F-A-03: presets file with unsupported schema_version must raise."""
    f = tmp_path / "presets.json"
    f.write_text(json.dumps({
        "schema_version": 2,
        "presets": {"x": {"profile": "default", "harness": "generic"}},
    }))
    with pytest.raises(PresetConfigError, match="schema_version"):
        load_presets(f)


# --- omit-to-inherit semantics -------------------------------------------


def test_preset_omitting_duration_marks_no_override(tmp_path: Path):
    f = _write_presets_json(tmp_path / "presets.json", {
        "x": {"profile": "default", "harness": "generic"},
    })
    p = load_presets(f)["x"]
    assert p.overrides("duration_seconds") is False
    assert p.overrides("idle_timeout_seconds") is False
    assert p.overrides("allow_broad_mount") is False


def test_preset_including_duration_marks_override(tmp_path: Path):
    f = _write_presets_json(tmp_path / "presets.json", {
        "x": {
            "profile": "default",
            "harness": "generic",
            "duration_seconds": 3600,
        },
    })
    p = load_presets(f)["x"]
    assert p.overrides("duration_seconds") is True
    assert p.duration_seconds == 3600


def test_preset_including_null_duration_marks_override(tmp_path: Path):
    """Null is also an override — explicit declaration of 'unlimited'."""
    f = _write_presets_json(tmp_path / "presets.json", {
        "x": {
            "profile": "default",
            "harness": "generic",
            "duration_seconds": None,
        },
    })
    p = load_presets(f)["x"]
    assert p.overrides("duration_seconds") is True
    assert p.duration_seconds is None


# --- get_preset / list_presets -------------------------------------------


def test_get_preset_returns_known(tmp_path: Path):
    f = _write_presets_json(tmp_path / "presets.json", {
        "x": {"profile": "default", "harness": "generic"},
    })
    assert get_preset("x", path=f).name == "x"


def test_get_preset_unknown_raises(tmp_path: Path):
    f = _write_presets_json(tmp_path / "presets.json", {
        "x": {"profile": "default", "harness": "generic"},
    })
    with pytest.raises(PresetConfigError, match="unknown preset"):
        get_preset("nope", path=f)


def test_list_presets_returns_list(tmp_path: Path):
    f = _write_presets_json(tmp_path / "presets.json", {
        "a": {"profile": "default", "harness": "generic"},
        "b": {"profile": "default", "harness": "generic"},
    })
    presets = list_presets(path=f)
    assert {p.name for p in presets} == {"a", "b"}


# --- validate_references -------------------------------------------------


def test_validate_passes_when_all_references_exist():
    presets = default_presets()
    # Bundled hermes references profile=default, harness=hermes-cell,
    # mounts=claude-projects+ai-sandbox.
    validate_references(
        presets,
        profile_names={"default", "safe", "build", "power", "quarantine"},
        harness_names={"hermes-cell", "generic"},
        mount_names={"claude-projects", "ai-sandbox"},
    )  # no exception


def test_validate_rejects_missing_profile():
    presets = default_presets()
    with pytest.raises(PresetConfigError, match="unknown profile"):
        validate_references(
            presets,
            profile_names={"safe"},  # missing 'default'
            harness_names={"hermes-cell", "generic"},
            mount_names={"claude-projects", "ai-sandbox"},
        )


def test_validate_rejects_missing_harness():
    presets = default_presets()
    with pytest.raises(PresetConfigError, match="unknown harness"):
        validate_references(
            presets,
            profile_names={"default", "safe"},
            harness_names={"generic"},  # missing 'hermes-cell'
            mount_names={"claude-projects", "ai-sandbox"},
        )


def test_validate_rejects_missing_mount():
    presets = default_presets()
    with pytest.raises(PresetConfigError, match="unknown mount"):
        validate_references(
            presets,
            profile_names={"default", "safe"},
            harness_names={"hermes-cell", "generic"},
            mount_names={"claude-projects"},  # missing 'ai-sandbox'
        )


def test_validate_rejects_platform_outside_harness_ceiling():
    presets = default_presets()
    with pytest.raises(PresetConfigError, match="not in harness"):
        validate_references(
            presets,
            profile_names={"default", "safe"},
            harness_names={"hermes-cell", "generic"},
            mount_names={"claude-projects", "ai-sandbox"},
            harness_platforms={"hermes-cell": {"slack"}, "generic": set()},
            # hermes preset declares 'discord' but ceiling is {'slack'}
        )


def test_validate_skips_platform_check_when_harness_platforms_none():
    """If caller doesn't supply harness_platforms, the platform check is skipped."""
    presets = default_presets()
    # Should not raise even though hermes declares discord
    validate_references(
        presets,
        profile_names={"default", "safe"},
        harness_names={"hermes-cell", "generic"},
        mount_names={"claude-projects", "ai-sandbox"},
        harness_platforms=None,
    )
