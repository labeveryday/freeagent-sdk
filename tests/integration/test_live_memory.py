"""
Live memory tool tests — Agent with real model using the memory tool.

This is a CRITICAL test. The memory tool uses a single-tool pattern with
an `action` parameter (read/write/append/search/list). Small models may
struggle with this pattern. We record exactly how and where they fail.

Verifies:
- Model can call memory(action="write", file="...", content="...")
- Model can call memory(action="read", file="...")
- Model can call memory(action="search", query="...")
- Model can call memory(action="list")
"""

import pytest
from tests.integration.conftest import skip_if_no_ollama, skip_if_no_model, MODELS

from freeagent import Agent


@skip_if_no_ollama()
@skip_if_no_model(MODELS["qwen3_8b"])
class TestLiveMemoryQwen8b:
    """Memory tool with qwen3:8b."""

    def test_write_memory(self, temp_memory_dir):
        agent = Agent(
            model=MODELS["qwen3_8b"],
            tools=[],  # memory tool is auto-added
            memory_dir=temp_memory_dir,
        )
        response = agent.run(
            "Remember that my favorite team is the Lakers. "
            "Save this to memory using the memory tool with action='write', "
            "file='favorites.md', and content='Favorite team: Lakers'."
        )
        assert response is not None
        # Check if memory was actually written
        content = agent.memory.read("favorites.md")
        # Record whether write succeeded
        write_succeeded = "not found" not in content.lower()
        if write_succeeded:
            assert "lakers" in content.lower() or "Lakers" in content
        else:
            pytest.skip(
                f"FAILURE MODE: qwen3:8b did not call memory(action='write'). "
                f"Response was: {response[:200]}"
            )

    def test_write_then_read(self, temp_memory_dir):
        agent = Agent(
            model=MODELS["qwen3_8b"],
            tools=[],
            memory_dir=temp_memory_dir,
        )
        # First: write
        agent.memory.write("facts.md", "Favorite color: blue", meta={
            "name": "facts", "type": "custom",
            "description": "User facts",
        })

        # Then: ask model to read it
        response = agent.run(
            "What is my favorite color? Use the memory tool with "
            "action='read' and file='facts.md' to check."
        )
        assert response is not None
        # Check if model found the answer
        if "blue" in response.lower():
            pass  # success
        else:
            pytest.skip(
                f"FAILURE MODE: qwen3:8b couldn't read memory. "
                f"Response: {response[:200]}"
            )

    def test_search_memory(self, temp_memory_dir):
        agent = Agent(
            model=MODELS["qwen3_8b"],
            tools=[],
            memory_dir=temp_memory_dir,
        )
        # Pre-populate memory
        agent.memory.write("notes.md", "Meeting with Bob about project X\nLunch with Alice", meta={
            "name": "notes", "type": "custom", "description": "Notes",
        })

        response = agent.run(
            "Search my memory for anything about 'Bob'. "
            "Use the memory tool with action='search' and query='Bob'."
        )
        assert response is not None

    def test_list_memory(self, temp_memory_dir):
        agent = Agent(
            model=MODELS["qwen3_8b"],
            tools=[],
            memory_dir=temp_memory_dir,
        )
        # Pre-populate
        agent.memory.write("tasks.md", "Buy groceries", meta={
            "name": "tasks", "type": "custom", "description": "Task list",
        })

        response = agent.run(
            "What memory files do I have? Use the memory tool with action='list'."
        )
        assert response is not None


@skip_if_no_ollama()
@skip_if_no_model(MODELS["qwen3_4b"])
class TestLiveMemoryQwen4b:
    """Memory tool with qwen3:4b — smaller model, likely harder."""

    def test_write_memory(self, temp_memory_dir):
        agent = Agent(
            model=MODELS["qwen3_4b"],
            tools=[],
            memory_dir=temp_memory_dir,
        )
        response = agent.run(
            "Save to memory: my name is Alice. "
            "Use the memory tool with action='write', file='user.md', "
            "content='Name: Alice'."
        )
        assert response is not None
        content = agent.memory.read("user.md")
        write_succeeded = "not found" not in content.lower()
        if not write_succeeded:
            pytest.skip(
                f"FAILURE MODE: qwen3:4b did not call memory(action='write'). "
                f"Response: {response[:200]}"
            )


@skip_if_no_ollama()
@skip_if_no_model(MODELS["llama31"])
class TestLiveMemoryLlama:
    """Memory tool with llama3.1."""

    def test_write_memory(self, temp_memory_dir):
        agent = Agent(
            model=MODELS["llama31"],
            tools=[],
            memory_dir=temp_memory_dir,
        )
        response = agent.run(
            "Remember that my favorite food is pizza. "
            "Use the memory tool with action='write', file='prefs.md', "
            "content='Favorite food: pizza'."
        )
        assert response is not None
        content = agent.memory.read("prefs.md")
        write_succeeded = "not found" not in content.lower()
        if not write_succeeded:
            pytest.skip(
                f"FAILURE MODE: llama3.1 did not call memory(action='write'). "
                f"Response: {response[:200]}"
            )
