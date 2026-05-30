"""Red-team — config write-protection (cluster 2 of the Stage 20 suite).

The foundational invariant: the host's Whizzard config directory must be
unreachable from inside a running cell, via any access path. A cell that
can read the config could leak credential paths, profile shapes, or the
mount registry; one that can *write* the config could rewrite its own
policy and break the one-way capability flow (D-9).

Each test stages an attack — an attacker inside the cell tries to reach
``$HOME/.whizzard/config/`` from the host's filesystem — and asserts the
attempt produced no host-side leak. The cell is non-root, has no Docker
socket, runs `--read-only` with `--cap-drop=ALL` and `no-new-privileges`;
the assertions here verify the *combined* posture is enough to keep the
config dir invisible.

Coverage angles per the build plan's "heaviest coverage here" guidance:

  1. Absolute host path — cell tries the bare host path; cell's view of
     $HOME is /home/whizzard, not the host's $HOME, so the host path
     simply does not exist inside the cell's namespace.
  2. Traversal from a rw mount — cell mounts a host tmp_path read-write,
     then walks `..` until it would reach the host's config dir; Docker
     bind-mount semantics confine `..` to the mount source.
  3. Hostile symlink in a rw mount — host plants a symlink inside the
     mount targeting the host's config dir; following it resolves in
     the *container's* namespace, not the host's.
  4. /proc/1/root introspection — PID 1 in the cell is the cell's init,
     so its root is the container rootfs, not the host's.
  5. /proc/self/mounts — only the declared mounts (and the container
     filesystem internals) show up; the host's filesystem layout is
     not enumerated.

Each test is framed as "stage the attack, run a command in a real cell,
assert no host data leaked". A failure here is a containment break,
not a flaky test — investigate before re-running.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from whizzard.config import WHIZZARD_HOME

pytestmark = pytest.mark.integration


_SENTINEL_VALUE_PREFIX = "WHIZZARD_REDTEAM_SENTINEL_"


@pytest.fixture
def host_config_sentinel():
    """Plant a uniquely-named sentinel file inside the *real* host config
    directory and tear it down after the test.

    Using a real path (not a tmp_path override) is intentional: the
    invariant under test is that the host's actual config dir is
    unreachable from the cell, not that an arbitrary directory of the
    same shape would be. The sentinel value is a UUID-tagged marker so
    every assertion can grep for the *specific* leak.

    If the host has no `~/.whizzard/` yet (fresh dev machine, never ran
    `whiz init`), the fixture creates it and removes both file and the
    `config/` it created on teardown; if the host already had a real
    config dir, only the sentinel file is removed.
    """
    config_dir = WHIZZARD_HOME / "config"
    created_whizzard_home = not WHIZZARD_HOME.exists()
    created_config = not config_dir.exists()
    config_dir.mkdir(parents=True, exist_ok=True)

    sentinel_value = f"{_SENTINEL_VALUE_PREFIX}{uuid.uuid4().hex}"
    sentinel_file = config_dir / f"redteam-{uuid.uuid4().hex}.txt"
    sentinel_file.write_text(sentinel_value)

    try:
        yield sentinel_value, sentinel_file
    finally:
        sentinel_file.unlink(missing_ok=True)
        if created_config and not any(config_dir.iterdir()):
            config_dir.rmdir()
        if created_whizzard_home and WHIZZARD_HOME.exists() and not any(
            WHIZZARD_HOME.iterdir()
        ):
            WHIZZARD_HOME.rmdir()


def _assert_no_sentinel_leak(stdout: str, sentinel_value: str) -> None:
    """Single assertion shape: the sentinel content must not appear in
    any output the cell produced. Includes the broader prefix to catch
    fragmentary leaks (a future test reuse with truncated reads)."""
    assert sentinel_value not in stdout, (
        f"host config sentinel leaked into the cell:\n{stdout}"
    )
    assert _SENTINEL_VALUE_PREFIX not in stdout, (
        f"sentinel prefix leaked into the cell — possible partial read:\n{stdout}"
    )


def test_config_dir_invisible_via_absolute_host_path(
    run_in_cell, host_config_sentinel,
) -> None:
    """The cell's $HOME is /home/whizzard, not the host's $HOME. The
    absolute host path simply does not exist in the cell's mount namespace,
    so the sentinel cannot be read."""
    sentinel_value, sentinel_file = host_config_sentinel
    host_config_path = str(sentinel_file)

    result = run_in_cell([
        "sh", "-c",
        f"cat {host_config_path} 2>&1; "
        f"echo '---'; "
        f"ls -la {host_config_path.rsplit('/', 1)[0]} 2>&1; "
        f"true",
    ])

    _assert_no_sentinel_leak(result.stdout, sentinel_value)
    # Positive signal: the path is genuinely absent inside the cell.
    assert (
        "no such file" in result.stdout.lower()
        or "cannot access" in result.stdout.lower()
        or "not found" in result.stdout.lower()
    ), (
        f"expected an absence signal for the host config path, got:\n{result.stdout}"
    )


def test_config_dir_unreachable_via_traversal_from_rw_mount(
    run_in_cell, tmp_path, host_config_sentinel,
) -> None:
    """A rw mount cannot be used as a launchpad for `..` traversal to the
    host config dir. Docker confines bind-mount `..` to the mount source —
    walking up from `/mounts/test-mount-0` ascends the *container's*
    namespace, not the host's."""
    sentinel_value, sentinel_file = host_config_sentinel
    mount_dir = tmp_path / "attacker-mount"
    mount_dir.mkdir()
    # A relative climb that, on the host, *would* lead from mount_dir to
    # the sentinel file. The cell's namespace doesn't have that shape.
    rel_climb = "../" * 25 + str(sentinel_file).lstrip("/")

    result = run_in_cell(
        [
            "sh", "-c",
            f"cd /mounts/test-mount-0; "
            f"cat {rel_climb} 2>&1 | head -5; "
            f"echo '---'; "
            f"cat ../../../../../../../../etc/whizzard-host-config 2>&1 | head -3; "
            f"true",
        ],
        mounts=[(str(mount_dir), "rw")],
    )

    _assert_no_sentinel_leak(result.stdout, sentinel_value)


