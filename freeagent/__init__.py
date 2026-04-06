"""
FreeAgent SDK — Local-first AI agent framework.
Built for models that aren't perfect.
"""

__version__ = "0.2.0"

from .agent import Agent
from .tool import tool, Tool, ToolResult
from .config import AgentConfig
from .hooks import HookEvent, HookContext, log_hook, cost_hook
from .memory import Memory
from .providers.ollama import OllamaProvider
from .providers.openai_compat import OpenAICompatProvider, VLLMProvider
from .skills import Skill
from .telemetry import Metrics

__all__ = [
    "Agent",
    "tool",
    "Tool",
    "ToolResult",
    "AgentConfig",
    "HookEvent",
    "HookContext",
    "log_hook",
    "cost_hook",
    "Memory",
    "OllamaProvider",
    "OpenAICompatProvider",
    "VLLMProvider",
    "Skill",
    "Metrics",
]
