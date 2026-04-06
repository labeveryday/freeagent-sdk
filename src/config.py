"""
Agent configuration with sensible defaults for local models.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentConfig:
    """Configuration for agent behavior and guardrails."""

    # Execution limits
    max_iterations: int = 10
    max_retries: int = 3
    timeout_seconds: float = 120.0

    # Circuit breaker
    loop_threshold: int = 3  # same tool+args N times = stuck

    # Model behavior
    temperature: float = 0.1  # low temp for tool calling reliability
    prefer_native_tools: bool = True  # use Ollama native tool API when available

    # Ollama connection
    ollama_base_url: str = "http://localhost:11434"
    model: str = "llama3.1:8b"

    # Known models that support native tool calling well
    native_tool_models: list[str] = field(default_factory=lambda: [
        "llama3.1", "llama3.2", "llama3.3", "llama4",
        "qwen3", "qwen2.5",
        "mistral", "mistral-nemo",
        "command-r",
        "gpt-oss",
    ])

    def supports_native_tools(self, model_name: str) -> bool:
        """Check if a model likely supports native tool calling."""
        base = model_name.split(":")[0].lower()
        return any(known in base for known in self.native_tool_models)
