"""Live streaming integration tests — real Ollama, verify tokens stream as they arrive."""

import pytest
from freeagent import Agent
from freeagent.events import (
    RunStartEvent, TokenEvent, RunCompleteEvent, RunEvent,
)


MODELS = ["qwen3:8b", "qwen3:4b", "llama3.1:latest"]


@pytest.mark.integration
@pytest.mark.parametrize("model", MODELS)
def test_run_stream_yields_tokens(model):
    """run_stream yields RunStart, Token(s), RunComplete with real model."""
    agent = Agent(model=model, conversation=None)

    events = list(agent.run_stream("Say exactly: hello world"))

    # Must start with RunStart and end with RunComplete
    assert isinstance(events[0], RunStartEvent)
    assert isinstance(events[-1], RunCompleteEvent)

    # Must have at least one token
    tokens = [e for e in events if isinstance(e, TokenEvent)]
    assert len(tokens) >= 1

    # Accumulated text should be non-empty
    full_text = "".join(t.text for t in tokens)
    assert len(full_text) > 0

    # RunComplete should have the full response
    complete = events[-1]
    assert len(complete.response) > 0
    assert complete.elapsed_ms > 0


@pytest.mark.integration
@pytest.mark.parametrize("model", MODELS)
@pytest.mark.asyncio
async def test_arun_stream_yields_tokens(model):
    """arun_stream yields tokens asynchronously with real model."""
    agent = Agent(model=model, conversation=None)

    events = []
    async for event in agent.arun_stream("Say exactly: test"):
        events.append(event)

    tokens = [e for e in events if isinstance(e, TokenEvent)]
    assert len(tokens) >= 1

    complete = next(e for e in events if isinstance(e, RunCompleteEvent))
    assert complete.elapsed_ms > 0


@pytest.mark.integration
def test_stream_matches_run():
    """Streaming and non-streaming should produce comparable results."""
    agent = Agent(model="qwen3:8b", conversation=None)

    # Non-streaming
    result = agent.run("What is 2+2? Reply with just the number.")

    # Streaming
    events = list(agent.run_stream("What is 2+2? Reply with just the number."))
    tokens = [e for e in events if isinstance(e, TokenEvent)]
    stream_result = "".join(t.text for t in tokens)

    # Both should contain "4" somewhere
    assert "4" in result or "four" in result.lower()
    assert "4" in stream_result or "four" in stream_result.lower()
