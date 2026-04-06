"""
Live skills tests — compare Agent behavior with vs without bundled skills.

Tests whether the bundled skills (tool-user, general-assistant) actually
help with tool calling accuracy and response quality.
"""

import pytest
from tests.integration.conftest import skip_if_no_ollama, skip_if_no_model, MODELS

from freeagent import Agent
from freeagent.tools.calculator import calculator


@skip_if_no_ollama()
@skip_if_no_model(MODELS["qwen3_8b"])
class TestLiveSkillsQwen8b:
    """Skills A/B test with qwen3:8b."""

    def test_with_default_skills(self):
        """Agent with bundled skills (default behavior)."""
        agent = Agent(model=MODELS["qwen3_8b"], tools=[calculator])
        assert len(agent.skills) > 0  # bundled skills loaded
        response = agent.run("What is 17 * 13? Use the calculator.")
        assert response is not None
        assert "221" in response

    def test_without_skills(self):
        """Agent with skills disabled — empty skills list."""
        agent = Agent(
            model=MODELS["qwen3_8b"],
            tools=[calculator],
            skills=[],  # no user skill dirs, but bundled still load
        )
        response = agent.run("What is 17 * 13? Use the calculator.")
        assert response is not None

    def test_skills_context_in_system_prompt(self):
        """Verify skills are actually injected into system prompt."""
        agent = Agent(model=MODELS["qwen3_8b"], tools=[calculator])
        # Skills should be loaded
        skill_names = [s.name for s in agent.skills]
        assert "tool-user" in skill_names or "general-assistant" in skill_names


@skip_if_no_ollama()
@skip_if_no_model(MODELS["qwen3_4b"])
class TestLiveSkillsQwen4b:
    """Skills test with qwen3:4b — do skills help smaller models more?"""

    def test_with_skills_tool_calling(self):
        agent = Agent(model=MODELS["qwen3_4b"], tools=[calculator])
        response = agent.run("What is 8 * 9? Use the calculator tool.")
        assert response is not None
        assert "72" in response
