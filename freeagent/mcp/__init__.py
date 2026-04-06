"""
MCP (Model Context Protocol) support for FreeAgent SDK.

Connects to MCP servers and adapts their tools for use with agents.
Requires: pip install freeagent-sdk[mcp]

Usage:
    from freeagent.mcp import connect

    async with connect("npx -y @modelcontextprotocol/server-filesystem /tmp") as tools:
        agent = Agent(model="qwen3:8b", tools=tools)
        result = await agent.arun("List files in /tmp")
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from ..tool import Tool


@asynccontextmanager
async def connect(
    command: str | None = None,
    url: str | None = None,
    env: dict[str, str] | None = None,
) -> AsyncIterator[list[Tool]]:
    """
    Connect to an MCP server and yield its tools as FreeAgent Tool objects.

    Args:
        command: Shell command to start a stdio MCP server (e.g., "npx -y @mcp/server")
        url: URL for a streamable HTTP MCP server (e.g., "http://localhost:3000/mcp")
        env: Extra environment variables for stdio servers

    Yields:
        List of Tool objects from the MCP server
    """
    from .client import MCPClient

    client = MCPClient()
    try:
        if command:
            await client.connect_stdio(command, env=env)
        elif url:
            await client.connect_http(url)
        else:
            raise ValueError("Provide either 'command' (stdio) or 'url' (HTTP)")

        tools = await client.list_tools()
        yield tools
    finally:
        await client.close()
