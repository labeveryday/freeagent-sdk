"""Tests for Agent — full loop with mock provider."""

import pytest
import tempfile
from freeagent.agent import Agent
from freeagent.tool import tool, Tool, ToolResult
from freeagent.providers import ProviderResponse
from freeagent.config import AgentConfig


class MockProvider:
    """Mock provider that returns pre-configured responses."""

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
def greet(name: str) -> str:
    """Greet someone."""
    return f"Hello, {name}!"


class TestChatMode:
    @pytest.mark.asyncio
    async def test_simple_chat(self):
        provider = MockProvider([
            ProviderResponse(content="Hi there!")
        ])
        agent = Agent(
            model="mock",
            provider=provider,
            tools=[],
            memory_dir=tempfile.mkdtemp(),
        )
        result = await agent.arun("Hello")
        assert "Hi there!" in result

    @pytest.mark.asyncio
    async def test_chat_mode_has_memory_tools(self):
        """Even with tools=[], agent still has memory tools so it's not 'chat' mode."""
        provider = MockProvider([
            ProviderResponse(content="I'm a bot.")
        ])
        agent = Agent(
            model="mock",
            provider=provider,
            tools=[],
            memory_dir=tempfile.mkdtemp(),
        )
        # Memory tools are always added, so mode won't be "chat"
        assert len(agent.tools) >= 1  # at least the memory tool
        assert any(t.name == "memory" for t in agent.tools)


class TestSingleToolCall:
    @pytest.mark.asyncio
    async def test_tool_call_and_response(self):
        provider = MockProvider([
            # First call: model wants to call add
            ProviderResponse(content="", tool_calls=[{
                "function": {"name": "add", "arguments": {"a": 2, "b": 3}}
            }]),
            # Second call: model gives final answer
            ProviderResponse(content="The sum is 5."),
        ])
        agent = Agent(
            model="mock",
            provider=provider,
            tools=[add],
            memory_dir=tempfile.mkdtemp(),
        )
        # Force native mode since mock model won't match native_tool_models
        from freeagent.engines import NativeEngine
        agent.engine = NativeEngine(provider)
        agent._mode = "native"

        result = await agent.arun("What is 2+3?")
        assert "5" in result


class TestValidationRetry:
    @pytest.mark.asyncio
    async def test_validation_error_then_success(self):
        provider = MockProvider([
            # First: model calls wrong tool name
            ProviderResponse(content="", tool_calls=[{
                "function": {"name": "addd", "arguments": {"a": 1, "b": 2}}
            }]),
            # Second: model fixes the name
            ProviderResponse(content="", tool_calls=[{
                "function": {"name": "add", "arguments": {"a": 1, "b": 2}}
            }]),
            # Third: final answer
            ProviderResponse(content="The answer is 3."),
        ])
        agent = Agent(
            model="mock",
            provider=provider,
            tools=[add],
            memory_dir=tempfile.mkdtemp(),
        )
        from freeagent.engines import NativeEngine
        agent.engine = NativeEngine(provider)
        agent._mode = "native"

        result = await agent.arun("What is 1+2?")
        assert "3" in result
        # Should have recorded validation error
        assert agent.metrics.last_run.validation_errors >= 1


class TestCircuitBreaker:
    @pytest.mark.asyncio
    async def test_loop_detection(self):
        # Model keeps calling the same tool with same args
        responses = [
            ProviderResponse(content="", tool_calls=[{
                "function": {"name": "add", "arguments": {"a": 1, "b": 1}}
            }])
        ] * 10 + [
            ProviderResponse(content="I'm stuck."),
        ]
        config = AgentConfig()
        config.loop_threshold = 3
        config.max_iterations = 20

        agent = Agent(
            model="mock",
            provider=MockProvider(responses),
            tools=[add],
            config=config,
            memory_dir=tempfile.mkdtemp(),
        )
        from freeagent.engines import NativeEngine
        agent.engine = NativeEngine(agent.provider)
        agent._mode = "native"

        result = await agent.arun("Loop test")
        assert agent.metrics.last_run.loop_detected


class TestTelemetryIntegration:
    @pytest.mark.asyncio
    async def test_metrics_recorded(self):
        provider = MockProvider([
            ProviderResponse(content="", tool_calls=[{
                "function": {"name": "greet", "arguments": {"name": "World"}}
            }]),
            ProviderResponse(content="Done!"),
        ])
        agent = Agent(
            model="mock",
            provider=provider,
            tools=[greet],
            memory_dir=tempfile.mkdtemp(),
        )
        from freeagent.engines import NativeEngine
        agent.engine = NativeEngine(provider)
        agent._mode = "native"

        await agent.arun("Say hello")

        run = agent.metrics.last_run
        assert run is not None
        assert run.model_calls >= 1
        assert run.tool_call_count == 1
        assert run.tool_calls[0].name == "greet"
        assert run.tool_calls[0].success is True
        assert run.elapsed_ms > 0


class TestHooks:
    @pytest.mark.asyncio
    async def test_before_run_hook(self):
        provider = MockProvider([
            ProviderResponse(content="Normal response")
        ])
        agent = Agent(
            model="mock",
            provider=provider,
            tools=[],
            memory_dir=tempfile.mkdtemp(),
        )
        called = []

        @agent.on("before_run")
        def hook(ctx):
            called.append(ctx.user_input)

        await agent.arun("test input")
        assert "test input" in called

    @pytest.mark.asyncio
    async def test_override_response(self):
        provider = MockProvider([
            ProviderResponse(content="Normal response")
        ])
        agent = Agent(
            model="mock",
            provider=provider,
            tools=[],
            memory_dir=tempfile.mkdtemp(),
        )

        @agent.on("before_run")
        def hook(ctx):
            ctx.override_response = "Overridden!"

        result = await agent.arun("test")
        assert result == "Overridden!"


class TestTimeout:
    @pytest.mark.asyncio
    async def test_timeout_returns_graceful_message(self):
        import asyncio

        class SlowProvider(MockProvider):
            async def chat_with_tools(self, messages, tools, temperature=0.1):
                await asyncio.sleep(10)
                return ProviderResponse(content="too late")

        config = AgentConfig()
        config.timeout_seconds = 0.1

        agent = Agent(
            model="mock",
            provider=SlowProvider(),
            tools=[add],
            config=config,
            memory_dir=tempfile.mkdtemp(),
        )
        from freeagent.engines import NativeEngine
        agent.engine = NativeEngine(agent.provider)
        agent._mode = "native"

        result = await agent.arun("slow query")
        assert "timed out" in result.lower() or "timeout" in result.lower()
        assert agent.metrics.last_run.timed_out


class TestRepr:
    def test_repr(self):
        agent = Agent(
            model="mock",
            provider=MockProvider(),
            tools=[add],
            memory_dir=tempfile.mkdtemp(),
        )
        r = repr(agent)
        assert "Agent(" in r
        assert "mock" in r
