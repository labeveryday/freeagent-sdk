"""
Execution engines — the core of the dual-mode architecture.

NativeEngine: Uses the provider's tool calling API (preferred for capable models)
ReactEngine: Text-based ReAct with constrained JSON (fallback for weaker models)

Both engines work with any provider that implements the Provider protocol.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from ..messages import Message
from ..tool import Tool

if TYPE_CHECKING:
    from ..providers import Provider


@dataclass
class ToolCall:
    """A single tool call from the model."""
    id: str = ""
    name: str = ""
    args: dict = field(default_factory=dict)


@dataclass
class EngineResult:
    """Result from an execution engine step."""
    is_tool_call: bool
    content: str = ""
    tool_name: str = ""
    tool_args: dict = None
    tool_calls: list[ToolCall] = field(default_factory=list)

    @classmethod
    def text(cls, content: str) -> EngineResult:
        return cls(is_tool_call=False, content=content)

    @classmethod
    def tool_call(cls, name: str, args: dict) -> EngineResult:
        tc = ToolCall(name=name, args=args or {})
        return cls(is_tool_call=True, tool_name=name, tool_args=args or {}, tool_calls=[tc])

    @classmethod
    def multi_tool_call(cls, calls: list[ToolCall]) -> EngineResult:
        """Multiple parallel tool calls."""
        first = calls[0] if calls else ToolCall()
        return cls(
            is_tool_call=True,
            tool_name=first.name,
            tool_args=first.args,
            tool_calls=calls,
        )


class ExecutionEngine(ABC):
    @abstractmethod
    async def execute(
        self,
        messages: list[Message],
        tools: list[Tool],
        temperature: float,
    ) -> EngineResult:
        ...


class NativeEngine(ExecutionEngine):
    """
    Uses the provider's native tool calling API.
    The model was fine-tuned for tool use — the provider handles parsing.
    Best for: llama3.1+, qwen3, mistral-nemo
    """

    def __init__(self, provider: Provider):
        self.provider = provider

    async def execute(
        self,
        messages: list[Message],
        tools: list[Tool],
        temperature: float = 0.1,
    ) -> EngineResult:
        tool_specs = [t.to_ollama_spec() for t in tools]

        response = await self.provider.chat_with_tools(
            messages=messages,
            tools=tool_specs,
            temperature=temperature,
        )

        # Model returned tool calls
        if response.tool_calls:
            calls = []
            for i, call in enumerate(response.tool_calls):
                fn = call.get("function", {})
                calls.append(ToolCall(
                    id=f"call_{i}",
                    name=fn.get("name", ""),
                    args=fn.get("arguments", {}),
                ))
            if len(calls) == 1:
                return EngineResult.tool_call(calls[0].name, calls[0].args)
            return EngineResult.multi_tool_call(calls)

        # Model returned text (final answer or thinking)
        return EngineResult.text(response.content)


class ReactEngine(ExecutionEngine):
    """
    Text-based ReAct with two-step generation.

    Step 1: Free-text reasoning (Thought + Action name)
    Step 2: Constrained JSON for arguments (GBNF grammar or JSON mode)

    The key insight: asking a small model to think AND produce
    structured JSON in one shot is where it fails. Split them.

    This engine is the main guardrail for small/weak models that
    can't do native tool calling reliably. It works with any provider.
    """

    REACT_PROMPT = """You have access to the following tools:

{tool_descriptions}

To use a tool, respond EXACTLY in this format:
Thought: <your reasoning about what to do>
Action: <tool_name>
Action Input: <JSON arguments>

When you have the final answer, respond:
Thought: <your reasoning>
Final Answer: <your response to the user>

IMPORTANT: Always start with "Thought:". Use exact tool names. Action Input must be valid JSON."""

    # Patterns for parsing ReAct output
    ACTION_PATTERN = re.compile(
        r"Action\s*:\s*(\S+)\s*[\n\r]+\s*Action\s*Input\s*:\s*(.*?)(?:\n\s*(?:Thought|Observation)|$)",
        re.DOTALL | re.IGNORECASE,
    )
    FINAL_ANSWER_PATTERN = re.compile(
        r"Final\s*Answer\s*:\s*(.*)",
        re.DOTALL | re.IGNORECASE,
    )

    def __init__(self, provider: Provider):
        self.provider = provider

    async def execute(
        self,
        messages: list[Message],
        tools: list[Tool],
        temperature: float = 0.1,
    ) -> EngineResult:
        # Inject ReAct instructions into system context
        react_prompt = self.REACT_PROMPT.format(
            tool_descriptions="\n\n".join(
                t.to_react_description() for t in tools
            )
        )

        # Add react prompt as system message if not already present
        augmented = list(messages)
        if not any(react_prompt in m.content for m in augmented if m.role == "system"):
            augmented.insert(1, Message.system(react_prompt))

        # Step 1: Get free-text reasoning
        response = await self.provider.chat(
            messages=augmented,
            temperature=temperature,
        )
        text = response.content

        # Check for final answer
        final_match = self.FINAL_ANSWER_PATTERN.search(text)
        if final_match:
            return EngineResult.text(final_match.group(1).strip())

        # Check for action
        action_match = self.ACTION_PATTERN.search(text)
        if action_match:
            tool_name = action_match.group(1).strip()
            raw_args = action_match.group(2).strip()

            # Try to parse the inline JSON first
            args = self._try_parse_json(raw_args)

            if args is not None:
                return EngineResult.tool_call(tool_name, args)

            # Step 2: If inline JSON failed, use constrained generation
            tool = next((t for t in tools if t.name == tool_name), None)
            if tool:
                args = await self._constrained_args(
                    augmented, tool, tool_name, temperature
                )
                return EngineResult.tool_call(tool_name, args)

        # No action found — treat entire response as text
        return EngineResult.text(text)

    async def _constrained_args(
        self,
        messages: list[Message],
        tool: Tool,
        tool_name: str,
        temperature: float,
    ) -> dict:
        """
        Second-pass: ask for JUST the arguments with schema-constrained output.
        Uses the provider's constrained generation (GBNF grammar, JSON mode, etc.)
        """
        prompt_msg = Message.user(
            f"You are calling the tool '{tool_name}'. "
            f"Provide ONLY the JSON arguments matching this schema:\n"
            f"{json.dumps(tool.schema())}\n"
            f"Output ONLY valid JSON, nothing else."
        )

        raw = await self.provider.chat_with_format(
            messages=messages + [prompt_msg],
            schema=tool.schema(),
            temperature=temperature,
        )

        return self._try_parse_json(raw) or {}

    @staticmethod
    def _try_parse_json(text: str) -> dict | None:
        """Try to parse JSON, handling common small-model quirks."""
        text = text.strip()

        # Strip markdown code fences (common with small models)
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

        # Strip thinking tags (qwen3, deepseek)
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

        try:
            result = json.loads(text)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

        # Try to find JSON object in the text (model wrapped it in explanation)
        match = re.search(r"\{[^{}]*\}", text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        return None
