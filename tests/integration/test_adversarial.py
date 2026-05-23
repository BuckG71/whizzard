"""Adversarial containment smoke — real-Docker probe-and-assert tests.

Each test launches a real contained cell, has it *attempt* to observe or do
something the containment model must prevent, and asserts the attempt was
blocked. These are probes, not payloads: a containment failure shows up as a
pytest assertion failure, never as host damage. Extra margin — on Docker
Desktop the cell runs inside the Docker VM, so even a genuine hole lands in
the VM, not the host OS.

This is the start of the Stage 20 red-team suite, one test per containment
invariant from architecture.md. Gated on real Docker per `conftest.py`; run
with `make integration` or `pytest -m integration`.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_docker_socket_not_reachable(run_in_cell) -> None:
    """The cell must not see the Docker socket. Reaching it would be a full
    host escape — the agent could launch its own uncontained containers
    (D-9 one-way capability flow; D-164 OIQ owns the docker surface)."""
    result = run_in_cell([
        "sh", "-c",
        "test -e /var/run/docker.sock && echo PRESENT || echo absent",
    ])
    assert result.returncode == 0, result.stderr
    assert "absent" in result.stdout
    assert "PRESENT" not in result.stdout


def test_all_capabilities_dropped(run_in_cell) -> None:
    """`--cap-drop=ALL` plus a non-root user means the cell's effective
    capability set is empty. A non-zero CapEff would mean the contained
    process can still perform privileged kernel operations."""
    result = run_in_cell(["sh", "-c", "grep CapEff /proc/self/status"])
    assert result.returncode == 0, result.stderr
    assert "0000000000000000" in result.stdout, (
        f"effective capabilities not fully dropped — containment weakened: "
        f"{result.stdout!r}"
    )


def test_network_off_profile_blocks_egress(run_in_cell) -> None:
    """A network-disabled profile (`safe` → `--network none`) gives the cell
    no egress: the contained agent cannot reach the internet."""
    result = run_in_cell(
        [
            "sh", "-c",
            "curl -s --max-time 5 https://example.com >/dev/null 2>&1 "
            "&& echo REACHED || echo blocked",
        ],
        profile="safe",
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "blocked" in result.stdout
    assert "REACHED" not in result.stdout


# --- mount-boundary probes -------------------------------------------------
# The host side stages a layout the attacker would engineer (a mounted
# subdir alongside an off-limits sibling, a hostile symlink inside a mount,
# a read-only mount). The cell tries every plausible escape; the assertions
# verify Docker bind-mount semantics + the OIQ flag set hold.


def test_mount_isolates_filesystem_outside_the_bind(
    run_in_cell, tmp_path,
) -> None:
    """A mounted subdir does NOT expose the host's sibling/parent directories
    — neither via `..` from inside the mount, nor via any absolute path."""
    inside = tmp_path / "inside"
    outside = tmp_path / "outside"
    inside.mkdir()
    outside.mkdir()
    (inside / "secret-inside").write_text("INSIDE_DATA_42")
    (outside / "secret-outside").write_text("OUTSIDE_DATA_99")

    result = run_in_cell(
        ["sh", "-c",
         "cat /mounts/test-mount-0/secret-inside; "
         "echo '---'; "
         "cat /mounts/test-mount-0/../../secret-outside 2>&1 | head -1; "
         f"cat {outside}/secret-outside 2>&1 | head -1; "
         "find / -name 'secret-outside' 2>/dev/null | head"],
        mounts=[(str(inside), "ro")],
    )

    assert "INSIDE_DATA_42" in result.stdout, "the mount itself is unreadable"
    # The sibling's content must not leak through any access path.
    assert "OUTSIDE_DATA_99" not in result.stdout, (
        f"host filesystem outside the mount leaked into the cell:\n{result.stdout}"
    )


def test_hostile_symlink_in_mount_resolves_in_container_namespace(
    run_in_cell, tmp_path,
) -> None:
    """An attacker plants a symlink inside a mount pointing at an absolute
    host path (e.g. /etc/passwd). When the cell follows it, the kernel
    resolves the link in the *container's* namespace — so the cell reads
    the container's /etc/passwd, not the host's. (Docker bind-mount +
    symlink containment.)"""
    mount_dir = tmp_path / "hostile-mount"
    mount_dir.mkdir()
    (mount_dir / "evil_link").symlink_to("/etc/passwd")

    result = run_in_cell(
        ["sh", "-c", "cat /mounts/test-mount-0/evil_link 2>&1 | head -5"],
        mounts=[(str(mount_dir), "ro")],
    )

    # The container's debian /etc/passwd has the canonical "root:x:0:0" entry.
    assert "root:x:0:0" in result.stdout, (
        f"symlink follow did not resolve to the container's /etc/passwd:\n"
        f"{result.stdout}"
    )
    # macOS /etc/passwd starts with the "# User Database" comment banner —
    # its absence here confirms the host's /etc/passwd was NOT leaked.
    assert "User Database" not in result.stdout, (
        f"host /etc/passwd leaked through the hostile symlink:\n{result.stdout}"
    )


def test_readonly_mount_blocks_writes(run_in_cell, tmp_path) -> None:
    """An `:ro` mount is genuinely read-only — writes through the cell fail
    even though the agent runs as a user with general write capability on
    other paths."""
    ro_dir = tmp_path / "ro-mount"
    ro_dir.mkdir()
    (ro_dir / "existing.txt").write_text("untouched")

    result = run_in_cell(
        ["sh", "-c",
         "(echo new > /mounts/test-mount-0/new.txt) 2>&1; "
         "echo '---'; "
         "cat /mounts/test-mount-0/existing.txt"],
        mounts=[(str(ro_dir), "ro")],
    )

    assert "untouched" in result.stdout, "existing read should succeed"
    # The write should have failed — "Read-only file system" / "Permission".
    lower = result.stdout.lower()
    assert "read-only" in lower or "permission" in lower, (
        f"writing to an :ro mount appeared to succeed:\n{result.stdout}"
    )
    # And confirm host-side: no new file landed.
    assert not (ro_dir / "new.txt").exists(), "host-side write leak via :ro mount"

