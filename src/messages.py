"""
Message types for the conversation history.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Message:
    role: str
    content: str
    tool_calls: list[dict] | None = None
    name: str | None = None  # for tool results

    @classmethod
    def system(cls, content: str) -> Message:
        return cls(role="system", content=content)

    @classmethod
    def user(cls, content: str) -> Message:
        return cls(role="user", content=content)

    @classmethod
    def assistant(cls, content: str, tool_calls: list[dict] = None) -> Message:
        return cls(role="assistant", content=content, tool_calls=tool_calls)

    @classmethod
    def tool_result(cls, name: str, content: str) -> Message:
        return cls(role="tool", content=content, name=name)

    @classmethod
    def tool_error(cls, tool_name: str, errors: list[str], schema: dict = None) -> Message:
        """Construct a specific error message that helps the model self-correct."""
        error_text = "Tool call failed with errors:\n"
        for e in errors:
            error_text += f"- {e}\n"
        if schema:
            import json
            error_text += f"\nExpected schema: {json.dumps(schema)}\n"
        error_text += "\nPlease try again with corrected arguments."
        return cls(role="tool", content=error_text, name=tool_name)

    def to_ollama(self) -> dict:
        """Convert to Ollama API format."""
        msg = {"role": self.role, "content": self.content}
        if self.tool_calls:
            msg["tool_calls"] = self.tool_calls
        return msg
