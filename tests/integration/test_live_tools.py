"""
Live tool calling tests — Agent with real Ollama + built-in tools.

Verifies:
- Tool calling works end-to-end with real model output
- Validator handles real model output (fuzzy matching, type coercion)
- Telemetry records tool calls
- Calculator and system_info tools work through the full pipeline
"""

import pytest
from tests.integration.conftest import skip_if_no_ollama, skip_if_no_model, MODELS

from freeagent import Agent
from freeagent.tools.calculator import calculator
from freeagent.tools.system_info import system_info


@skip_if_no_ollama()
@skip_if_no_model(MODELS["qwen3_8b"])
class TestLiveToolsQwen8b:
    """Tool calling with qwen3:8b."""

    def test_calculator_basic(self):
        agent = Agent(model=MODELS["qwen3_8b"], tools=[calculator])
        response = agent.run("What is 15 * 23? Use the calculator tool.")
        assert response is not None
        assert isinstance(response, str)
        assert "345" in response

    def test_calculator_telemetry(self):
        agent = Agent(model=MODELS["qwen3_8b"], tools=[calculator])
        response = agent.run("Calculate 100 / 4 using the calculator.")
        # Check telemetry recorded the tool call
        run = agent.metrics.runs[-1]
        assert run.mode == "native"
        # Should have at least one tool call in metrics
        assert len(run.tool_calls) > 0
        # At least one should be calculator
        calc_calls = [tc for tc in run.tool_calls if tc.name == "calculator"]
        assert len(calc_calls) > 0

    def test_system_info(self):
        agent = Agent(model=MODELS["qwen3_8b"], tools=[system_info])
        response = agent.run("What operating system am I running? Use the system_info tool.")
        assert response is not None
        assert isinstance(response, str)
        assert len(response.strip()) > 0

    def test_multi_tool_selection(self):
        """Model should pick the right tool when multiple are available."""
        agent = Agent(model=MODELS["qwen3_8b"], tools=[calculator, system_info])
        response = agent.run("What is 7 + 8? Use the appropriate tool.")
        assert "15" in response

    def test_no_tool_needed(self):
        """Model should answer directly when no tool is needed."""
        agent = Agent(model=MODELS["qwen3_8b"], tools=[calculator])
        response = agent.run("What color is the sky?")
        assert response is not None
        assert isinstance(response, str)
        assert len(response.strip()) > 0


@skip_if_no_ollama()
@skip_if_no_model(MODELS["qwen3_4b"])
class TestLiveToolsQwen4b:
    """Tool calling with qwen3:4b — test smaller model reliability."""

    def test_calculator_basic(self):
        agent = Agent(model=MODELS["qwen3_4b"], tools=[calculator])
        response = agent.run("What is 12 * 5? Use the calculator tool.")
        assert response is not None
        assert "60" in response

    def test_wrong_tool_recovery(self):
        """Track if smaller model can recover from validation errors."""
        agent = Agent(model=MODELS["qwen3_4b"], tools=[calculator, system_info])
        response = agent.run("Calculate 99 + 1 using the calculator.")
        # We mainly want to see if it completes without crashing
        assert response is not None
        assert isinstance(response, str)


@skip_if_no_ollama()
@skip_if_no_model(MODELS["llama31"])
class TestLiveToolsLlama:
    """Tool calling with llama3.1."""

    def test_calculator_basic(self):
        agent = Agent(model=MODELS["llama31"], tools=[calculator])
        response = agent.run("What is 25 * 4? Use the calculator tool.")
        assert response is not None
        assert "100" in response

    def test_system_info_disk(self):
        agent = Agent(model=MODELS["llama31"], tools=[system_info])
        response = agent.run("How much free disk space do I have? Use the system_info tool.")
        assert response is not None
        assert isinstance(response, str)
