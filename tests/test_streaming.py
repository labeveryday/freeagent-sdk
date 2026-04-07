"""Tests for streaming support — events, provider streaming, agent.run_stream."""

import asyncio
import pytest
from unittest.mock import patch

from freeagent import Agent
from freeagent.events import (
    RunStartEvent, TokenEvent, ToolCallEvent, ToolResultEvent,
    ValidationErrorEvent, RetryEvent, IterationEvent, RunCompleteEvent, RunEvent,
)
from freeagent.providers import ProviderResponse, StreamChunk
from freeagent.tool import tool, ToolResult


# ── Event dataclass tests ─────────────────────────────────

def test_run_start_event():
    e = RunStartEvent(model="qwen3:8b", mode="native")
    assert e.model == "qwen3:8b"
    assert e.mode == "native"


def test_token_event():
    e = TokenEvent(text="hello", iteration=0)
    assert e.text == "hello"
    assert e.iteration == 0


def test_tool_call_event():
    e = ToolCallEvent(name="calc", args={"x": 1})
    assert e.name == "calc"
    assert e.args == {"x": 1}


def test_tool_result_event():
    e = ToolResultEvent(name="calc", result="42", success=True, duration_ms=5.0)
    assert e.success is True
    assert e.duration_ms == 5.0


def test_validation_error_event():
    e = ValidationErrorEvent(tool_name="calc", errors=["missing x"])
    assert e.errors == ["missing x"]


def test_retry_event():
    e = RetryEvent(tool_name="calc", retry_count=1)
    assert e.retry_count == 1


def test_iteration_event():
    e = IterationEvent(iteration=2)
    assert e.iteration == 2


def test_run_complete_event():
    e = RunCompleteEvent(response="done", elapsed_ms=100.0, metrics={"tool_calls": 1})
    assert e.response == "done"
    assert e.metrics["tool_calls"] == 1


# ── Stream chunk tests ────────────────────────────────────

def test_stream_chunk_defaults():
    c = StreamChunk()
    assert c.content == ""
    assert c.tool_calls == []
    assert c.done is False


def test_stream_chunk_with_content():
    c = StreamChunk(content="hello", done=False)
    assert c.content == "hello"


# ── Mock provider that yields chunks ─────────────────────

class MockStreamProvider:
    """Mock provider that simulates streaming."""

    def __init__(self, chunks: list[str], model: str = "test-model"):
        self.model = model
        self._chunks = chunks

    async def chat(self, messages, temperature=0.1):
        return ProviderResponse(content="".join(self._chunks))

    async def chat_with_tools(self, messages, tools, temperature=0.1):
        return ProviderResponse(content="".join(self._chunks))

    async def chat_with_format(self, messages, schema, temperature=0.1):
        return "{}"

    async def chat_stream(self, messages, temperature=0.1):
        for i, chunk in enumerate(self._chunks):
            yield StreamChunk(content=chunk, done=(i == len(self._chunks) - 1))

    async def chat_stream_with_tools(self, messages, tools, temperature=0.1):
        for i, chunk in enumerate(self._chunks):
            yield StreamChunk(content=chunk, done=(i == len(self._chunks) - 1))


# ── Agent streaming tests ────────────────────────────────

@pytest.mark.asyncio
async def test_arun_stream_chat_mode():
    """arun_stream yields RunStart, Token(s), RunComplete for simple chat."""
    provider = MockStreamProvider(["Hello", " world", "!"])
    with patch("freeagent.agent.make_memory_tools", return_value=[]):
        agent = Agent(
            model="test-model",
            tools=[],
            provider=provider,
            conversation=None,
        )

    events = []
    async for event in agent.arun_stream("hi"):
        events.append(event)

    # Check event types in order
    types = [type(e).__name__ for e in events]
    assert types[0] == "RunStartEvent"
    assert types[-1] == "RunCompleteEvent"

    # Should have token events
    tokens = [e for e in events if isinstance(e, TokenEvent)]
    assert len(tokens) == 3
    assert tokens[0].text == "Hello"
    assert tokens[1].text == " world"
    assert tokens[2].text == "!"

    # RunComplete should have the full response
    complete = events[-1]
    assert complete.response == "Hello world!"


