"""
FreeAgent — MCP Tool Support

Connect to MCP servers and use their tools with your agent.
Requires: pip install freeagent-sdk[mcp]

This example connects to the filesystem MCP server and lets
the agent read files.

    pip install freeagent-sdk[mcp]
    ollama pull qwen3:8b
    python examples/06_mcp.py
"""

import asyncio
from freeagent import Agent
from freeagent.mcp import connect


async def main():
    # Connect to the filesystem MCP server via stdio
    async with connect("npx -y @modelcontextprotocol/server-filesystem /tmp") as tools:
        agent = Agent(
            model="qwen3:8b",
            tools=tools,
            system_prompt="You are a helpful file assistant. Use the available tools to help users.",
        )

        response = await agent.arun("List the files in /tmp")
        print(response)
        print(agent.metrics)


if __name__ == "__main__":
    asyncio.run(main())
