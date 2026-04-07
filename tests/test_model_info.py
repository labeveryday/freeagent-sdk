"""Tests for model info detection and auto-tuning."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from freeagent import Agent
from freeagent.model_info import ModelInfo, fetch_model_info
from freeagent.providers import ProviderResponse


# ── ModelInfo dataclass tests ─────────────────────────────

def test_model_info_is_small():
    info = ModelInfo(name="tiny", parameter_count=2_000_000_000)
    assert info.is_small is True
    assert info.is_medium is False


def test_model_info_is_medium():
    info = ModelInfo(name="medium", parameter_count=8_000_000_000)
    assert info.is_small is False
    assert info.is_medium is True


def test_model_info_is_large():
    info = ModelInfo(name="large", parameter_count=70_000_000_000)
    assert info.is_small is False
    assert info.is_medium is False


def test_model_info_zero_params():
    info = ModelInfo(name="unknown", parameter_count=0)
    assert info.is_small is False
    assert info.is_medium is False


def test_model_info_supports_native_tools():
    info = ModelInfo(name="test", capabilities=["completion", "tools"])
    assert info.supports_native_tools is True


def test_model_info_no_tools():
    info = ModelInfo(name="test", capabilities=["completion"])
    assert info.supports_native_tools is False


# ── fetch_model_info tests ────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_model_info_success():
    """Mock httpx to simulate /api/show response."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "details": {
            "family": "qwen3",
            "parameter_size": "8.2B",
            "quantization_level": "Q4_K_M",
        },
        "model_info": {
            "general.parameter_count": 8190735360,
            "qwen3.context_length": 40960,
        },
        "capabilities": ["completion", "tools"],
    }

    with patch("freeagent.model_info.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        info = await fetch_model_info("qwen3:8b")

    assert info is not None
    assert info.name == "qwen3:8b"
    assert info.parameter_count == 8190735360
    assert info.context_length == 40960
    assert info.family == "qwen3"
    assert info.supports_native_tools is True
    assert info.is_medium is True


@pytest.mark.asyncio
async def test_fetch_model_info_connection_error():
    """Returns None when Ollama isn't running."""
    import httpx
    with patch("freeagent.model_info.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_client_cls.return_value = mock_client

        info = await fetch_model_info("qwen3:8b")

    assert info is None


# ── Auto-tuning integration tests ────────────────────────

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


def _make_model_info(param_count, capabilities=None, context_length=8192):
    return ModelInfo(
        name="test",
        parameter_count=param_count,
        context_length=context_length,
        capabilities=capabilities or ["completion", "tools"],
        family="test",
    )


def test_auto_tune_small_model_strips_defaults():
    """Small models (<3B) should have bundled_skills=False and memory_tool=False."""
    small_info = _make_model_info(2_000_000_000)

    with patch.object(Agent, "_detect_model_info", return_value=small_info):
        agent = Agent(model="tiny:2b", provider=MockProvider(), conversation=None)

    # Skills should be empty (bundled stripped)
    assert len(agent.skills) == 0
    # Tools should not include memory tool
    tool_names = [t.name for t in agent.tools]
    assert "memory" not in tool_names


def test_auto_tune_medium_model_keeps_defaults():
    """Medium models (3-14B) should keep bundled skills and memory tool."""
    medium_info = _make_model_info(8_000_000_000)

    with patch.object(Agent, "_detect_model_info", return_value=medium_info):
        agent = Agent(model="qwen3:8b", provider=MockProvider(), conversation=None)

    assert len(agent.skills) > 0
    tool_names = [t.name for t in agent.tools]
    assert "memory" in tool_names


def test_auto_tune_sets_context_window():
    """Auto-tune should set context_window from model_info."""
    info = _make_model_info(8_000_000_000, context_length=40960)

    with patch.object(Agent, "_detect_model_info", return_value=info):
        agent = Agent(model="qwen3:8b", provider=MockProvider(), conversation=None)

    assert agent.config.context_window == 40960


def test_auto_tune_uses_capabilities_for_engine():
    """Model with tools capability should use NativeEngine."""
    info = _make_model_info(8_000_000_000, capabilities=["completion", "tools"])

    with patch.object(Agent, "_detect_model_info", return_value=info):
        from freeagent.tool import tool
        @tool
        def dummy(x: int) -> str:
            """Dummy."""
            return str(x)
        agent = Agent(model="unknown-model:8b", provider=MockProvider(),
                      tools=[dummy], conversation=None)

    # "unknown-model" isn't in the hardcoded list, but model_info says it supports tools
    assert agent._mode == "native"


def test_auto_tune_disabled():
    """auto_tune=False should skip detection entirely."""
    with patch.object(Agent, "_detect_model_info") as mock_detect:
        agent = Agent(model="qwen3:8b", provider=MockProvider(),
                      auto_tune=False, conversation=None)

    mock_detect.assert_not_called()
    assert agent.model_info is None


def test_explicit_bundled_skills_overrides_auto_tune():
    """bundled_skills=True should override auto-tune stripping for small models."""
    small_info = _make_model_info(2_000_000_000)

    with patch.object(Agent, "_detect_model_info", return_value=small_info):
        agent = Agent(model="tiny:2b", provider=MockProvider(),
                      bundled_skills=True, conversation=None)

    assert len(agent.skills) > 0


def test_explicit_memory_tool_overrides_auto_tune():
    """memory_tool=True should override auto-tune stripping for small models."""
    small_info = _make_model_info(2_000_000_000)

    with patch.object(Agent, "_detect_model_info", return_value=small_info):
        agent = Agent(model="tiny:2b", provider=MockProvider(),
                      memory_tool=True, conversation=None)

    tool_names = [t.name for t in agent.tools]
    assert "memory" in tool_names


def test_detection_failure_graceful():
    """If model detection fails, agent still works with defaults."""
    with patch.object(Agent, "_detect_model_info", return_value=None):
        agent = Agent(model="qwen3:8b", provider=MockProvider(), conversation=None)

    assert agent.model_info is None
    assert len(agent.skills) > 0  # bundled skills loaded by default
