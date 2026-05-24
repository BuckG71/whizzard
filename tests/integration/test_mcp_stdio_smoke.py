"""Whiz MCP server — stdio protocol round-trip smoke (D-156 + D-167).

The fullest cell-side cooperation-layer test: spawn `mcp_server.py` inside a
whizzard-hermes cell via `docker run -i`, talk to it as an MCP client over
stdio (the same path Hermes-the-harness will use), initialize the session,
list the registered tools, and call `whiz_status` with a real snapshot
mounted into the cell. Verifies the FastMCP server actually starts, speaks
MCP correctly, and renders the tool's return value back to the client.

Closes the "the MCP cooperation layer never spoke its own protocol for real"
half of the Stage 9 + 14 blind spot. The Hermes auto-wiring of the
config.yaml MCP entry remains the (separate) follow-up.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

pytestmark = pytest.mark.integration

_EXPECTED_TOOLS = {
    "whiz_status", "whiz_audit_self", "whiz_emit_event",
    "whiz_request_mount", "whiz_request_extend", "whiz_check_request",
}
# F-B1/C1 (catch-up review pass 2): `whiz_list_presets` was removed in
# F-E-01 (it was a shipped stub returning []). This smoke was passing
# only because the running cell image hadn't been rebuilt to drop the
# tool; the next `whiz image build` would have flipped this assertion to
# failing. Same drift class as F-F-01 (integration not in `make check`).


async def _exercise(image: str, snap_dir: str):
    """Spawn the cell-hosted MCP server, initialize, list tools, call
    whiz_status, return the relevant pieces of the conversation."""
    params = StdioServerParameters(
        command="docker",
        args=[
            "run", "-i", "--rm",
            "-v", f"{snap_dir}:/whiz-test:ro",
            "-e", "WHIZ_SNAPSHOT_PATH=/whiz-test/snap.json",
            "-e", "WHIZ_SESSION_ID=smoke-mcp",
            image,
            "python3", "/opt/whiz/mcp_server.py",
        ],
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        tool_list = await session.list_tools()
        status_result = await session.call_tool("whiz_status", {})
        return tool_list, status_result


def test_mcp_server_speaks_its_protocol_end_to_end(
    whizzard_hermes_image: str, tmp_path
) -> None:
    """Full MCP round-trip through docker stdio: initialize, list_tools,
    call_tool('whiz_status'). The snapshot is mounted read-only into the
    cell; whiz_status returns it; the response comes back over the MCP wire."""
    snap_dir = tmp_path / "snap"
    snap_dir.mkdir()
    snapshot = {
        "session_id": "smoke-mcp",
        "profile": {
            "name": "safe", "network_enabled": False,
            "duration_seconds": None, "allow_broad_mount": False,
            "description": "stdio smoke",
        },
        "mounts": [],
        "harness": "test-harness",
        "snapshot_written_at": "2026-05-22T00:00:00+00:00",
    }
    (snap_dir / "snap.json").write_text(json.dumps(snapshot))

    tool_list, status_result = asyncio.run(
        asyncio.wait_for(_exercise(whizzard_hermes_image, str(snap_dir)),
                         timeout=45),
    )

    # All seven registered tools should be advertised by the server.
    tool_names = {t.name for t in tool_list.tools}
    assert tool_names >= _EXPECTED_TOOLS, f"missing tools: {_EXPECTED_TOOLS - tool_names}"

    # whiz_status returned the mounted snapshot — confirms the tool actually
    # executed in the cell with the env var pointing at the bind-mounted file.
    text_parts = [c.text for c in status_result.content if hasattr(c, "text")]
    blob = "\n".join(text_parts)
    assert "smoke-mcp" in blob, f"snapshot session_id missing from response: {blob}"
    assert "test-harness" in blob, f"snapshot harness missing from response: {blob}"
