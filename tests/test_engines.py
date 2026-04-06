"""Tests for engines — NativeEngine and ReactEngine with mock providers."""

import pytest
from freeagent.engines import NativeEngine, ReactEngine, EngineResult
from freeagent.messages import Message
from freeagent.tool import tool, Tool
from freeagent.providers import ProviderResponse


class MockProvider:
    """Mock provider for testing engines."""

    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.model = "mock"
        self._call_count = 0

    async def chat(self, messages, temperature=0.1):
        return self._next_response()

    async def chat_with_tools(self, messages, tools, temperature=0.1):
        return self._next_response()

    async def chat_with_format(self, messages, schema, temperature=0.1):
        resp = self._next_response()
        return resp.content

    def _next_response(self):
        if self._call_count < len(self.responses):
            resp = self.responses[self._call_count]
            self._call_count += 1
            return resp
        return ProviderResponse(content="default response")


@tool
def dummy_tool(x: str) -> str:
    """A dummy tool."""
    return f"result: {x}"


class TestNativeEngine:
    @pytest.mark.asyncio
    async def test_text_response(self):
        provider = MockProvider([
            ProviderResponse(content="Hello!", tool_calls=[])
        ])
        engine = NativeEngine(provider)
        msgs = [Message.system("sys"), Message.user("hi")]

        result = await engine.execute(msgs, [dummy_tool], 0.1)
        assert not result.is_tool_call
        assert result.content == "Hello!"

    @pytest.mark.asyncio
    async def test_tool_call_response(self):
        provider = MockProvider([
            ProviderResponse(content="", tool_calls=[{
                "function": {
                    "name": "dummy_tool",
                    "arguments": {"x": "test"},
                }
            }])
        ])
        engine = NativeEngine(provider)
        msgs = [Message.system("sys"), Message.user("hi")]

        result = await engine.execute(msgs, [dummy_tool], 0.1)
        assert result.is_tool_call
        assert result.tool_name == "dummy_tool"
        assert result.tool_args == {"x": "test"}

    @pytest.mark.asyncio
    async def test_empty_tool_calls_is_text(self):
        provider = MockProvider([
            ProviderResponse(content="No tools needed", tool_calls=[])
        ])
        engine = NativeEngine(provider)
        msgs = [Message.system("sys"), Message.user("hi")]

        result = await engine.execute(msgs, [dummy_tool], 0.1)
        assert not result.is_tool_call


class TestReactEngine:
    @pytest.mark.asyncio
    async def test_final_answer(self):
        provider = MockProvider([
            ProviderResponse(content="Thought: I know the answer.\nFinal Answer: 42")
        ])
        engine = ReactEngine(provider)
        msgs = [Message.system("sys"), Message.user("what is 6*7?")]

        result = await engine.execute(msgs, [dummy_tool], 0.1)
        assert not result.is_tool_call
        assert "42" in result.content

    @pytest.mark.asyncio
    async def test_action_with_inline_json(self):
        provider = MockProvider([
            ProviderResponse(
                content='Thought: I need to use the tool.\nAction: dummy_tool\nAction Input: {"x": "hello"}'
            )
        ])
        engine = ReactEngine(provider)
        msgs = [Message.system("sys"), Message.user("hi")]

        result = await engine.execute(msgs, [dummy_tool], 0.1)
        assert result.is_tool_call
        assert result.tool_name == "dummy_tool"
        assert result.tool_args == {"x": "hello"}

    @pytest.mark.asyncio
    async def test_no_action_returns_text(self):
        provider = MockProvider([
            ProviderResponse(content="I don't know what to do.")
        ])
        engine = ReactEngine(provider)
        msgs = [Message.system("sys"), Message.user("hi")]

        result = await engine.execute(msgs, [dummy_tool], 0.1)
        assert not result.is_tool_call
        assert "I don't know" in result.content


class TestTryParseJson:
    def test_valid_json(self):
        assert ReactEngine._try_parse_json('{"a": 1}') == {"a": 1}

    def test_code_fenced_json(self):
        assert ReactEngine._try_parse_json('```json\n{"a": 1}\n```') == {"a": 1}

    def test_with_thinking_tags(self):
        result = ReactEngine._try_parse_json('<think>hmm</think>{"a": 1}')
        assert result == {"a": 1}

    def test_json_in_text(self):
        result = ReactEngine._try_parse_json('Here is the result: {"a": 1} done')
        assert result == {"a": 1}

    def test_invalid_json(self):
        assert ReactEngine._try_parse_json("not json") is None

    def test_empty_string(self):
        assert ReactEngine._try_parse_json("") is None


class TestEngineResult:
    def test_text_factory(self):
        r = EngineResult.text("hello")
        assert not r.is_tool_call
        assert r.content == "hello"

    def test_tool_call_factory(self):
        r = EngineResult.tool_call("calc", {"n": 1})
        assert r.is_tool_call
        assert r.tool_name == "calc"
        assert r.tool_args == {"n": 1}

    def test_tool_call_none_args(self):
        r = EngineResult.tool_call("calc", None)
        assert r.tool_args == {}