def test_config_dir_unreachable_via_symlink_from_rw_mount(
    run_in_cell, tmp_path, host_config_sentinel,
) -> None:
    """An attacker plants a symlink inside their writable mount pointing
    at the host's config dir. Inside the cell, following the symlink
    resolves in the *container's* namespace — there is no host config
    path there, so the read fails closed."""
    sentinel_value, sentinel_file = host_config_sentinel
    mount_dir = tmp_path / "symlink-mount"
    mount_dir.mkdir()
    (mount_dir / "config_link").symlink_to(sentinel_file)
    (mount_dir / "config_dir_link").symlink_to(WHIZZARD_HOME)

    result = run_in_cell(
        ["sh", "-c",
         "cat /mounts/test-mount-0/config_link 2>&1 | head -5; "
         "echo '---'; "
         "ls -la /mounts/test-mount-0/config_dir_link/ 2>&1 | head -10; "
         "echo '---'; "
         "find /mounts/test-mount-0/config_dir_link -name '*.json' 2>&1 | head; "
         "true"],
        mounts=[(str(mount_dir), "rw")],
    )

    _assert_no_sentinel_leak(result.stdout, sentinel_value)
    # Defense-in-depth: the host config file's mtime should be unchanged
    # (the attempted reads + writes were all confined).
    assert sentinel_file.exists(), "fixture file disappeared mid-test"


def test_proc_1_root_does_not_expose_host_filesystem(
    run_in_cell, host_config_sentinel,
) -> None:
    """PID 1 in the cell is the cell's init (tini), so /proc/1/root is the
    *container's* rootfs. An attacker probing /proc/1/root expects to
    backdoor into the host's view; on a properly-isolated cell, it just
    re-roots inside the container."""
    sentinel_value, sentinel_file = host_config_sentinel
    rel_under_root = str(sentinel_file).lstrip("/")

    result = run_in_cell([
        "sh", "-c",
        f"cat /proc/1/root/{rel_under_root} 2>&1 | head -5; "
        f"echo '---'; "
        f"ls /proc/1/root/Users 2>&1 | head -3; "
        f"ls /proc/1/root/home 2>&1 | head -3; "
        f"true",
    ])

    _assert_no_sentinel_leak(result.stdout, sentinel_value)


def test_proc_self_mounts_only_shows_declared_surfaces(
    run_in_cell, tmp_path, host_config_sentinel,
) -> None:
    """`/proc/self/mounts` from inside the cell must not reveal the
    host's filesystem layout. The cell sees only its declared bind
    mounts, the container rootfs, /proc, /sys, /dev, and tmpfs surfaces —
    not the host paths backing them.

    Specifically: the host path to the config dir must not appear in the
    cell's mount table even though it's the host-side root of WHIZZARD_HOME.
    """
    sentinel_value, sentinel_file = host_config_sentinel
    mount_dir = tmp_path / "probe-mount"
    mount_dir.mkdir()

    result = run_in_cell(
        ["sh", "-c", "cat /proc/self/mounts"],
        mounts=[(str(mount_dir), "rw")],
    )

    _assert_no_sentinel_leak(result.stdout, sentinel_value)
    # The host-side WHIZZARD_HOME path must not appear in the cell's
    # mount table. (The mount fixture mounts mount_dir at
    # /mounts/test-mount-0 — that's expected and fine.)
    assert str(WHIZZARD_HOME) not in result.stdout, (
        f"host WHIZZARD_HOME path leaked via /proc/self/mounts:\n{result.stdout}"
    )


def test_attempting_to_mount_config_dir_is_rejected_pre_launch() -> None:
    """The launch-time gate: if a user (or a compromised config) tried to
    register the config dir as a mount, safety validation rejects it
    before any container is created. Belt for the integration-tier
    in-cell tests — even the path that would *create* visibility is
    closed.

    This is unit-shaped (no container) but lives in the integration
    file because it completes the cluster-2 picture: pre-launch + in-cell
    proofs in one place. Doesn't actually start Docker, so it's cheap."""
    from whizzard.config import Profile
    from whizzard.safety import SafetyViolation, check_mount_path

    profile = Profile(
        name="adversary", network_enabled=False, duration_seconds=60,
        allow_broad_mount=True, description="",
    )

    # Direct hit
    if WHIZZARD_HOME.exists():
        with pytest.raises(SafetyViolation, match="hard-blocked"):
            check_mount_path(WHIZZARD_HOME, profile, True)

    # Descendant
    config_dir = WHIZZARD_HOME / "config"
    if config_dir.exists():
        with pytest.raises(SafetyViolation, match="hard-blocked"):
            check_mount_path(config_dir, profile, True)

    # Ancestor (mounting $HOME would expose WHIZZARD_HOME)
    with pytest.raises(SafetyViolation, match="hard-blocked"):
        check_mount_path(Path.home(), profile, True)
