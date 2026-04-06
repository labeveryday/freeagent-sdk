"""
Ollama model provider — stdlib only, zero external dependencies.

Supports:
1. Native tool calling — sends tool schemas, gets structured tool_calls
2. Constrained JSON — sends JSON schema in format param, GBNF grammar forces valid output
"""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Any

from ..messages import Message
from . import ProviderResponse


class OllamaProvider:
    """Ollama HTTP API client — zero dependencies."""

    def __init__(self, model: str, base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = 120

    def _post(self, path: str, payload: dict) -> dict:
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise ConnectionError(f"Ollama {e.code}: {body}") from e
        except urllib.error.URLError as e:
            raise ConnectionError(
                f"Cannot connect to Ollama at {self.base_url}. "
                f"Is it running? ({e.reason})"
            ) from e

    async def chat(self, messages: list[Message], temperature: float = 0.1) -> ProviderResponse:
        payload = {
            "model": self.model,
            "messages": [m.to_ollama() for m in messages],
            "stream": False,
            "options": {"temperature": temperature},
        }
        data = self._post("/api/chat", payload)
        return ProviderResponse(content=data.get("message", {}).get("content", ""))

    async def chat_with_tools(self, messages: list[Message], tools: list[dict], temperature: float = 0.1) -> ProviderResponse:
        payload = {
            "model": self.model,
            "messages": [m.to_ollama() for m in messages],
            "tools": tools,
            "stream": False,
            "options": {"temperature": temperature},
        }
        data = self._post("/api/chat", payload)
        msg = data.get("message", {})
        return ProviderResponse(
            content=msg.get("content", ""),
            tool_calls=msg.get("tool_calls", []),
        )

    async def chat_with_format(self, messages: list[Message], schema: dict, temperature: float = 0.1) -> str:
        payload = {
            "model": self.model,
            "messages": [m.to_ollama() for m in messages],
            "format": schema,
            "stream": False,
            "options": {"temperature": temperature},
        }
        data = self._post("/api/chat", payload)
        return data.get("message", {}).get("content", "{}")

    async def close(self):
        pass
