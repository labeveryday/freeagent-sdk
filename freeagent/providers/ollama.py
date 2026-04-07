"""
Ollama model provider — async HTTP via httpx.

Supports:
1. Native tool calling — sends tool schemas, gets structured tool_calls
2. Constrained JSON — sends JSON schema in format param, GBNF grammar forces valid output
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import httpx

from ..messages import Message
from . import ProviderResponse, StreamChunk


class OllamaProvider:
    """Ollama HTTP API client."""

    def __init__(self, model: str, base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = 120
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._client

    async def _post(self, path: str, payload: dict) -> dict:
        client = self._get_client()
        try:
            resp = await client.post(
                path,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            body = e.response.text
            raise ConnectionError(f"Ollama {e.response.status_code}: {body}") from e
        except httpx.ConnectError as e:
            raise ConnectionError(
                f"Cannot connect to Ollama at {self.base_url}. "
                f"Is it running? ({e})"
            ) from e

    async def chat(self, messages: list[Message], temperature: float = 0.1) -> ProviderResponse:
        payload = {
            "model": self.model,
            "messages": [m.to_ollama() for m in messages],
            "stream": False,
            "options": {"temperature": temperature},
        }
        data = await self._post("/api/chat", payload)
        return ProviderResponse(content=data.get("message", {}).get("content", ""))

    async def chat_with_tools(self, messages: list[Message], tools: list[dict], temperature: float = 0.1) -> ProviderResponse:
        payload = {
            "model": self.model,
            "messages": [m.to_ollama() for m in messages],
            "tools": tools,
            "stream": False,
            "options": {"temperature": temperature},
        }
        data = await self._post("/api/chat", payload)
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
        data = await self._post("/api/chat", payload)
        return data.get("message", {}).get("content", "{}")

    async def chat_stream(self, messages: list[Message], temperature: float = 0.1) -> AsyncIterator[StreamChunk]:
        """Stream chat response token by token."""
        payload = {
            "model": self.model,
            "messages": [m.to_ollama() for m in messages],
            "stream": True,
            "options": {"temperature": temperature},
        }
        async for chunk in self._stream_post("/api/chat", payload):
            yield chunk

    async def chat_stream_with_tools(self, messages: list[Message], tools: list[dict], temperature: float = 0.1) -> AsyncIterator[StreamChunk]:
        """Stream chat response with tools. Tool calls arrive in chunks too."""
        payload = {
            "model": self.model,
            "messages": [m.to_ollama() for m in messages],
            "tools": tools,
            "stream": True,
            "options": {"temperature": temperature},
        }
        async for chunk in self._stream_post("/api/chat", payload):
            yield chunk

    async def _stream_post(self, path: str, payload: dict) -> AsyncIterator[StreamChunk]:
        """POST with streaming, parse JSONL lines from Ollama."""
        client = self._get_client()
        try:
            async with client.stream("POST", path, json=payload, headers={"Content-Type": "application/json"}) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    msg = data.get("message", {})
                    done = data.get("done", False)
                    yield StreamChunk(
                        content=msg.get("content", ""),
                        tool_calls=msg.get("tool_calls", []),
                        done=done,
                    )
        except httpx.HTTPStatusError as e:
            body = e.response.text
            raise ConnectionError(f"Ollama {e.response.status_code}: {body}") from e
        except httpx.ConnectError as e:
            raise ConnectionError(
                f"Cannot connect to Ollama at {self.base_url}. "
                f"Is it running? ({e})"
            ) from e

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
