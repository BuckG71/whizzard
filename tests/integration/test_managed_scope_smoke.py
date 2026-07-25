"""Integration smoke: real Hermes reads Whizzard's managed-scope config (D-194).

Validates the genuinely novel piece of Phase B end-to-end: Whizzard authors a
managed-scope `config.yaml` as JSON (a valid YAML subset, so no YAML dep), and
the REAL Hermes 0.19 loader in the cell must parse it and merge the authored
leaves — auto-registering the Whiz MCP server (retires the D-167 manual step)
and, when enabled, the web backend. The adapter mount/env wiring is covered by
unit tests (`test_hermes_adapter.py`); this proves the cell actually consumes
what we write.
"""

import subprocess

import pytest

from whizzard.adapters import hermes as hermes_module

pytestmark = pytest.mark.integration

# In-cell config check: point Hermes at the mounted managed dir + an empty
# HERMES_HOME (no user config), load config via Hermes's OWN loader, and assert
# the authored leaves merged. If JSON weren't valid YAML, or managed scope
# weren't honored in 0.19, this raises inside the cell and the run fails.
_CELL_CHECK = (
    "import os; os.makedirs('/tmp/hh', exist_ok=True); "
    "os.environ['HERMES_HOME']='/tmp/hh'; "
    "from hermes_cli.config import load_config_readonly as L; c=L(); "
    "assert c.get('mcp_servers',{}).get('whiz',{}).get('command')=='python3', "
    "('whiz mcp not registered from managed scope', c.get('mcp_servers')); "
    "assert c.get('web',{}).get('backend')=='firecrawl', "
    "('web backend not merged', c.get('web')); "
    "print('MANAGED_OK')"
)


def test_real_hermes_reads_managed_scope_config(whizzard_hermes_image):
    """Author the managed dir with the real writer, mount it read-only into the
    cell exactly as the adapter does, and confirm Hermes 0.19 merges it."""
    session_id = "smoke-managed-scope"
    managed_dir = hermes_module._write_managed_dir(session_id, "firecrawl")
    try:
        result = subprocess.run(
            [
                "docker", "run", "--rm",
                "-v", f"{managed_dir}:{hermes_module._IN_CELL_MANAGED_DIR}:ro",
                "-e", f"{hermes_module.ENV_HERMES_MANAGED_DIR}="
                      f"{hermes_module._IN_CELL_MANAGED_DIR}",
                "--entrypoint", "python3",
                whizzard_hermes_image,
                "-c", _CELL_CHECK,
            ],
            capture_output=True, text=True, timeout=90,
        )
    finally:
        hermes_module.cleanup_managed_dir(session_id)

    assert result.returncode == 0, (
        f"Hermes did not merge the managed-scope config:\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "MANAGED_OK" in result.stdout, result.stdout


def test_managed_mount_is_read_only_in_cell(whizzard_hermes_image):
    """The agent must not be able to edit the authored config — the mount is
    read-only, so a write attempt inside the cell fails."""
    session_id = "smoke-managed-ro"
    managed_dir = hermes_module._write_managed_dir(session_id, "off")
    try:
        result = subprocess.run(
            [
                "docker", "run", "--rm",
                "-v", f"{managed_dir}:{hermes_module._IN_CELL_MANAGED_DIR}:ro",
                "--entrypoint", "sh",
                whizzard_hermes_image,
                "-c", f"echo pwned > {hermes_module._IN_CELL_MANAGED_DIR}/config.yaml",
            ],
            capture_output=True, text=True, timeout=60,
        )
    finally:
        hermes_module.cleanup_managed_dir(session_id)

    assert result.returncode != 0, (
        "write to the managed config succeeded — mount is not read-only"
    )
    assert "read-only" in (result.stdout + result.stderr).lower()
