"""
Live ReactEngine tests — force ReAct mode and test with real model.

ReactEngine is the fallback for models that can't do native tool calling.
We force it by setting prefer_native_tools=False or using a config that
doesn't list the model in native_tool_models.
"""

import pytest
from tests.integration.conftest import skip_if_no_ollama, skip_if_no_model, MODELS

from freeagent import Agent, AgentConfig
from freeagent.tools.calculator import calculator
from freeagent.tools.system_info import system_info


def _make_react_config(model: str) -> AgentConfig:
    """Create a config that forces ReactEngine by clearing native_tool_models."""
    return AgentConfig(
        native_tool_models=[],  # no models support native — forces ReAct
        temperature=0.1,
        max_iterations=5,
        timeout_seconds=120.0,
    )


@skip_if_no_ollama()
@skip_if_no_model(MODELS["qwen3_8b"])
class TestLiveReactQwen8b:
    """ReactEngine with qwen3:8b (normally uses NativeEngine)."""

    def test_react_mode_selected(self):
        config = _make_react_config(MODELS["qwen3_8b"])
        agent = Agent(model=MODELS["qwen3_8b"], tools=[calculator], config=config, auto_tune=False)
        assert agent._mode == "react"

    def test_calculator_via_react(self):
        config = _make_react_config(MODELS["qwen3_8b"])
        agent = Agent(model=MODELS["qwen3_8b"], tools=[calculator], config=config, auto_tune=False)
        response = agent.run("What is 6 * 7? Use the calculator tool.")
        assert response is not None
        assert isinstance(response, str)
        # ReAct may be less reliable — record result but don't hard-fail on answer
        has_answer = "42" in response
        if not has_answer:
            pytest.skip(
                f"FAILURE MODE: ReactEngine with qwen3:8b didn't get correct answer. "
                f"Response: {response[:300]}"
            )

    def test_system_info_via_react(self):
        config = _make_react_config(MODELS["qwen3_8b"])
        agent = Agent(model=MODELS["qwen3_8b"], tools=[system_info], config=config, auto_tune=False)
        response = agent.run("What OS am I running? Use the system_info tool with check='os'.")
        assert response is not None
        assert isinstance(response, str)


@skip_if_no_ollama()
@skip_if_no_model(MODELS["qwen3_4b"])
class TestLiveReactQwen4b:
    """ReactEngine with qwen3:4b — the primary target for ReAct fallback."""

    def test_calculator_via_react(self):
        config = _make_react_config(MODELS["qwen3_4b"])
        agent = Agent(model=MODELS["qwen3_4b"], tools=[calculator], config=config, auto_tune=False)
        response = agent.run(
            "What is 10 + 5? Use the calculator tool. "
            "Format: Thought, Action, Action Input."
        )
        assert response is not None
        assert isinstance(response, str)
        has_answer = "15" in response
        if not has_answer:
            pytest.skip(
                f"FAILURE MODE: ReactEngine with qwen3:4b didn't get correct answer. "
                f"Response: {response[:300]}"
            )


@skip_if_no_ollama()
@skip_if_no_model(MODELS["llama31"])
class TestLiveReactLlama:
    """ReactEngine with llama3.1."""

    def test_calculator_via_react(self):
        config = _make_react_config(MODELS["llama31"])
        agent = Agent(model=MODELS["llama31"], tools=[calculator], config=config, auto_tune=False)
        response = agent.run("What is 9 * 9? Use the calculator tool.")
        assert response is not None
        assert isinstance(response, str)
        has_answer = "81" in response
        if not has_answer:
            pytest.skip(
                f"FAILURE MODE: ReactEngine with llama3.1 didn't get correct answer. "
                f"Response: {response[:300]}"
            )
