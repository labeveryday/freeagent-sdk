"""
MCP client — wraps the mcp Python SDK to manage server lifecycle.

Supports:
- stdio transport: spawn a subprocess and communicate via stdin/stdout
- streamable HTTP transport: connect to a running HTTP server
"""

from __future__ import annotations

import shlex
from typing import Any

from ..tool import Tool
from .adapter import mcp_tools_to_freeagent


class MCPClient:
    """Manages connection to an MCP server."""

    def __init__(self):
        self._session = None
        self._read = None
        self._write = None
        self._cm = None

    async def connect_stdio(self, command: str, env: dict[str, str] | None = None):
        """Connect to an MCP server via stdio transport."""
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError:
            raise ImportError(
                "MCP support requires the 'mcp' package. "
                "Install with: pip install freeagent-sdk[mcp]"
            )

        parts = shlex.split(command)
        server_params = StdioServerParameters(
            command=parts[0],
            args=parts[1:],
            env=env,
        )

        self._cm = stdio_client(server_params)
        self._read, self._write = await self._cm.__aenter__()
        self._session = ClientSession(self._read, self._write)
        await self._session.__aenter__()
        await self._session.initialize()

    async def connect_http(self, url: str):
        """Connect to an MCP server via streamable HTTP transport."""
        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import streamablehttp_client
        except ImportError:
            raise ImportError(
                "MCP support requires the 'mcp' package. "
                "Install with: pip install freeagent-sdk[mcp]"
            )

        self._cm = streamablehttp_client(url)
        self._read, self._write, _ = await self._cm.__aenter__()
        self._session = ClientSession(self._read, self._write)
        await self._session.__aenter__()
        await self._session.initialize()

    async def list_tools(self) -> list[Tool]:
        """Get all tools from the MCP server as FreeAgent Tool objects."""
        if not self._session:
            raise RuntimeError("Not connected. Call connect_stdio() or connect_http() first.")

        result = await self._session.list_tools()
        return mcp_tools_to_freeagent(result.tools, self._session)

    async def close(self):
        """Disconnect from the MCP server."""
        if self._session:
            try:
                await self._session.__aexit__(None, None, None)
            except Exception:
                pass
            self._session = None

        if self._cm:
            try:
                await self._cm.__aexit__(None, None, None)
            except Exception:
                pass
            self._cm = None
