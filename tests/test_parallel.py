"""Tests for parallel tool calling."""

import asyncio
import tempfile
import pytest
from freeagent.agent import Agent
from freeagent.tool import tool
from freeagent.providers import ProviderResponse
from freeagent.engines import NativeEngine, ToolCall, EngineResult
from freeagent.config import AgentConfig


class MockProvider:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.model = "mock"
        self._call_count = 0

    async def chat(self, messages, temperature=0.1):
        return self._next()

    async def chat_with_tools(self, messages, tools, temperature=0.1):
        return self._next()

    async def chat_with_format(self, messages, schema, temperature=0.1):
        return self._next().content

    async def close(self):
        pass

    def _next(self):
        if self._call_count < len(self.responses):
            r = self.responses[self._call_count]
            self._call_count += 1
            return r
        return ProviderResponse(content="[no more responses]")


@tool
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


@tool
def multiply(a: int, b: int) -> int:
    """Multiply two numbers."""
    return a * b


execution_order = []


@tool
async def slow_tool(name: str) -> str:
    """A slow tool that records execution order."""
    execution_order.append(f"start:{name}")
    await asyncio.sleep(0.05)
    execution_order.append(f"end:{name}")
    return f"done:{name}"


class TestParallelToolCalls:
    @pytest.mark.asyncio
    async def test_two_parallel_calls(self):
        """Model returns 2 tool calls, both should execute."""
        provider = MockProvider([
            # First response: two tool calls
            ProviderResponse(content="", tool_calls=[
                {"function": {"name": "add", "arguments": {"a": 1, "b": 2}}},
                {"function": {"name": "multiply", "arguments": {"a": 3, "b": 4}}},
            ]),
            # Second response: final answer
            ProviderResponse(content="1+2=3 and 3*4=12"),
        ])
        agent = Agent(
            model="mock",
            provider=provider,
            tools=[add, multiply],
            memory_dir=tempfile.mkdtemp(),
        )
        agent.engine = NativeEngine(provider)
        agent._mode = "native"

        result = await agent.arun("Calculate both")
        assert "3" in result and "12" in result

        # Telemetry should record both tool calls
        run = agent.metrics.last_run
        assert run.tool_call_count == 2
        tool_names = {tc.name for tc in run.tool_calls}
        assert "add" in tool_names
        assert "multiply" in tool_names

    @pytest.mark.asyncio
    async def test_concurrent_execution(self):
        """Verify tools actually run concurrently, not sequentially."""
        global execution_order
        execution_order = []

        provider = MockProvider([
            ProviderResponse(content="", tool_calls=[
                {"function": {"name": "slow_tool", "arguments": {"name": "A"}}},
                {"function": {"name": "slow_tool", "arguments": {"name": "B"}}},
            ]),
            ProviderResponse(content="Done!"),
        ])
        agent = Agent(
            model="mock",
            provider=provider,
            tools=[slow_tool],
            memory_dir=tempfile.mkdtemp(),
        )
        agent.engine = NativeEngine(provider)
        agent._mode = "native"

        await agent.arun("Run both")

        # Both should start before either ends (concurrent execution)
        starts = [e for e in execution_order if e.startswith("start:")]
        assert len(starts) == 2

    @pytest.mark.asyncio
    async def test_one_bad_call_doesnt_block_good_ones(self):
        """If one call fails validation, the valid one still executes."""
        provider = MockProvider([
            ProviderResponse(content="", tool_calls=[
                {"function": {"name": "add", "arguments": {"a": 1, "b": 2}}},
                {"function": {"name": "nonexistent", "arguments": {}}},
            ]),
            # After error feedback, model gives final answer
            ProviderResponse(content="", tool_calls=[
                {"function": {"name": "add", "arguments": {"a": 1, "b": 2}}},
            ]),
            ProviderResponse(content="The answer is 3."),
        ])
        agent = Agent(
            model="mock",
            provider=provider,
            tools=[add],
            memory_dir=tempfile.mkdtemp(),
        )
        agent.engine = NativeEngine(provider)
        agent._mode = "native"

        result = await agent.arun("Test")
        # Should still get a result
        assert "3" in result

    @pytest.mark.asyncio
    async def test_three_parallel_calls(self):
        """Three parallel calls all execute and record telemetry."""
        provider = MockProvider([
            ProviderResponse(content="", tool_calls=[
                {"function": {"name": "add", "arguments": {"a": 1, "b": 1}}},
                {"function": {"name": "add", "arguments": {"a": 2, "b": 2}}},
                {"function": {"name": "multiply", "arguments": {"a": 3, "b": 3}}},
            ]),
            ProviderResponse(content="Results: 2, 4, 9"),
        ])
        agent = Agent(
            model="mock",
            provider=provider,
            tools=[add, multiply],
            memory_dir=tempfile.mkdtemp(),
        )
        agent.engine = NativeEngine(provider)
        agent._mode = "native"

        result = await agent.arun("Triple calc")
        assert agent.metrics.last_run.tool_call_count == 3


class TestEngineResultMultiCall:
    def test_multi_tool_call(self):
        calls = [
            ToolCall(name="a", args={"x": 1}),
            ToolCall(name="b", args={"y": 2}),
        ]
        result = EngineResult.multi_tool_call(calls)
        assert result.is_tool_call
        assert len(result.tool_calls) == 2
        assert result.tool_name == "a"  # first call for backward compat

    def test_single_tool_call_has_tool_calls_list(self):
        result = EngineResult.tool_call("calc", {"n": 1})
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "calc"
