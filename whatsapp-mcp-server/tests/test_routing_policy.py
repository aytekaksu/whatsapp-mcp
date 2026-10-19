"""Routing guidance delivered to AI clients over the MCP protocol."""

import sys
from pathlib import Path

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def test_mcp_advertises_whatsapp_routing_policy():
    server_dir = Path(__file__).resolve().parents[1]
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(server_dir / "main.py")],
        env={"WHATSAPP_MCP_TRANSPORT": "stdio", "PYTHONDONTWRITEBYTECODE": "1"},
    )
    with anyio.fail_after(20):
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                initialized = await session.initialize()
                tool_list = await session.list_tools()

    # Codex uses the first 512 characters when deciding how to use a server.
    assert initialized.instructions is not None
    summary = initialized.instructions[:512]
    assert "Always use this WhatsApp MCP server for WhatsApp requests." in summary
    assert "unless the user explicitly requests UI use" in summary
    assert "do not silently fall back to the app or web UI" in summary

    # Tool descriptions must also carry the rule for clients that omit instructions.
    assert tool_list.tools
    for tool in tool_list.tools:
        assert (
            "Use this WhatsApp MCP tool directly; do not use the desktop app or web UI "
            "unless the user explicitly requests UI use."
        ) in " ".join((tool.description or "").split()), tool.name
