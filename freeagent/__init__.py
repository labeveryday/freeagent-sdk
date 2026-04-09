"""
FreeAgent SDK — Local-first AI agent framework.
Built for models that aren't perfect.
"""

__version__ = "0.3.3"

from .agent import Agent
from .tool import tool, Tool, ToolResult
from .config import AgentConfig
from .hooks import HookEvent, HookContext, log_hook, cost_hook
from .memory import Memory
from .providers.ollama import OllamaProvider
from .providers.openai_compat import OpenAICompatProvider, VLLMProvider
from .skills import Skill
from .conversation import ConversationManager, SlidingWindow, TokenWindow, UnlimitedHistory
from .telemetry import Metrics
from .events import (
    RunStartEvent, TokenEvent, ToolCallEvent, ToolResultEvent,
    ValidationErrorEvent, RetryEvent, IterationEvent, RunCompleteEvent, RunEvent,
)

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
    "ConversationManager",
    "SlidingWindow",
    "TokenWindow",
    "UnlimitedHistory",
    "Metrics",
    "RunStartEvent",
    "TokenEvent",
    "ToolCallEvent",
    "ToolResultEvent",
    "ValidationErrorEvent",
    "RetryEvent",
    "IterationEvent",
    "RunCompleteEvent",
    "RunEvent",
]

# Conditional MCP export (only if mcp package is installed)
try:
    from .mcp import connect as mcp_connect
    __all__.append("mcp_connect")
except ImportError:
    pass
