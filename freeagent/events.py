"""
Streaming events — semantic event types for agent.run_stream().

Each event represents a meaningful moment during agent execution:
run start, token output, tool calls/results, validation errors, retries, and run completion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Union


@dataclass
class RunStartEvent:
    """Emitted when the agent run begins."""
    model: str
    mode: str


@dataclass
class TokenEvent:
    """Emitted for each text token during streaming response."""
    text: str
    iteration: int


@dataclass
class ToolCallEvent:
    """Emitted when the model requests a tool call."""
    name: str
    args: dict


@dataclass
class ToolResultEvent:
    """Emitted after a tool finishes executing."""
    name: str
    result: str
    success: bool
    duration_ms: float


@dataclass
class ValidationErrorEvent:
    """Emitted when a tool call fails validation."""
    tool_name: str
    errors: list[str]


@dataclass
class RetryEvent:
    """Emitted when retrying after a validation error."""
    tool_name: str
    retry_count: int


@dataclass
class IterationEvent:
    """Emitted at the start of each agent loop iteration."""
    iteration: int


@dataclass
class RunCompleteEvent:
    """Emitted when the agent run finishes."""
    response: str
    elapsed_ms: float
    metrics: dict


RunEvent = Union[
    RunStartEvent,
    TokenEvent,
    ToolCallEvent,
    ToolResultEvent,
    ValidationErrorEvent,
    RetryEvent,
    IterationEvent,
    RunCompleteEvent,
]