@pytest.mark.asyncio
async def test_arun_stream_with_tools():
    """arun_stream yields tool events when tools are involved."""

    @tool
    def add(a: int, b: int) -> str:
        """Add two numbers."""
        return str(a + b)

    # Mock provider: first call returns tool call, second returns text
    call_count = 0

    class ToolMockProvider:
        model = "qwen3:8b"

        async def chat(self, messages, temperature=0.1):
            return ProviderResponse(content="The answer is 3")

        async def chat_with_tools(self, messages, tools, temperature=0.1):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ProviderResponse(
                    content="",
                    tool_calls=[{
                        "function": {"name": "add", "arguments": {"a": 1, "b": 2}}
                    }],
                )
            return ProviderResponse(content="The answer is 3")

        async def chat_with_format(self, messages, schema, temperature=0.1):
            return "{}"

        async def chat_stream(self, messages, temperature=0.1):
            yield StreamChunk(content="The answer is 3", done=True)

        async def chat_stream_with_tools(self, messages, tools, temperature=0.1):
            yield StreamChunk(content="The answer is 3", done=True)

    agent = Agent(
        model="qwen3:8b",
        tools=[add],
        provider=ToolMockProvider(),
        conversation=None,
    )

    events = []
    async for event in agent.arun_stream("1+2"):
        events.append(event)

    types = [type(e).__name__ for e in events]
    assert "RunStartEvent" in types
    assert "IterationEvent" in types
    assert "ToolCallEvent" in types
    assert "ToolResultEvent" in types
    assert "RunCompleteEvent" in types

    # Check tool events
    tool_call = next(e for e in events if isinstance(e, ToolCallEvent))
    assert tool_call.name == "add"
    assert tool_call.args == {"a": 1, "b": 2}

    tool_result = next(e for e in events if isinstance(e, ToolResultEvent))
    assert tool_result.name == "add"
    assert tool_result.success is True


@pytest.mark.asyncio
async def test_arun_returns_same_as_stream():
    """arun() should return the same result as consuming arun_stream()."""
    provider = MockStreamProvider(["Hello", " world"])
    with patch("freeagent.agent.make_memory_tools", return_value=[]):
        agent = Agent(
            model="test-model",
            tools=[],
            provider=provider,
            conversation=None,
        )

    result = await agent.arun("hi")
    assert result == "Hello world"


def test_run_still_works():
    """Existing synchronous run() must still work."""
    provider = MockStreamProvider(["Hello"])
    with patch("freeagent.agent.make_memory_tools", return_value=[]):
        agent = Agent(
            model="test-model",
            tools=[],
            provider=provider,
            conversation=None,
        )
    result = agent.run("hi")
    assert result == "Hello"


def test_run_stream_sync():
    """run_stream() yields events synchronously."""
    provider = MockStreamProvider(["Hello", " world"])
    with patch("freeagent.agent.make_memory_tools", return_value=[]):
        agent = Agent(
            model="test-model",
            tools=[],
            provider=provider,
            conversation=None,
        )

    events = list(agent.run_stream("hi"))
    types = [type(e).__name__ for e in events]
    assert "RunStartEvent" in types
    assert "TokenEvent" in types
    assert "RunCompleteEvent" in types

    tokens = [e for e in events if isinstance(e, TokenEvent)]
    full_text = "".join(t.text for t in tokens)
    assert full_text == "Hello world"


@pytest.mark.asyncio
async def test_stream_event_order():
    """Events should arrive in the correct order: RunStart -> ... -> RunComplete."""
    provider = MockStreamProvider(["test"])
    with patch("freeagent.agent.make_memory_tools", return_value=[]):
        agent = Agent(
            model="test-model",
            tools=[],
            provider=provider,
            conversation=None,
        )

    events = []
    async for event in agent.arun_stream("hi"):
        events.append(event)

    assert isinstance(events[0], RunStartEvent)
    assert isinstance(events[-1], RunCompleteEvent)
    assert events[0].model == "test-model"
    assert events[0].mode == "chat"


@pytest.mark.asyncio
async def test_stream_fallback_no_chat_stream():
    """Provider without chat_stream falls back to chat()."""

    class MinimalProvider:
        model = "minimal"

        async def chat(self, messages, temperature=0.1):
            return ProviderResponse(content="fallback response")

        async def chat_with_tools(self, messages, tools, temperature=0.1):
            return ProviderResponse(content="fallback")

        async def chat_with_format(self, messages, schema, temperature=0.1):
            return "{}"

    with patch("freeagent.agent.make_memory_tools", return_value=[]):
        agent = Agent(
            model="minimal",
            tools=[],
            provider=MinimalProvider(),
            conversation=None,
        )

    events = []
    async for event in agent.arun_stream("hi"):
        events.append(event)

    tokens = [e for e in events if isinstance(e, TokenEvent)]
    assert len(tokens) == 1
    assert tokens[0].text == "fallback response"


# ── Import tests ──────────────────────────────────────────

def test_events_importable():
    """All event types should be importable from freeagent."""
    from freeagent import (
        RunStartEvent, TokenEvent, ToolCallEvent, ToolResultEvent,
        ValidationErrorEvent, RetryEvent, IterationEvent, RunCompleteEvent,
    )
    assert RunStartEvent is not None


def test_events_importable_from_events_module():
    """All event types importable from freeagent.events."""
    from freeagent.events import RunEvent
    assert RunEvent is not None
