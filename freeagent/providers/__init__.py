"""
Model providers — pluggable backends for the agent.

All providers implement the same 3-method interface:
  - chat(messages, temperature) → Response
  - chat_with_tools(messages, tools, temperature) → Response
  - chat_with_format(messages, schema, temperature) → str
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Protocol, runtime_checkable

from ..messages import Message


@dataclass
class ProviderResponse:
    """Unified response from any provider."""
    content: str = ""
    tool_calls: list[dict] = field(default_factory=list)


@dataclass
class StreamChunk:
    """A single chunk from a streaming response."""
    content: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    done: bool = False


@runtime_checkable
class Provider(Protocol):
    """Interface that all model providers must implement."""

    model: str

    async def chat(self, messages: list[Message], temperature: float = 0.1) -> ProviderResponse: ...

    async def chat_with_tools(self, messages: list[Message], tools: list[dict],
                               temperature: float = 0.1) -> ProviderResponse: ...

    async def chat_with_format(self, messages: list[Message], schema: dict,
                                temperature: float = 0.1) -> str: ...

    async def chat_stream(self, messages: list[Message],
                           temperature: float = 0.1) -> AsyncIterator[StreamChunk]: ...

    async def chat_stream_with_tools(self, messages: list[Message], tools: list[dict],
                                      temperature: float = 0.1) -> AsyncIterator[StreamChunk]: ...


from .ollama import OllamaProvider
from .openai_compat import OpenAICompatProvider, VLLMProvider
