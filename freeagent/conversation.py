"""
Conversation management — pluggable strategies for multi-turn state.

Controls how conversation history accumulates across agent.run() calls
and what happens when the history gets too long for the model's context window.

Usage:
    from freeagent import Agent
    from freeagent.conversation import SlidingWindow, TokenWindow

    # Default — sliding window, 20 turns
    agent = Agent(model="qwen3:8b")
    agent.run("Turn 1")
    agent.run("Turn 2")  # remembers turn 1

    # Custom window
    agent = Agent(model="qwen3:4b", conversation=SlidingWindow(max_turns=5))

    # Token-based budget
    agent = Agent(model="qwen3:4b", conversation=TokenWindow(max_tokens=3000))

    # No conversation (each run is independent)
    agent = Agent(model="qwen3:8b", conversation=None)

    # Clear mid-conversation
    agent.conversation.clear()
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections import deque
from pathlib import Path
from typing import Any

from .messages import Message


# ── ABC ───────────────────────────────────────────────────

class ConversationManager(ABC):
    """
    Base class for conversation management strategies.

    Two hooks into the agent lifecycle:
    - prepare(): called before the model, returns the full message list
    - commit(): called after the turn, stores the updated messages

    Implement these to create custom strategies.
    """

    @abstractmethod
    def prepare(self, system: str, user_input: str) -> list[Message]:
        """
        Build the message list for this turn.
        Includes system prompt, conversation history, and new user message.
        """
        ...

    @abstractmethod
    def commit(self, messages: list[Message]) -> None:
        """
        Store messages after the turn completes.
        The messages list includes model responses and tool results from this turn.
        """
        ...

    @abstractmethod
    def clear(self) -> None:
        """Reset conversation state."""
        ...

    def to_dict(self) -> dict:
        """Serialize state for session persistence."""
        return {}

    def from_dict(self, data: dict) -> None:
        """Restore state from session persistence."""
        pass

    @property
    def turn_count(self) -> int:
        """Number of user turns in the conversation."""
        return 0


# ── Sliding Window ────────────────────────────────────────

class SlidingWindow(ConversationManager):
    """
    Keep the last N turns of conversation.

    A turn = one user message + everything that follows (assistant, tool calls,
    tool results) until the next user message. When max_turns is exceeded,
    the oldest turn is dropped.

    This is the default strategy. No extra model calls, predictable token usage.

    Args:
        max_turns: Maximum number of turns to keep. Default 20.
    """

    def __init__(self, max_turns: int = 20):
        self.max_turns = max_turns
        self._history: deque[Message] = deque()

    def prepare(self, system: str, user_input: str) -> list[Message]:
        messages = [Message.system(system)]
        messages.extend(self._history)
        messages.append(Message.user(user_input))
        return messages

    def commit(self, messages: list[Message]) -> None:
        # Store everything except the system prompt
        self._history = deque(m for m in messages if m.role != "system")
        self._prune()

    def clear(self) -> None:
        self._history.clear()

    @property
    def turn_count(self) -> int:
        return sum(1 for m in self._history if m.role == "user")

    def _prune(self):
        """Drop oldest turns until within max_turns."""
        while self._count_turns() > self.max_turns and self._history:
            self._drop_oldest_turn()

    def _count_turns(self) -> int:
        return sum(1 for m in self._history if m.role == "user")

    def _drop_oldest_turn(self):
        """Remove the oldest complete turn (user + all responses until next user)."""
        if not self._history:
            return

        # Find first user message
        first_user = None
        for i, m in enumerate(self._history):
            if m.role == "user":
                first_user = i
                break

        if first_user is None:
            # No user messages — clear everything
            self._history.clear()
            return

        # Find the next user message (end of this turn)
        next_user = None
        for i in range(first_user + 1, len(self._history)):
            if self._history[i].role == "user":
                next_user = i
                break

        # Drop everything from start to next_user (or all if no next user)
        if next_user is not None:
            for _ in range(next_user):
                self._history.popleft()
        else:
            self._history.clear()

    def to_dict(self) -> dict:
        return {
            "type": "SlidingWindow",
            "max_turns": self.max_turns,
            "history": [_msg_to_dict(m) for m in self._history],
        }

    def from_dict(self, data: dict) -> None:
        self.max_turns = data.get("max_turns", self.max_turns)
        self._history = [_msg_from_dict(d) for d in data.get("history", [])]


# ── Token Window ──────────────────────────────────────────

class TokenWindow(ConversationManager):
    """
    Keep conversation history that fits within a token budget.

    Fills history from most recent to oldest, stopping when the budget
    is exhausted. More precise than turn-based windowing for models
    with known context limits.

    Args:
        max_tokens: Maximum tokens for conversation history (excludes system prompt).
    """

    def __init__(self, max_tokens: int = 4000):
        self.max_tokens = max_tokens
        self._history: list[Message] = []

    def prepare(self, system: str, user_input: str) -> list[Message]:
        user_msg = Message.user(user_input)
        budget = self.max_tokens - _estimate_tokens(user_input)

        # Fill from most recent, working backward
        window: list[Message] = []
        for msg in reversed(self._history):
            cost = _estimate_tokens(msg.content or "")
            if msg.tool_calls:
                cost += _estimate_tokens(str(msg.tool_calls))
            if budget - cost < 0:
                break
            window.insert(0, msg)
            budget -= cost

        messages = [Message.system(system)]
        messages.extend(window)
        messages.append(user_msg)
        return messages

    def commit(self, messages: list[Message]) -> None:
        self._history = [m for m in messages if m.role != "system"]

    def clear(self) -> None:
        self._history.clear()

    @property
    def turn_count(self) -> int:
        return sum(1 for m in self._history if m.role == "user")

    def to_dict(self) -> dict:
        return {
            "type": "TokenWindow",
            "max_tokens": self.max_tokens,
            "history": [_msg_to_dict(m) for m in self._history],
        }

    def from_dict(self, data: dict) -> None:
        self.max_tokens = data.get("max_tokens", self.max_tokens)
        self._history = [_msg_from_dict(d) for d in data.get("history", [])]


# ── Unlimited (no pruning) ────────────────────────────────

class UnlimitedHistory(ConversationManager):
    """
    Keep all conversation history. No pruning.
    Use with caution on small models — will overflow the context window.
    """

    def __init__(self):
        self._history: list[Message] = []

    def prepare(self, system: str, user_input: str) -> list[Message]:
        messages = [Message.system(system)]
        messages.extend(self._history)
        messages.append(Message.user(user_input))
        return messages

    def commit(self, messages: list[Message]) -> None:
        self._history = [m for m in messages if m.role != "system"]

    def clear(self) -> None:
        self._history.clear()

    @property
    def turn_count(self) -> int:
        return sum(1 for m in self._history if m.role == "user")

    def to_dict(self) -> dict:
        return {
            "type": "UnlimitedHistory",
            "history": [_msg_to_dict(m) for m in self._history],
        }

    def from_dict(self, data: dict) -> None:
        self._history = [_msg_from_dict(d) for d in data.get("history", [])]


# ── Session Persistence ──────────────────────────────────

class Session:
    """
    Persists a ConversationManager's state to a JSONL file.
    Wraps any conversation strategy with save/restore.

    Usage:
        session = Session("my-chat", dir=".freeagent/sessions")
        session.save(conversation_manager)
        session.restore(conversation_manager)
    """

    def __init__(self, name: str, session_dir: str | Path = ".freeagent/sessions"):
        self.name = name
        self._dir = Path(session_dir).expanduser().resolve()
        self._path = self._dir / f"{name}.json"

    def save(self, manager: ConversationManager) -> None:
        """Save conversation state to disk."""
        self._dir.mkdir(parents=True, exist_ok=True)
        data = {
            "session": self.name,
            "manager": manager.to_dict(),
        }
        self._path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    def restore(self, manager: ConversationManager) -> bool:
        """Restore conversation state from disk. Returns True if restored."""
        if not self._path.is_file():
            return False
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            manager.from_dict(data.get("manager", {}))
            return True
        except (json.JSONDecodeError, OSError, KeyError):
            return False

    def delete(self) -> None:
        """Delete the session file."""
        if self._path.is_file():
            self._path.unlink()

    @property
    def exists(self) -> bool:
        return self._path.is_file()


# ── Helpers ───────────────────────────────────────────────

def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    return len(text) // 4


def _msg_to_dict(m: Message) -> dict:
    """Serialize a Message to a dict."""
    d: dict[str, Any] = {"role": m.role, "content": m.content}
    if m.tool_calls:
        d["tool_calls"] = m.tool_calls
    if m.name:
        d["name"] = m.name
    return d


def _msg_from_dict(d: dict) -> Message:
    """Deserialize a Message from a dict."""
    return Message(
        role=d["role"],
        content=d.get("content", ""),
        tool_calls=d.get("tool_calls"),
        name=d.get("name"),
    )
