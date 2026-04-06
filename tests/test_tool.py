"""Tests for @tool decorator, schema generation, ToolResult, async execution."""

import pytest
from freeagent.tool import tool, Tool, ToolResult, ToolParam


class TestToolDecorator:
    def test_basic_decorator(self):
        @tool
        def greet(name: str) -> str:
            """Say hello."""
            return f"Hello, {name}!"

        assert isinstance(greet, Tool)
        assert greet.name == "greet"
        assert greet.description == "Say hello."
        assert len(greet.params) == 1
        assert greet.params[0].name == "name"
        assert greet.params[0].type == "string"

    def test_decorator_with_args(self):
        @tool(name="get_weather", description="Fetch weather data")
        def weather(city: str) -> dict:
            return {"temp": 72}

        assert weather.name == "get_weather"
        assert weather.description == "Fetch weather data"

    def test_type_mapping(self):
        @tool
        def multi(s: str, i: int, f: float, b: bool, l: list, d: dict):
            """Multi-type."""
            pass

        types = {p.name: p.type for p in multi.params}
        assert types == {
            "s": "string", "i": "integer", "f": "number",
            "b": "boolean", "l": "array", "d": "object",
        }

    def test_optional_params(self):
        @tool
        def search(q: str, limit: int = 10):
            """Search."""
            pass

        q_param = next(p for p in search.params if p.name == "q")
        limit_param = next(p for p in search.params if p.name == "limit")
        assert q_param.required is True
        assert limit_param.required is False
        assert limit_param.default == 10


class TestSchema:
    def test_schema_generation(self):
        @tool
        def calc(a: int, b: int):
            """Add numbers."""
            pass

        schema = calc.schema()
        assert schema["type"] == "object"
        assert "a" in schema["properties"]
        assert "b" in schema["properties"]
        assert schema["required"] == ["a", "b"]

    def test_ollama_spec(self):
        @tool
        def calc(a: int):
            """Add."""
            pass

        spec = calc.to_ollama_spec()
        assert spec["type"] == "function"
        assert spec["function"]["name"] == "calc"
        assert "parameters" in spec["function"]

    def test_react_description(self):
        @tool
        def calc(a: int):
            """Add numbers."""
            pass

        desc = calc.to_react_description()
        assert "calc" in desc
        assert "Add numbers" in desc
        assert "a" in desc


class TestToolResult:
    def test_ok(self):
        r = ToolResult.ok(42)
        assert r.success is True
        assert r.data == 42
        assert r.error is None

    def test_fail(self):
        r = ToolResult.fail("bad input")
        assert r.success is False
        assert r.error == "bad input"

    def test_to_message_success(self):
        assert ToolResult.ok("hello").to_message() == "hello"
        assert ToolResult.ok(42).to_message() == "42"

    def test_to_message_dict(self):
        import json
        r = ToolResult.ok({"a": 1})
        assert json.loads(r.to_message()) == {"a": 1}

    def test_to_message_error(self):
        import json
        r = ToolResult.fail("oops")
        msg = json.loads(r.to_message())
        assert msg["error"] == "oops"


class TestExecution:
    @pytest.mark.asyncio
    async def test_sync_function(self):
        @tool
        def add(a: int, b: int) -> int:
            """Add two numbers."""
            return a + b

        result = await add.execute(a=1, b=2)
        assert result.success
        assert result.data == 3

    @pytest.mark.asyncio
    async def test_async_function(self):
        @tool
        async def async_add(a: int, b: int) -> int:
            """Add async."""
            return a + b

        result = await async_add.execute(a=5, b=3)
        assert result.success
        assert result.data == 8

    @pytest.mark.asyncio
    async def test_exception_returns_fail(self):
        @tool
        def broken():
            """Always fails."""
            raise ValueError("boom")

        result = await broken.execute()
        assert not result.success
        assert "boom" in result.error
