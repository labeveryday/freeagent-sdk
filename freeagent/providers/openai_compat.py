"""
OpenAI-compatible provider — works with vLLM, LM Studio, LocalAI, TGI, and any
server that implements the OpenAI /v1/chat/completions API.

Async HTTP via httpx. Supports:
1. Native tool calling via the OpenAI tools API
2. JSON mode via response_format (for constrained generation)

Usage:
    # vLLM
    provider = VLLMProvider(model="qwen3-8b", base_url="http://localhost:8000")

    # Any OpenAI-compatible server
    provider = OpenAICompatProvider(
        model="llama3.1:8b",
        base_url="http://localhost:1234",
        api_key="lm-studio",
    )

    # With the agent
    agent = Agent(model="qwen3-8b", provider=provider, tools=[my_tool])
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import httpx

from ..messages import Message
from . import ProviderResponse, StreamChunk


class OpenAICompatProvider:
    """
    OpenAI-compatible HTTP API client.
    Works with vLLM, LM Studio, LocalAI, text-generation-inference, etc.
    """

    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:8000",
        api_key: str = "",
        timeout: int = 120,
        extra_headers: dict[str, str] | None = None,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._extra_headers = extra_headers or {}
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers = {**self._extra_headers}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers=headers,
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
            raise ConnectionError(f"OpenAI-compat API {e.response.status_code}: {body}") from e
        except httpx.ConnectError as e:
            raise ConnectionError(
                f"Cannot connect to {self.base_url}. Is the server running? ({e})"
            ) from e

    def _to_openai_messages(self, messages: list[Message]) -> list[dict]:
        """Convert internal messages to OpenAI chat format."""
        result = []
        for m in messages:
            msg: dict[str, Any] = {"role": m.role, "content": m.content}
            if m.tool_calls:
                # Convert Ollama-style tool_calls to OpenAI format
                openai_calls = []
                for i, tc in enumerate(m.tool_calls):
                    fn = tc.get("function", {})
                    args = fn.get("arguments", {})
                    openai_calls.append({
                        "id": f"call_{i}",
                        "type": "function",
                        "function": {
                            "name": fn.get("name", ""),
                            "arguments": json.dumps(args) if isinstance(args, dict) else str(args),
                        },
                    })
                msg["tool_calls"] = openai_calls
                # OpenAI requires content to be null when tool_calls present
                if not m.content:
                    msg["content"] = None
            if m.name and m.role == "tool":
                # OpenAI tool results need a tool_call_id
                msg["tool_call_id"] = f"call_0"
            result.append(msg)
        return result

    def _to_openai_tools(self, tools: list[dict]) -> list[dict]:
        """Ensure tools are in OpenAI format (they may already be from Ollama format)."""
        result = []
        for t in tools:
            if "type" in t and "function" in t:
                # Already in OpenAI format
                result.append(t)
            else:
                # Wrap bare function spec
                result.append({"type": "function", "function": t})
        return result

    def _parse_tool_calls(self, tool_calls: list[dict] | None) -> list[dict]:
        """
        Convert OpenAI tool_calls to our internal format (same as Ollama).

        Small model guardrails:
        - Handles malformed JSON arguments (strips thinking tags, code fences)
        - Falls back to empty dict if arguments can't be parsed
        """
        if not tool_calls:
            return []
        result = []
        for tc in tool_calls:
            fn = tc.get("function", {})
            args_raw = fn.get("arguments", "{}")
            args = self._parse_arguments(args_raw)
            result.append({
                "function": {
                    "name": fn.get("name", ""),
                    "arguments": args,
                },
            })
        return result

    @staticmethod
    def _parse_arguments(raw: Any) -> dict:
        """
        Parse tool call arguments with small-model error recovery.

        Handles common issues:
        - String "42" instead of proper JSON
        - Thinking tags (<think>...</think>) mixed into arguments
        - Markdown code fences wrapping JSON
        - Trailing commas, single quotes
        """
        if isinstance(raw, dict):
            return raw
        if not isinstance(raw, str):
            return {}

        text = raw.strip()

        # Strip thinking tags (qwen3, deepseek)
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

        # Strip markdown code fences
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
            text = text.strip()

        # Try direct parse
        try:
            result = json.loads(text)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

        # Try to find a JSON object in the text
        match = re.search(r"\{[^{}]*\}", text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        return {}

    @staticmethod
    def _clean_content(content: str) -> str:
        """Clean model response content — strip thinking tags from final output."""
        if not content:
            return ""
        # Strip thinking tags but keep the actual answer
        cleaned = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
        return cleaned if cleaned else content

    async def chat(self, messages: list[Message], temperature: float = 0.1) -> ProviderResponse:
        payload = {
            "model": self.model,
            "messages": self._to_openai_messages(messages),
            "temperature": temperature,
        }
        data = await self._post("/v1/chat/completions", payload)
        choice = data.get("choices", [{}])[0]
        msg = choice.get("message", {})
        return ProviderResponse(content=self._clean_content(msg.get("content", "") or ""))

    async def chat_with_tools(
        self, messages: list[Message], tools: list[dict], temperature: float = 0.1
    ) -> ProviderResponse:
        payload = {
            "model": self.model,
            "messages": self._to_openai_messages(messages),
            "tools": self._to_openai_tools(tools),
            "temperature": temperature,
        }
        data = await self._post("/v1/chat/completions", payload)
        choice = data.get("choices", [{}])[0]
        msg = choice.get("message", {})
        return ProviderResponse(
            content=self._clean_content(msg.get("content", "") or ""),
            tool_calls=self._parse_tool_calls(msg.get("tool_calls")),
        )

    async def chat_with_format(
        self, messages: list[Message], schema: dict, temperature: float = 0.1
    ) -> str:
        """
        Request JSON output. Uses response_format for servers that support it,
        falls back to prompting for JSON.
        """
        payload = {
            "model": self.model,
            "messages": self._to_openai_messages(messages),
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        try:
            data = await self._post("/v1/chat/completions", payload)
            choice = data.get("choices", [{}])[0]
            return choice.get("message", {}).get("content", "{}")
        except ConnectionError:
            # Server doesn't support response_format — fall back to plain chat
            del payload["response_format"]
            data = await self._post("/v1/chat/completions", payload)
            choice = data.get("choices", [{}])[0]
            return choice.get("message", {}).get("content", "{}")

    async def chat_stream(self, messages: list[Message], temperature: float = 0.1) -> AsyncIterator[StreamChunk]:
        """Stream chat response via SSE."""
        payload = {
            "model": self.model,
            "messages": self._to_openai_messages(messages),
            "temperature": temperature,
            "stream": True,
        }
        async for chunk in self._stream_sse("/v1/chat/completions", payload):
            yield chunk

    async def chat_stream_with_tools(self, messages: list[Message], tools: list[dict], temperature: float = 0.1) -> AsyncIterator[StreamChunk]:
        """Stream chat response with tools via SSE."""
        payload = {
            "model": self.model,
            "messages": self._to_openai_messages(messages),
            "tools": self._to_openai_tools(tools),
            "temperature": temperature,
            "stream": True,
        }
        async for chunk in self._stream_sse("/v1/chat/completions", payload):
            yield chunk

    async def _stream_sse(self, path: str, payload: dict) -> AsyncIterator[StreamChunk]:
        """POST with SSE streaming, parse data: lines."""
        client = self._get_client()
        try:
            async with client.stream("POST", path, json=payload, headers={"Content-Type": "application/json"}) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]  # strip "data: "
                    if data_str == "[DONE]":
                        yield StreamChunk(done=True)
                        return
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    choice = data.get("choices", [{}])[0]
                    delta = choice.get("delta", {})
                    content = self._clean_content(delta.get("content", "") or "")

                    # Parse streaming tool calls
                    tool_calls = []
                    if delta.get("tool_calls"):
                        tool_calls = self._parse_tool_calls(delta["tool_calls"])

                    finish = choice.get("finish_reason")
                    yield StreamChunk(
                        content=content,
                        tool_calls=tool_calls,
                        done=finish is not None,
                    )
        except httpx.HTTPStatusError as e:
            body = e.response.text
            raise ConnectionError(f"OpenAI-compat API {e.response.status_code}: {body}") from e
        except httpx.ConnectError as e:
            raise ConnectionError(
                f"Cannot connect to {self.base_url}. Is the server running? ({e})"
            ) from e

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None


class VLLMProvider(OpenAICompatProvider):
    """
    vLLM provider — OpenAI-compatible with vLLM defaults.

    vLLM serves models on port 8000 with the OpenAI API by default:
        vllm serve qwen3-8b --port 8000

    Usage:
        provider = VLLMProvider(model="qwen3-8b")
        agent = Agent(model="qwen3-8b", provider=provider, tools=[my_tool])
    """

    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:8000",
        api_key: str = "EMPTY",  # vLLM default
        timeout: int = 120,
    ):
        super().__init__(
            model=model,
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
        )
