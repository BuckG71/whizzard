"""Stage 1: profile configuration sanity checks."""

import pytest

from warlock.config import get_profile, list_profiles


def test_default_profile_is_unlimited():
    """Default profile must have no expiry — productive baseline."""
    p = get_profile("default")
    assert p.duration_seconds is None
    assert p.network_enabled is True


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
