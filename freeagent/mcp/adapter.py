"""
MCP → FreeAgent adapter — converts MCP tool schemas to FreeAgent Tool objects.

MCP tools have JSON Schema parameters. We convert these to our ToolParam format
and create callable Tool objects that invoke the MCP server.
"""

from __future__ import annotations

from typing import Any

from ..tool import Tool, ToolParam, ToolResult


# JSON Schema type → our type string
_JSON_SCHEMA_TYPES = {
    "string": "string",
    "integer": "integer",
    "number": "number",
    "boolean": "boolean",
    "array": "array",
    "object": "object",
}

MAX_DESCRIPTION_CHARS = 100


def mcp_tools_to_freeagent(mcp_tools: list, session: Any) -> list[Tool]:
    """
    Convert a list of MCP tool definitions to FreeAgent Tool objects.

    Each tool becomes a callable Tool that invokes the MCP server
    via the session when executed.
    """
    tools = []
    for mcp_tool in mcp_tools:
        tool = _convert_tool(mcp_tool, session)
        if tool:
            tools.append(tool)
    return tools


def _convert_tool(mcp_tool: Any, session: Any) -> Tool | None:
    """Convert a single MCP tool to a FreeAgent Tool."""
    name = mcp_tool.name
    description = mcp_tool.description or ""

    # Truncate verbose descriptions for small model context budgets
    if len(description) > MAX_DESCRIPTION_CHARS:
        description = description[:MAX_DESCRIPTION_CHARS - 3] + "..."

    # Extract parameters from JSON schema
    params = _extract_params(mcp_tool.inputSchema or {})

    # Create a callable that invokes the MCP server
    async def _call_mcp(**kwargs):
        result = await session.call_tool(name, arguments=kwargs)
        # MCP returns content as a list of content blocks
        if result.content:
            texts = []
            for block in result.content:
                if hasattr(block, "text"):
                    texts.append(block.text)
                else:
                    texts.append(str(block))
            return "\n".join(texts)
        return ""

    return Tool(
        name=name,
        description=description,
        params=params,
        fn=_call_mcp,
    )


def _extract_params(schema: dict) -> list[ToolParam]:
    """Extract ToolParams from a JSON Schema properties dict."""
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    params = []

    for name, prop in properties.items():
        json_type = prop.get("type", "string")
        our_type = _JSON_SCHEMA_TYPES.get(json_type, "string")
        desc = prop.get("description", "")

        params.append(ToolParam(
            name=name,
            type=our_type,
            description=desc[:80] if desc else "",
            required=name in required,
            default=prop.get("default"),
        ))

    return params


def build_tool_index(tools: list[Tool]) -> str:
    """
    Build a tool index for the system prompt when there are many tools.
    Auto-prepended when total tools > 10.
    """
    lines = ["## Available Tools\n"]
    for t in tools:
        lines.append(f"- **{t.name}**: {t.description}")
    return "\n".join(lines)
