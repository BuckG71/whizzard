"""Stage 1 + Stage 3: profile configuration tests."""

import json
from pathlib import Path

import pytest

from whizzard.config import (
    ProfileConfigError,
    default_profiles,
    get_profile,
    list_profiles,
    load_profiles,
)

# Stage 1 — bundled defaults

def test_default_profile_is_unlimited():
    """Default profile must have no expiry — productive baseline."""
    p = get_profile("default")
    assert p.duration_seconds is None
    assert p.network_enabled is True


def test_default_profile_bundled_allows_broad_mount():
    """Per D-157 (supersedes D-38 on this field): the bundled `default`
    profile has allow_broad_mount=True so the user's daily-driver preset
    can attach broad mounts when the CLI flag or preset authorizes.
    Two-gate model per D-46 is preserved; this just opens the profile gate.

    Tests against `default_profiles()` (bundled) rather than `get_profile()`
    (which reads user-config overlay) — the assertion is about what ships,
    not what Bryan's personal `~/.whizzard/config/profiles.json` says.
    """
    p = default_profiles()["default"]
    assert p.allow_broad_mount is True


def test_safe_profile_is_locked_down():
    p = get_profile("safe")
    assert p.network_enabled is False
    assert p.duration_seconds == 30 * 60


def test_power_has_shorter_duration_than_build():
    """More capability => shorter duration on purpose."""
    build = get_profile("build")
    power = get_profile("power")
    assert build.duration_seconds is not None
    assert power.duration_seconds is not None
    assert power.duration_seconds < build.duration_seconds


def test_quarantine_is_offline():
    p = get_profile("quarantine")
    assert p.network_enabled is False


def test_unknown_profile_raises():
    with pytest.raises(KeyError):
        get_profile("does-not-exist")


def test_all_five_profiles_present():
    names = {p.name for p in list_profiles()}
    assert names == {"safe", "default", "build", "power", "quarantine"}


def test_default_profiles_helper_returns_copy():
    """default_profiles() must return a fresh dict so callers can mutate it."""
    a = default_profiles()
    b = default_profiles()
    assert a == b
    assert a is not b


# Stage 3 — JSON loading

def _write_profiles_json(path: Path, profiles: dict) -> Path:
    payload = {"schema_version": 1, "profiles": profiles}
    path.write_text(json.dumps(payload))
    return path


def test_load_returns_defaults_when_file_absent(tmp_path: Path):
    profiles = load_profiles(tmp_path / "missing.json")
    names = {p.name for p in profiles.values()}
    assert names == {"safe", "default", "build", "power", "quarantine"}


def test_load_parses_user_overrides(tmp_path: Path):
    f = _write_profiles_json(tmp_path / "profiles.json", {
        "custom": {
            "network_enabled": True,
            "duration_seconds": 600,
            "allow_broad_mount": True,
            "description": "test profile",
        },
    })
    profiles = load_profiles(f)
    assert set(profiles.keys()) == {"custom"}
    assert profiles["custom"].duration_seconds == 600
    assert profiles["custom"].allow_broad_mount is True
    assert profiles["custom"].description == "test profile"


def test_network_mode_derives_from_network_enabled():
    # D-184: absent network_mode is derived so pre-existing boolean profiles
    # keep their behavior.
    from whizzard.config import get_profile

    assert get_profile("default").network_mode == "open"  # network on
    assert get_profile("safe").network_mode == "none"  # network off


def test_network_mode_mediated_parses(tmp_path: Path):
    f = _write_profiles_json(tmp_path / "profiles.json", {
        "med": {
            "network_enabled": True,
            "duration_seconds": 600,
            "network_mode": "mediated",
        },
    })
    profiles = load_profiles(f)
    assert profiles["med"].network_mode == "mediated"


def test_network_mode_mediated_requires_network_enabled(tmp_path: Path):
    f = _write_profiles_json(tmp_path / "profiles.json", {
        "bad": {
            "network_enabled": False,
            "duration_seconds": 600,
            "network_mode": "mediated",
        },
    })
    with pytest.raises(ProfileConfigError):
        load_profiles(f)


def test_network_mode_invalid_value_rejected(tmp_path: Path):
    f = _write_profiles_json(tmp_path / "profiles.json", {
        "bad": {
            "network_enabled": True,
            "duration_seconds": 600,
            "network_mode": "proxy-all-the-things",
        },
    })
    with pytest.raises(ProfileConfigError):
        load_profiles(f)


def test_load_accepts_null_duration_as_unlimited(tmp_path: Path):
    f = _write_profiles_json(tmp_path / "profiles.json", {
        "always-on": {
            "network_enabled": True,
            "duration_seconds": None,
            "description": "no expiry",
        },
    })
    profiles = load_profiles(f)
    assert profiles["always-on"].duration_seconds is None


def test_load_rejects_invalid_json(tmp_path: Path):
    bad = tmp_path / "profiles.json"
    bad.write_text("{not valid json")
    with pytest.raises(ProfileConfigError):
        load_profiles(bad)


def test_load_rejects_missing_network_enabled(tmp_path: Path):
    f = _write_profiles_json(tmp_path / "profiles.json", {
        "x": {"duration_seconds": 60},
    })
    with pytest.raises(ProfileConfigError, match="network_enabled"):
        load_profiles(f)


