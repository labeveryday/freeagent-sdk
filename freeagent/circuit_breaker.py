"""
Circuit breaker for agent loops.

Detects when a model is stuck (calling the same tool with the same
args repeatedly) and enforces iteration limits. Never hang. Never crash.
Always degrade gracefully.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum, auto

from .config import AgentConfig


class BreakerAction(Enum):
    CONTINUE = auto()
    LOOP_DETECTED = auto()
    MAX_ITERATIONS = auto()


@dataclass
class BreakerResult:
    action: BreakerAction
    reason: str = ""


class CircuitBreaker:
    """Prevents infinite loops and runaway agents."""

    def __init__(self, config: AgentConfig):
        self.max_iterations = config.max_iterations
        self.loop_threshold = config.loop_threshold
        self._history: list[str] = []
        self._iteration = 0

    def check(self, tool_name: str, args: dict) -> BreakerResult:
        """Check if we should continue, break a loop, or stop."""
        self._iteration += 1

        # Max iterations
        if self._iteration >= self.max_iterations:
            return BreakerResult(
                action=BreakerAction.MAX_ITERATIONS,
                reason=f"Reached max iterations ({self.max_iterations}).",
            )

        # Loop detection — same tool + same args hash
        sig = self._signature(tool_name, args)
        repeats = self._history.count(sig)
        self._history.append(sig)

        if repeats >= self.loop_threshold:
            return BreakerResult(
                action=BreakerAction.LOOP_DETECTED,
                reason=(
                    f"Tool '{tool_name}' called {repeats + 1} times "
                    f"with identical arguments. Model is stuck."
                ),
            )

        return BreakerResult(action=BreakerAction.CONTINUE)

    def reset(self):
        self._history.clear()
        self._iteration = 0

    @staticmethod
    def _signature(tool_name: str, args: dict) -> str:
        args_str = json.dumps(args, sort_keys=True)
        h = hashlib.md5(args_str.encode()).hexdigest()[:8]
        return f"{tool_name}:{h}"
