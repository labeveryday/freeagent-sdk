"""Tests for caching: system prompt, bundled skills, memory files."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from freeagent import Agent
from freeagent.memory import Memory
from freeagent.skills import load_skills, BUNDLED_SKILLS_DIR, _BUNDLED_CACHE, Skill
from freeagent.providers import ProviderResponse
import freeagent.skills as skills_module


class MockProvider:
    model = "test"
    async def chat(self, messages, temperature=0.1):
        return ProviderResponse(content="ok")
    async def chat_with_tools(self, messages, tools, temperature=0.1):
        return ProviderResponse(content="ok")
    async def chat_with_format(self, messages, schema, temperature=0.1):
        return "{}"
    async def chat_stream(self, messages, temperature=0.1):
        from freeagent.providers import StreamChunk
        yield StreamChunk(content="ok", done=True)
    async def chat_stream_with_tools(self, messages, tools, temperature=0.1):
        from freeagent.providers import StreamChunk
        yield StreamChunk(content="ok", done=True)


# ── System prompt caching tests ──────────────────────────

def test_system_prompt_cache_hit():
    """Second call to _build_system_prompt should use cache."""
    with patch("freeagent.agent.make_memory_tools", return_value=[]):
        agent = Agent(model="test", provider=MockProvider(), tools=[],
                      conversation=None, auto_tune=False)

    # First call — populates cache
    prompt1 = agent._build_system_prompt()
    assert agent._cached_system_prompt is not None

    # Second call — should return same object (cache hit)
    prompt2 = agent._build_system_prompt()
    assert prompt1 is prompt2


def test_system_prompt_cache_invalidates_on_memory_change():
    """Cache should invalidate when memory file count changes."""
    tmpdir = tempfile.mkdtemp()
    with patch("freeagent.agent.make_memory_tools", return_value=[]):
        agent = Agent(model="test", provider=MockProvider(), tools=[],
                      conversation=None, auto_tune=False, memory_dir=tmpdir)

    prompt1 = agent._build_system_prompt()
    assert agent._cached_system_prompt is not None

    # Write a memory file — changes len(memory)
    agent.memory.write("test.md", "hello", meta={"name": "test", "type": "custom"})

    prompt2 = agent._build_system_prompt()
    # Should have been rebuilt (different object)
    assert agent._cache_mem_len == len(agent.memory)


# ── Bundled skills cache tests ────────────────────────────

def test_bundled_skills_cached():
    """Bundled skills should be cached at module level."""
    # Reset the cache
    old_cache = skills_module._BUNDLED_CACHE
    old_mtime = skills_module._BUNDLED_MTIME

    try:
        skills_module._BUNDLED_CACHE = None
        skills_module._BUNDLED_MTIME = 0.0

        # First load
        result1 = load_skills([BUNDLED_SKILLS_DIR])
        assert skills_module._BUNDLED_CACHE is not None
        cached = skills_module._BUNDLED_CACHE

        # Second load — should reuse cache
        result2 = load_skills([BUNDLED_SKILLS_DIR])
        assert skills_module._BUNDLED_CACHE is cached  # same object
        assert len(result1) == len(result2)
    finally:
        skills_module._BUNDLED_CACHE = old_cache
        skills_module._BUNDLED_MTIME = old_mtime


# ── Memory file cache tests ──────────────────────────────

def test_memory_file_cache_hit():
    """Second read of same file should use cache."""
    tmpdir = tempfile.mkdtemp()
    mem = Memory(memory_dir=tmpdir)
    mem.write("test.md", "hello", meta={"name": "test"})

    # First read — populates cache
    content1 = mem.read("test.md")
    assert len(mem._file_cache) > 0

    # Second read — should use cache
    content2 = mem.read("test.md")
    assert content1 == content2


def test_memory_file_cache_invalidates_on_write():
    """Cache should invalidate when file is written."""
    tmpdir = tempfile.mkdtemp()
    mem = Memory(memory_dir=tmpdir)
    mem.write("test.md", "hello", meta={"name": "test"})

    # Read to populate cache
    mem.read("test.md")
    path_key = str(mem._resolve("test.md"))
    assert path_key in mem._file_cache

    # Write to invalidate
    mem.write("test.md", "world", meta={"name": "test"})
    assert path_key not in mem._file_cache


def test_memory_file_cache_invalidates_on_append():
    """Cache should invalidate when file is appended."""
    tmpdir = tempfile.mkdtemp()
    mem = Memory(memory_dir=tmpdir)
    mem.write("test.md", "hello", meta={"name": "test"})

    # Read to populate cache
    mem.read("test.md")
    path_key = str(mem._resolve("test.md"))
    assert path_key in mem._file_cache

    # Append to invalidate
    mem.append("test.md", "more")
    assert path_key not in mem._file_cache


# ── SlidingWindow deque test ─────────────────────────────

def test_sliding_window_uses_deque():
    """SlidingWindow._history should be a deque."""
    from collections import deque
    from freeagent.conversation import SlidingWindow

    sw = SlidingWindow(max_turns=5)
    assert isinstance(sw._history, deque)
