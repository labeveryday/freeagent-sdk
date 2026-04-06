"""
Response validation and repair.

Every piece of model output passes through validation before
the framework acts on it. Small models produce bad output —
the validator catches it and feeds specific errors back.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from difflib import get_close_matches
from typing import Any

from .tool import Tool


@dataclass
class ValidationOk:
    tool: Tool
    args: dict


@dataclass
class ValidationError:
    errors: list[str]
    schema: dict | None = None


ValidationResult = ValidationOk | ValidationError


class Validator:
    """Validates tool calls from the model."""

    def __init__(self, tools: list[Tool]):
        self.tools = {t.name: t for t in tools}

    def validate(self, tool_name: str, raw_args: Any) -> ValidationResult:
        """
        Validate a tool call:
        1. Does the tool exist? (fuzzy match misspellings)
        2. Are the arguments valid JSON?
        3. Are required fields present?
        4. Coerce types where possible ("42" → 42)
        """
        errors = []

        # 1. Find the tool (with fuzzy matching)
        tool = self.tools.get(tool_name)
        if tool is None:
            close = get_close_matches(tool_name, self.tools.keys(), n=1, cutoff=0.6)
            if close:
                errors.append(
                    f"Unknown tool '{tool_name}'. Did you mean '{close[0]}'?"
                )
            else:
                errors.append(
                    f"Unknown tool '{tool_name}'. "
                    f"Available tools: {', '.join(self.tools.keys())}"
                )
            return ValidationError(errors)

        # 2. Parse arguments
        if isinstance(raw_args, str):
            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError as e:
                errors.append(f"Invalid JSON: {e}")
                return ValidationError(errors, tool.schema())
        elif isinstance(raw_args, dict):
            args = raw_args
        else:
            args = {}

        # 3. Check required fields
        for param in tool.params:
            if param.required and param.name not in args:
                errors.append(
                    f"Missing required field '{param.name}' "
                    f"(type: {param.type})"
                )

        if errors:
            return ValidationError(errors, tool.schema())

        # 4. Type coercion
        args = self._coerce_types(args, tool)

        # 5. Apply defaults for missing optional fields
        for param in tool.params:
            if param.name not in args and param.default is not None:
                args[param.name] = param.default

        return ValidationOk(tool=tool, args=args)

    def _coerce_types(self, args: dict, tool: Tool) -> dict:
        """Try to fix common type issues from small models."""
        coerced = dict(args)
        param_map = {p.name: p for p in tool.params}

        for key, value in coerced.items():
            param = param_map.get(key)
            if param is None:
                continue

            # String numbers → actual numbers
            if param.type == "integer" and isinstance(value, str):
                try:
                    coerced[key] = int(value)
                except ValueError:
                    pass
            elif param.type == "number" and isinstance(value, str):
                try:
                    coerced[key] = float(value)
                except ValueError:
                    pass
            # String booleans → actual booleans
            elif param.type == "boolean" and isinstance(value, str):
                if value.lower() in ("true", "1", "yes"):
                    coerced[key] = True
                elif value.lower() in ("false", "0", "no"):
                    coerced[key] = False

        return coerced
