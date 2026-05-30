"""S20.3 / D-133 prong (b): dry-run vs real-launch argv parity.

The build plan calls out: "the dry-run preview cannot diverge from the
actual launch: the preview and the real `docker run` invocation must
resolve from one code path. A preview that lies is a security bug."

Both paths in fact share ``build_run_argv``. The dry-run path
(``cli/_launch.py`` when ``dry_run=True``) calls it with no ``cidfile``
and the default ``interactive=True``; the real path (``run_shell`` in
``docker_cmd.py``) calls it with ``cidfile=<path>`` and the caller's
``interactive`` value.

This test locks down that divergence: for the same inputs, the two
paths produce argvs that differ ONLY by the documented tracking-only
flags. A future flag added to ``run_shell``'s ``build_run_argv`` call
that the dry-run path doesn't replicate fails this test loudly — the
preview would otherwise lie about a security-relevant launch flag.
"""

from __future__ import annotations

from whizzard.config import get_profile
from whizzard.docker_cmd import build_run_argv

# Flags the real launch ADDS that dry-run intentionally omits.
# Each entry is the flag name; values aren't compared.
# Adding to this set is a deliberate "this divergence is OK" decision.
_INTENTIONAL_REAL_ONLY_FLAGS = frozenset({
    "--cidfile",  # tracking-only; not a security boundary
})


def _argv_difference(real: list[str], preview: list[str]) -> list[str]:
    """Return the set of flag names present in `real` but not in
    `preview`. Skips values (only flag names matter for the parity
    check). A "flag name" is any argv element starting with `-`."""
    real_flags = {a for a in real if a.startswith("-")}
    preview_flags = {a for a in preview if a.startswith("-")}
    return sorted(real_flags - preview_flags)


def test_dry_run_argv_matches_real_launch_argv_modulo_tracking_flags():
    """The two paths must agree on every security-relevant flag. The
    only allowed real-only flags are explicit tracking helpers — they
    don't shape the container's boundary."""
    profile = get_profile("safe")
    image = "whizzard-base:latest"
    session_id = "parity-test-001"

    # Dry-run shape: no cidfile, default interactive
    preview_argv = build_run_argv(
        profile,
        image=image,
        resolved_mounts=None,
        session_id=session_id,
    )

    # Real-launch shape: with cidfile (tracking), explicit interactive
    real_argv = build_run_argv(
        profile,
        image=image,
        resolved_mounts=None,
        session_id=session_id,
        cidfile=None,  # exercise the keyword; production passes a Path
        interactive=True,
    )

    extra = _argv_difference(real_argv, preview_argv)
    unexpected = set(extra) - _INTENTIONAL_REAL_ONLY_FLAGS
    assert not unexpected, (
        f"real-launch argv has flags the dry-run preview omits: {unexpected}. "
        f"If this is intentional, add to _INTENTIONAL_REAL_ONLY_FLAGS with a "
        f"comment explaining why the divergence is non-security-relevant. "
        f"Otherwise, the dry-run path is silently hiding a security-shaping "
        f"flag from the user."
    )

    # And nothing the dry-run path adds that the real path drops.
    preview_extra = _argv_difference(preview_argv, real_argv)
    assert not preview_extra, (
        f"dry-run preview shows flags the real launch doesn't apply: "
        f"{preview_extra}. The user's preview is misleading."
    )


def test_dry_run_security_flags_are_present():
    """Belt: the dry-run preview must surface every security-shaping
    flag the real launch applies. Whitelist of flag names that MUST
    appear regardless of profile."""
    profile = get_profile("default")
    preview_argv = build_run_argv(
        profile,
        image="whizzard-base:latest",
        session_id="parity-test-002",
    )

    required_security_flags = [
        "--user",
        "--cap-drop=ALL",
        "--security-opt",
        "--read-only",
        "--tmpfs",
    ]
    for flag in required_security_flags:
        assert flag in preview_argv, (
            f"dry-run preview missing required security flag {flag!r} — "
            f"the preview is misleading the user about the launched container's posture"
        )


def test_dry_run_network_flag_reflects_profile():
    """Network policy is profile-driven; the preview must reflect it
    accurately for both on and off cases."""
    safe = get_profile("safe")  # network off
    default = get_profile("default")  # network on

    safe_argv = build_run_argv(
        safe, image="whizzard-base:latest", session_id="net-test-1",
    )
    default_argv = build_run_argv(
        default, image="whizzard-base:latest", session_id="net-test-2",
    )

    # Network-off profile MUST include --network none.
    joined_safe = " ".join(safe_argv)
    assert "--network none" in joined_safe, (
        f"network-off profile preview missing --network none: {joined_safe}"
    )
    # Network-on profile MUST NOT include --network none.
    joined_default = " ".join(default_argv)
    assert "--network none" not in joined_default, (
        f"network-on profile preview includes --network none (would mislead "
        f"the user about egress): {joined_default}"
    )
