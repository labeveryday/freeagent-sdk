"""
Context window management — keep conversations within the model's limits.

Small models have tiny context windows (4K-8K tokens). This module
estimates token usage and prunes old messages when needed.
"""

from __future__ import annotations

from .config import AgentConfig
from .messages import Message


def estimate_tokens(text: str) -> int:
    """
    Rough token estimate: ~4 chars per token for English text.
    Good enough for budget management — not meant to be exact.
    """
    return len(text) // 4


def estimate_messages_tokens(messages: list[Message]) -> int:
    """Estimate total tokens across all messages."""
    total = 0
    for m in messages:
        total += estimate_tokens(m.content or "")
        if m.tool_calls:
            total += estimate_tokens(str(m.tool_calls))
    return total


def check_context_window(messages: list[Message], config: AgentConfig) -> list[Message]:
    """
    Prune messages if total tokens exceed the soft threshold.

    Rules:
    - Never drop the system prompt (first message)
    - Never drop the current user message (second message)
    - Prune oldest tool results first (they're the biggest)
    - Then prune oldest assistant messages

    Returns the (potentially pruned) message list.
    """
    threshold = int(config.context_window * config.context_soft_threshold)
    total = estimate_messages_tokens(messages)

    if total <= threshold:
        return messages

    # Keep system prompt and latest user message protected
    # System prompt is messages[0], latest user message is messages[1]
    protected = set()
    if messages:
        protected.add(0)  # system prompt
    if len(messages) > 1:
        protected.add(1)  # first user message

    # Also protect the last 2 messages (most recent context)
    for i in range(max(0, len(messages) - 2), len(messages)):
        protected.add(i)

    # Build prunable indices, prioritizing tool results then assistant messages
    tool_indices = []
    assistant_indices = []
    for i, m in enumerate(messages):
        if i in protected:
            continue
        if m.role == "tool":
            tool_indices.append(i)
        elif m.role == "assistant":
            assistant_indices.append(i)

    # Prune oldest tool results first
    pruned = set()
    for i in tool_indices:
        if total <= threshold:
            break
        total -= estimate_tokens(messages[i].content or "")
        pruned.add(i)

    # Then assistant messages if still over
    for i in assistant_indices:
        if total <= threshold:
            break
        total -= estimate_tokens(messages[i].content or "")
        pruned.add(i)

    if not pruned:
        return messages

    return [m for i, m in enumerate(messages) if i not in pruned]
