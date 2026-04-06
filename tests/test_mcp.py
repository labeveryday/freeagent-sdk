"""Tests for MCP adapter — schema conversion, description truncation, tool index."""

from freeagent.mcp.adapter import (
    _extract_params, _convert_tool, build_tool_index,
    MAX_DESCRIPTION_CHARS,
)
from freeagent.tool import Tool, ToolParam


class MockMCPTool:
    """Mock MCP tool definition."""
    def __init__(self, name, description="", input_schema=None):
        self.name = name
        self.description = description
        self.inputSchema = input_schema or {}


class MockSession:
    """Mock MCP session."""
    async def call_tool(self, name, arguments=None):
        return MockResult([MockContent(f"result for {name}")])


class MockResult:
    def __init__(self, content):
        self.content = content


class MockContent:
    def __init__(self, text):
        self.text = text


class TestExtractParams:
    def test_basic_properties(self):
        schema = {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name"},
                "units": {"type": "string", "description": "Temperature units"},
            },
            "required": ["city"],
        }
        params = _extract_params(schema)
        assert len(params) == 2
        city = next(p for p in params if p.name == "city")
        assert city.type == "string"
        assert city.required is True
        units = next(p for p in params if p.name == "units")
        assert units.required is False

    def test_integer_type(self):
        schema = {
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
            },
            "required": ["count"],
        }
        params = _extract_params(schema)
        assert params[0].type == "integer"

    def test_empty_schema(self):
        params = _extract_params({})
        assert params == []

    def test_no_required(self):
        schema = {
            "type": "object",
            "properties": {"x": {"type": "string"}},
        }
        params = _extract_params(schema)
        assert params[0].required is False

    def test_default_value(self):
        schema = {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 10},
            },
        }
        params = _extract_params(schema)
        assert params[0].default == 10


class TestConvertTool:
    def test_basic_conversion(self):
        mcp_tool = MockMCPTool(
            name="weather",
            description="Get weather for a city",
            input_schema={
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City"},
                },
                "required": ["city"],
            },
        )
        tool = _convert_tool(mcp_tool, MockSession())
        assert isinstance(tool, Tool)
        assert tool.name == "weather"
        assert tool.description == "Get weather for a city"
        assert len(tool.params) == 1
        assert tool.params[0].name == "city"

    def test_description_truncation(self):
        long_desc = "x" * 200
        mcp_tool = MockMCPTool(name="verbose", description=long_desc)
        tool = _convert_tool(mcp_tool, MockSession())
        assert len(tool.description) <= MAX_DESCRIPTION_CHARS

    def test_empty_description(self):
        mcp_tool = MockMCPTool(name="nodesс", description="")
        tool = _convert_tool(mcp_tool, MockSession())
        assert tool.description == ""

    def test_no_input_schema(self):
        mcp_tool = MockMCPTool(name="simple", input_schema=None)
        tool = _convert_tool(mcp_tool, MockSession())
        assert tool.params == []


class TestMCPToolExecution:
    async def test_call_mcp_tool(self):
        mcp_tool = MockMCPTool(
            name="test_tool",
            description="Test",
            input_schema={
                "type": "object",
                "properties": {"q": {"type": "string"}},
                "required": ["q"],
            },
        )
        tool = _convert_tool(mcp_tool, MockSession())
        result = await tool.execute(q="hello")
        assert result.success
        assert "result for test_tool" in str(result.data)


class TestBuildToolIndex:
    def test_builds_index(self):
        tools = [
            Tool(name="weather", description="Get weather", params=[]),
            Tool(name="search", description="Search the web", params=[]),
        ]
        index = build_tool_index(tools)
        assert "## Available Tools" in index
        assert "weather" in index
        assert "search" in index

    def test_empty_tools(self):
        index = build_tool_index([])
        assert "Available Tools" in index
