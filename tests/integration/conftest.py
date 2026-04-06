"""Shared fixtures for integration tests."""

import pytest
import httpx
import tempfile
import shutil
from pathlib import Path


def _ollama_available() -> bool:
    """Check if Ollama is running and reachable."""
    try:
        resp = httpx.get("http://localhost:11434/api/tags", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


def _model_available(model: str) -> bool:
    """Check if a specific model is available in Ollama."""
    try:
        resp = httpx.get("http://localhost:11434/api/tags", timeout=5)
        if resp.status_code != 200:
            return False
        models = [m["name"] for m in resp.json().get("models", [])]
        # Check both exact and base name match
        return any(model in m or m.startswith(model) for m in models)
    except Exception:
        return False


# Skip all integration tests if Ollama is not running
pytestmark = pytest.mark.integration

OLLAMA_AVAILABLE = _ollama_available()
MODELS = {
    "qwen3_8b": "qwen3:8b",
    "qwen3_4b": "qwen3:4b",
    "llama31": "llama3.1:latest",
}


def skip_if_no_ollama():
    return pytest.mark.skipif(
        not OLLAMA_AVAILABLE,
        reason="Ollama not running at localhost:11434",
    )


def skip_if_no_model(model: str):
    return pytest.mark.skipif(
        not _model_available(model),
        reason=f"Model {model} not available in Ollama",
    )


@pytest.fixture
def temp_memory_dir():
    """Provide a temporary directory for memory tests, cleaned up after."""
    d = tempfile.mkdtemp(prefix="freeagent_test_mem_")
    yield d
    shutil.rmtree(d, ignore_errors=True)
