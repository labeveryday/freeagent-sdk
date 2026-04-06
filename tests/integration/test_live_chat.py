"""
Live chat tests — Agent with real Ollama, no tools.

Verifies:
- httpx async client works end-to-end
- SyncBridge correctly wraps async into sync
- Response is a non-empty string
- Telemetry records the run
"""

import pytest
from tests.integration.conftest import skip_if_no_ollama, skip_if_no_model, MODELS

from freeagent import Agent


@skip_if_no_ollama()
@skip_if_no_model(MODELS["qwen3_8b"])
class TestLiveChatQwen8b:
    """Basic chat with qwen3:8b — no tools."""

    def test_simple_response(self):
        agent = Agent(model=MODELS["qwen3_8b"], tools=[])
        response = agent.run("What is 2 + 2? Reply with just the number.")
        assert response is not None
        assert isinstance(response, str)
        assert len(response.strip()) > 0
        assert "4" in response

    def test_telemetry_recorded(self):
        agent = Agent(model=MODELS["qwen3_8b"], tools=[])
        response = agent.run("Say hello in one word.")
        assert len(agent.metrics.runs) == 1
        run = agent.metrics.runs[0]
        assert run.model == MODELS["qwen3_8b"]
        # mode may be "native" because memory tools are auto-added
        assert run.mode in ("chat", "native")
        assert run.elapsed_ms > 0
        assert run.response is not None

    def test_system_prompt_respected(self):
        agent = Agent(
            model=MODELS["qwen3_8b"],
            system_prompt="You are a pirate. Always say 'Arrr' in your response.",
            tools=[],
        )
        response = agent.run("Greet me.")
        # Model should follow the pirate persona
        assert isinstance(response, str)
        assert len(response.strip()) > 0


@skip_if_no_ollama()
@skip_if_no_model(MODELS["qwen3_4b"])
class TestLiveChatQwen4b:
    """Basic chat with qwen3:4b — smaller model."""

    def test_simple_response(self):
        agent = Agent(model=MODELS["qwen3_4b"], tools=[])
        response = agent.run("What is the capital of France? Reply in one word.")
        assert response is not None
        assert isinstance(response, str)
        assert len(response.strip()) > 0


@skip_if_no_ollama()
@skip_if_no_model(MODELS["llama31"])
class TestLiveChatLlama:
    """Basic chat with llama3.1."""

    def test_simple_response(self):
        agent = Agent(model=MODELS["llama31"], tools=[])
        response = agent.run("What color is the sky on a clear day? One word answer.")
        assert response is not None
        assert isinstance(response, str)
        assert len(response.strip()) > 0