def test_load_rejects_missing_duration_seconds(tmp_path: Path):
    f = _write_profiles_json(tmp_path / "profiles.json", {
        "x": {"network_enabled": True},
    })
    with pytest.raises(ProfileConfigError, match="duration_seconds"):
        load_profiles(f)


def test_load_rejects_negative_duration(tmp_path: Path):
    f = _write_profiles_json(tmp_path / "profiles.json", {
        "x": {"network_enabled": True, "duration_seconds": -10},
    })
    with pytest.raises(ProfileConfigError, match="positive"):
        load_profiles(f)


def test_load_rejects_non_int_duration(tmp_path: Path):
    f = _write_profiles_json(tmp_path / "profiles.json", {
        "x": {"network_enabled": True, "duration_seconds": "forever"},
    })
    with pytest.raises(ProfileConfigError, match="integer or null"):
        load_profiles(f)


def test_load_rejects_bool_duration(tmp_path: Path):
    """Python booleans are technically ints; reject them explicitly."""
    f = _write_profiles_json(tmp_path / "profiles.json", {
        "x": {"network_enabled": True, "duration_seconds": True},
    })
    with pytest.raises(ProfileConfigError, match="integer or null"):
        load_profiles(f)


def test_load_rejects_non_bool_network_enabled(tmp_path: Path):
    f = _write_profiles_json(tmp_path / "profiles.json", {
        "x": {"network_enabled": "yes", "duration_seconds": 60},
    })
    with pytest.raises(ProfileConfigError, match="network_enabled"):
        load_profiles(f)


def test_load_rejects_empty_profiles(tmp_path: Path):
    f = _write_profiles_json(tmp_path / "profiles.json", {})
    with pytest.raises(ProfileConfigError, match="at least one"):
        load_profiles(f)


def test_load_uses_default_for_optional_fields(tmp_path: Path):
    f = _write_profiles_json(tmp_path / "profiles.json", {
        "minimal": {"network_enabled": True, "duration_seconds": 60},
    })
    profiles = load_profiles(f)
    assert profiles["minimal"].allow_broad_mount is False
    assert profiles["minimal"].description == ""


def test_bundled_example_file_parses_cleanly(tmp_path: Path):
    """The repo's profiles.json.example must be a valid config."""
    example = Path(__file__).resolve().parent.parent / "config" / "profiles.json.example"
    assert example.exists(), f"missing template at {example}"
    profiles = load_profiles(example)
    assert {"safe", "default", "build", "power", "quarantine"} == set(profiles.keys())
    # Same semantics as bundled defaults
    assert profiles["default"].duration_seconds is None
    assert profiles["power"].allow_broad_mount is True


# --- Stage 15: idle_timeout_seconds ---------------------------------------


def test_bundled_default_profiles_carry_idle_timeout():
    profiles = default_profiles()
    assert profiles["build"].idle_timeout_seconds == 30 * 60
    assert profiles["safe"].idle_timeout_seconds == 15 * 60
    # the always-on `default` profile deliberately has no idle timeout
    assert profiles["default"].idle_timeout_seconds is None


def test_load_parses_idle_timeout_seconds(tmp_path: Path):
    f = _write_profiles_json(tmp_path / "p.json", {
        "x": {"network_enabled": True, "duration_seconds": 3600,
              "idle_timeout_seconds": 600},
    })
    assert load_profiles(f)["x"].idle_timeout_seconds == 600


def test_idle_timeout_absent_defaults_to_none(tmp_path: Path):
    f = _write_profiles_json(tmp_path / "p.json", {
        "x": {"network_enabled": True, "duration_seconds": 3600},
    })
    assert load_profiles(f)["x"].idle_timeout_seconds is None


def test_idle_timeout_null_is_accepted(tmp_path: Path):
    f = _write_profiles_json(tmp_path / "p.json", {
        "x": {"network_enabled": True, "duration_seconds": 3600,
              "idle_timeout_seconds": None},
    })
    assert load_profiles(f)["x"].idle_timeout_seconds is None


def test_idle_timeout_rejects_non_integer(tmp_path: Path):
    f = _write_profiles_json(tmp_path / "p.json", {
        "x": {"network_enabled": True, "duration_seconds": 3600,
              "idle_timeout_seconds": "soon"},
    })
    with pytest.raises(ProfileConfigError, match="idle_timeout_seconds"):
        load_profiles(f)


def test_idle_timeout_rejects_non_positive(tmp_path: Path):
    f = _write_profiles_json(tmp_path / "p.json", {
        "x": {"network_enabled": True, "duration_seconds": 3600,
              "idle_timeout_seconds": 0},
    })
    with pytest.raises(ProfileConfigError, match="positive"):
        load_profiles(f)


# --- F-A-03: schema_version enforcement ----------------------------------


def test_load_rejects_unsupported_schema_version(tmp_path: Path):
    f = tmp_path / "p.json"
    f.write_text(json.dumps({
        "schema_version": 2,
        "profiles": {
            "x": {"network_enabled": True, "duration_seconds": 60},
        },
    }))
    with pytest.raises(ProfileConfigError, match="schema_version"):
        load_profiles(f)


def test_load_accepts_missing_schema_version(tmp_path: Path):
    """Missing schema_version is treated as v1 — older configs keep working."""
    f = tmp_path / "p.json"
    f.write_text(json.dumps({
        "profiles": {
            "x": {"network_enabled": True, "duration_seconds": 60},
        },
    }))
    profiles = load_profiles(f)
    assert "x" in profiles
