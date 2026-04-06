"""
Tool output sanitization — clean and truncate before feeding back to the model.

Small models choke on ANSI codes, HTML tags, deeply nested JSON, and
massive tool outputs. This module makes tool results model-friendly.
"""

from __future__ import annotations

import json
import re


# ANSI escape sequences
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")

# HTML tags
_HTML_RE = re.compile(r"<[^>]+>")

# Multiple whitespace / blank lines
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")


def sanitize_tool_output(output: str) -> str:
    """
    Clean tool output for model consumption.

    Strips ANSI codes, HTML tags, normalizes whitespace,
    and flattens nested JSON to depth 3.
    """
    if not output:
        return output

    # Strip ANSI escape codes
    text = _ANSI_RE.sub("", output)

    # Strip HTML tags
    text = _HTML_RE.sub("", text)

    # Normalize whitespace
    text = _MULTI_NEWLINE_RE.sub("\n\n", text)
    text = _MULTI_SPACE_RE.sub(" ", text)

    # Try to flatten deeply nested JSON
    try:
        data = json.loads(text)
        if isinstance(data, (dict, list)):
            text = json.dumps(_flatten_json(data, max_depth=3), indent=None)
    except (json.JSONDecodeError, ValueError):
        pass

    return text.strip()


def truncate_tool_output(output: str, max_chars: int, strategy: str = "truncate") -> str:
    """
    Truncate tool output to fit within token budget.

    Strategies:
    - "truncate": simple cut with [truncated] marker
    - "summarize_head_tail": keep first and last portions
    """
    if not output or len(output) <= max_chars:
        return output

    if strategy == "summarize_head_tail":
        # Keep ~60% from head, ~30% from tail, leave room for marker
        marker = "\n\n[... truncated ...]\n\n"
        available = max_chars - len(marker)
        head_size = int(available * 0.6)
        tail_size = available - head_size
        return output[:head_size] + marker + output[-tail_size:]

    # Default: simple truncate
    marker = "\n[truncated — output was {} chars]"
    marker = marker.format(len(output))
    return output[:max_chars - len(marker)] + marker


def _flatten_json(obj: object, max_depth: int, depth: int = 0) -> object:
    """Flatten nested JSON to a max depth. Beyond that, stringify."""
    if depth >= max_depth:
        if isinstance(obj, (dict, list)):
            return str(obj)[:200] + "..." if len(str(obj)) > 200 else str(obj)
        return obj

    if isinstance(obj, dict):
        return {k: _flatten_json(v, max_depth, depth + 1) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_flatten_json(item, max_depth, depth + 1) for item in obj[:20]]

    return obj
