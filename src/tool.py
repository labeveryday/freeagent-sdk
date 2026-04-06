"""
Tool definition system.

Tools are defined as simple functions with the @tool decorator.
The decorator extracts the function signature and docstring to
build the JSON schema automatically. Keep schemas flat and simple —
every field you add is a chance for a small model to fail.
"""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, get_type_hints


@dataclass
class ToolResult:
    """Result of a tool execution. Errors are values, not exceptions."""
    success: bool
    data: Any = None
    error: str | None = None

    @classmethod
    def ok(cls, data: Any) -> ToolResult:
        return cls(success=True, data=data)

    @classmethod
    def fail(cls, error: str) -> ToolResult:
        return cls(success=False, error=error)

    def to_message(self) -> str:
        if self.success:
            if isinstance(self.data, dict):
                return json.dumps(self.data)
            return str(self.data)
        return json.dumps({"error": self.error})


# Python type → JSON schema type mapping
_TYPE_MAP = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


@dataclass
class ToolParam:
    """A single parameter for a tool."""
    name: str
    type: str
    description: str = ""
    required: bool = True
    default: Any = None


@dataclass
class Tool:
    """A tool that an agent can use."""
    name: str
    description: str
    params: list[ToolParam] = field(default_factory=list)
    fn: Callable = None

    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with the given arguments."""
        try:
            result = self.fn(**kwargs)
            # Handle async functions
            if inspect.iscoroutine(result):
                result = await result
            return ToolResult.ok(result)
        except Exception as e:
            return ToolResult.fail(str(e))

    def schema(self) -> dict:
        """Generate JSON schema for this tool's parameters."""
        properties = {}
        required = []

        for p in self.params:
            prop = {"type": p.type}
            if p.description:
                prop["description"] = p.description
            if p.default is not None:
                prop["default"] = p.default
            properties[p.name] = prop
            if p.required:
                required.append(p.name)

        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }

    def to_ollama_spec(self) -> dict:
        """Convert to Ollama's tool format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.schema(),
            },
        }

    def to_react_description(self) -> str:
        """Human-readable description for ReAct prompts."""
        params_desc = []
        for p in self.params:
            desc = f"  - {p.name} ({p.type})"
            if p.description:
                desc += f": {p.description}"
            if not p.required:
                desc += f" [optional, default={p.default}]"
            params_desc.append(desc)

        params_str = "\n".join(params_desc) if params_desc else "  (no parameters)"
        return f"{self.name}: {self.description}\n  Parameters:\n{params_str}"


def tool(fn: Callable = None, *, name: str = None, description: str = None):
    """
    Decorator to turn a function into a Tool.

    Usage:
        @tool
        def weather(city: str) -> dict:
            '''Get weather for a city.'''
            return {"temp": 72, "condition": "sunny"}

        @tool(name="get_weather", description="Fetch weather data")
        def weather(city: str):
            ...
    """
    def decorator(func: Callable) -> Tool:
        tool_name = name or func.__name__
        tool_desc = description or (func.__doc__ or "").strip()

        # Extract parameters from type hints
        hints = get_type_hints(func)
        sig = inspect.signature(func)
        params = []

        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue

            param_type = hints.get(param_name, str)
            json_type = _TYPE_MAP.get(param_type, "string")

            has_default = param.default is not inspect.Parameter.empty
            default_val = param.default if has_default else None

            # Try to extract per-param description from docstring
            param_desc = _extract_param_doc(func.__doc__, param_name)

            params.append(ToolParam(
                name=param_name,
                type=json_type,
                description=param_desc,
                required=not has_default,
                default=default_val,
            ))

        return Tool(
            name=tool_name,
            description=tool_desc,
            params=params,
            fn=func,
        )

    if fn is not None:
        return decorator(fn)
    return decorator


def _extract_param_doc(docstring: str | None, param_name: str) -> str:
    """Extract parameter description from docstring (Google/numpy style)."""
    if not docstring:
        return ""
    for line in docstring.split("\n"):
        stripped = line.strip()
        if stripped.startswith(f"{param_name}:") or stripped.startswith(f"{param_name} "):
            parts = stripped.split(":", 1)
            if len(parts) > 1:
                return parts[1].strip()
    return ""
