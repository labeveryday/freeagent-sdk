"""Live model info integration tests — real Ollama, verify detection works."""

import pytest
from freeagent.model_info import fetch_model_info


MODELS = [
    ("qwen3:8b", "qwen3", True, True),      # medium, has tools
    ("qwen3:4b", "qwen3", True, True),       # medium, has tools
    ("llama3.1:latest", "llama", True, True),  # medium, has tools
    ("gemma4:e2b", "gemma4", True, True),    # medium (5.1B), has tools
]


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("model,family,is_medium,has_tools", MODELS)
async def test_fetch_model_info(model, family, is_medium, has_tools):
    """Verify model info detection for all test models."""
    info = await fetch_model_info(model)

    assert info is not None
    assert info.name == model
    assert info.parameter_count > 0
    assert info.context_length > 0
    assert info.family == family
    assert info.is_medium == is_medium
    assert info.supports_native_tools == has_tools
    assert len(info.parameter_size) > 0
    assert len(info.quantization) > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fetch_nonexistent_model():
    """Non-existent model should return None."""
    info = await fetch_model_info("nonexistent:latest")
    # Ollama returns 404 for unknown models
    assert info is None


@pytest.mark.integration
def test_auto_tune_live_qwen3_8b():
    """qwen3:8b should get full defaults with auto-tune."""
    from freeagent import Agent
    agent = Agent(model="qwen3:8b", conversation=None)

    assert agent.model_info is not None
    assert agent.model_info.is_medium is True
    assert len(agent.skills) > 0  # bundled skills kept
    assert any(t.name == "memory" for t in agent.tools)  # memory tool kept
    assert agent._mode == "native"  # detected from capabilities
    assert agent.config.context_window == 40960  # from model info
