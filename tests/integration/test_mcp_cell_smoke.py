"""In-cell MCP cooperation-layer deployment — smoke (D-167, Stage 9 + 14).

Verifies that whizzard-hermes:latest carries the pieces needed to run the
in-cell Whiz MCP server: the `mcp` SDK is importable, the standalone
`mcp_server.py` is reachable at the expected path, and the tool functions
execute in the cell environment.

D-167: `mcp_server.py` is COPY'd in as a standalone script (NOT installed as
part of the whizzard package — that would leak the policy-layer
implementation). The full MCP-protocol stdio round-trip with a real Hermes
client is heavier and remains the next-level Hermes-integration smoke.
"""

from __future__ import annotations

import json
import subprocess

import pytest

pytestmark = pytest.mark.integration


def test_mcp_sdk_installed_in_hermes_cell(whizzard_hermes_image: str) -> None:
    """The mcp SDK installed by Dockerfile.hermes is importable in the cell."""
    result = subprocess.run(
        ["docker", "run", "--rm", whizzard_hermes_image,
         "python3", "-c", "import mcp"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, (
        f"mcp not importable in the Hermes cell — Dockerfile.hermes drift?\n"
        f"stderr: {result.stderr}"
    )


def test_mcp_server_script_present_in_hermes_cell(whizzard_hermes_image: str) -> None:
    """mcp_server.py is COPY'd into /opt/whiz/ as a standalone script
    (D-167); the cell ships exactly that one file, not the whizzard package."""
    result = subprocess.run(
        ["docker", "run", "--rm", whizzard_hermes_image,
         "sh", "-c",
         "test -f /opt/whiz/mcp_server.py && wc -l < /opt/whiz/mcp_server.py"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    line_count = int(result.stdout.strip())
    # Sanity check: the script is non-trivial and matches the host source.
    assert line_count > 100, f"mcp_server.py looks truncated ({line_count} lines)"


def test_whizzard_package_NOT_installed_in_cell(whizzard_hermes_image: str) -> None:
    """D-167 invariant: the full whizzard package must NOT be installed in
    the cell. Reading e.g. enforcement.py from inside would let a compromised
    agent map the policy layer (idle-detection signals etc.). Only the
    cooperation-layer surface — mcp_server.py — should be reachable."""
    result = subprocess.run(
        ["docker", "run", "--rm", whizzard_hermes_image,
         "python3", "-c",
         "import whizzard"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode != 0, (
        "the `whizzard` package is importable inside the cell — D-167 violated"
    )
    assert "ModuleNotFoundError" in result.stderr or "No module" in result.stderr


def test_mcp_server_tool_functions_callable_in_cell(whizzard_hermes_image: str) -> None:
    """mcp_server.py's tool functions execute in the cell. Probed with
    whiz_status pointing at a missing snapshot path — expecting the structured
    error response, not an exception."""
    result = subprocess.run(
        ["docker", "run", "--rm",
         "-e", "WHIZ_SNAPSHOT_PATH=/nope",
         whizzard_hermes_image,
         "python3", "-c",
         "import sys; sys.path.insert(0, '/opt/whiz'); "
         "from mcp_server import tool_whiz_status; "
         "import json; print(json.dumps(tool_whiz_status()))"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip())
    assert "error" in payload
    assert "/nope" in payload["error"]
