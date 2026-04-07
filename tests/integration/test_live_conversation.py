"""
Live integration test for conversation management.
Requires Ollama running with qwen3:8b.

Run: pytest tests/integration/test_live_conversation.py -v -s
"""

import pytest
import shutil
from freeagent import Agent, tool, SlidingWindow, TokenWindow
from freeagent.conversation import Session


@tool
def weather(city: str) -> dict:
    """Get current weather for a city."""
    data = {
        "new york": {"temp_f": 72, "condition": "partly cloudy"},
        "tokyo": {"temp_f": 85, "condition": "sunny"},
        "london": {"temp_f": 61, "condition": "rainy"},
    }
    key = city.lower().strip()
    for k, v in data.items():
        if k in key:
            return {**v, "city": city}
    return {"city": city, "temp_f": 70, "condition": "unknown"}


@tool
def unit_converter(value: float, from_unit: str, to_unit: str) -> dict:
    """Convert between units."""
    conversions = {
        ("fahrenheit", "celsius"): lambda v: round((v - 32) * 5/9, 1),
    }
    key = (from_unit.lower(), to_unit.lower())
    if key in conversions:
        return {"result": conversions[key](value), "from": from_unit, "to": to_unit}
    return {"error": f"Unknown conversion: {from_unit} to {to_unit}"}


@pytest.fixture
def cleanup_sessions():
    yield
    shutil.rmtree(".freeagent", ignore_errors=True)


@pytest.mark.integration
class TestLiveMultiTurn:
    """Test multi-turn conversation with real Ollama."""

    def test_two_turn_weather_then_convert(self):
        """The core multi-turn test: get weather, then reference the result."""
        agent = Agent(
            model="qwen3:8b",
            tools=[weather, unit_converter],
            conversation=SlidingWindow(max_turns=10),
        )

        # Turn 1: get weather
        r1 = agent.run("What's the weather in Tokyo?")
        print(f"\nTurn 1: {r1}")
        assert "85" in r1 or "sunny" in r1.lower()

        # Turn 2: reference turn 1
        r2 = agent.run("Convert that temperature to Celsius")
        print(f"Turn 2: {r2}")
        assert "29" in r2  # 85F ≈ 29.4C

        # Verify conversation state
        assert agent.conversation.turn_count == 2
        print(f"Turns: {agent.conversation.turn_count}")
        print(f"Metrics: {agent.metrics}")

    def test_three_turn_compare(self):
        """Multi-turn: check two cities, then compare."""
        agent = Agent(
            model="qwen3:8b",
            tools=[weather],
            conversation=SlidingWindow(max_turns=10),
        )

        r1 = agent.run("What's the weather in New York?")
        print(f"\nTurn 1: {r1}")

        r2 = agent.run("Now check Tokyo.")
        print(f"Turn 2: {r2}")

        r3 = agent.run("Which city is warmer?")
        print(f"Turn 3: {r3}")
        assert "tokyo" in r3.lower()

        assert agent.conversation.turn_count == 3

    def test_conversation_none_is_stateless(self):
        """conversation=None means no memory between turns."""
        agent = Agent(
            model="qwen3:8b",
            tools=[weather],
            conversation=None,
        )

        r1 = agent.run("What's the weather in Tokyo?")
        print(f"\nTurn 1: {r1}")

        # Turn 2 without context — model doesn't know what "that" refers to
        r2 = agent.run("Convert that temperature to Celsius")
        print(f"Turn 2 (stateless): {r2}")
        # Should NOT have 29 since it doesn't know what temp we mean
        # (it might guess or use a default, but that's fine — the point is no context)

    def test_clear_resets(self):
        """agent.conversation.clear() starts fresh."""
        agent = Agent(
            model="qwen3:8b",
            tools=[weather],
            conversation=SlidingWindow(max_turns=10),
        )

        agent.run("What's the weather in Tokyo?")
        assert agent.conversation.turn_count == 1

        agent.conversation.clear()
        assert agent.conversation.turn_count == 0

        r = agent.run("What did I just ask you?")
        print(f"\nAfter clear: {r}")
        # Model shouldn't know about Tokyo


@pytest.mark.integration
class TestLiveSession:
    """Test session persistence with real Ollama."""

    def test_session_persist_and_restore(self, cleanup_sessions):
        """Save a session, create a new agent, restore it."""
        # Agent 1: first turn
        agent1 = Agent(
            model="qwen3:8b",
            tools=[weather],
            conversation=SlidingWindow(max_turns=10),
            session="test-session",
        )
        r1 = agent1.run("What's the weather in Tokyo?")
        print(f"\nAgent1 Turn 1: {r1}")
        assert agent1._session.exists

        # Agent 2: restore session, second turn
        agent2 = Agent(
            model="qwen3:8b",
            tools=[weather, unit_converter],
            conversation=SlidingWindow(max_turns=10),
            session="test-session",
        )
        assert agent2.conversation.turn_count == 1  # restored!

        r2 = agent2.run("Convert that temperature to Celsius")
        print(f"Agent2 Turn 2: {r2}")
        assert "29" in r2

        # Cleanup
        agent2._session.delete()
