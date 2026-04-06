"""
Hooks — lifecycle event system for the agent loop.

Hooks let you observe and modify agent behavior at every stage
without subclassing or monkey-patching. Register callbacks for
events like before/after tool calls, on error, on loop, etc.

Usage:
    agent = Agent(model="llama3.1:8b", tools=[weather])

    @agent.on("before_tool")
    def log_tool(event):
        print(f"Calling {event.tool_name} with {event.args}")

    @agent.on("after_tool")
    def check_result(event):
        if event.result.success:
            print(f"Got: {event.result.data}")

    @agent.on("on_error")
    def handle_error(event):
        log_to_sentry(event.error)

    @agent.on("on_token")
    def stream_output(event):
        print(event.content, end="", flush=True)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class HookEvent(str, Enum):
    """All lifecycle events in the agent loop."""

    # Agent lifecycle
    BEFORE_RUN = "before_run"          # agent.run() called
    AFTER_RUN = "after_run"            # agent.run() completed

    # Model interaction
    BEFORE_MODEL = "before_model"      # about to call the model
    AFTER_MODEL = "after_model"        # model responded

    # Tool lifecycle
    BEFORE_TOOL = "before_tool"        # about to execute a tool
    AFTER_TOOL = "after_tool"          # tool finished executing

    # Validation
    ON_VALIDATION_ERROR = "on_validation_error"  # tool call failed validation
    ON_RETRY = "on_retry"              # retrying after validation failure

    # Circuit breaker
    ON_LOOP = "on_loop"                # loop detected
    ON_MAX_ITER = "on_max_iter"        # max iterations reached
    ON_TIMEOUT = "on_timeout"          # timeout hit

    # Errors
    ON_ERROR = "on_error"              # any error during execution

    # Memory
    MEMORY_LOAD = "memory_load"        # memory loaded from disk
    MEMORY_SAVE = "memory_save"        # memory saved to disk
    MEMORY_UPDATE = "memory_update"    # memory key updated


@dataclass
class HookContext:
    """Data passed to hook callbacks."""
    event: HookEvent
    agent: Any = None

    # Run context
    user_input: str = ""
    response: str = ""
    iteration: int = 0
    elapsed_ms: float = 0

    # Tool context
    tool_name: str = ""
    args: dict = field(default_factory=dict)
    result: Any = None

    # Validation context
    errors: list[str] = field(default_factory=list)
    schema: dict = field(default_factory=dict)
    retry_count: int = 0

    # Error context
    error: Exception | None = None

    # Memory context
    memory_key: str = ""
    memory_value: Any = None

    # Model context
    messages: list = field(default_factory=list)
    model_response: str = ""

    # Mutable — hooks can modify this to alter behavior
    skip: bool = False  # set True in before_tool to skip execution
    override_response: str | None = None  # set to override final response


class HookRegistry:
    """Manages hook registration and dispatch."""

    def __init__(self):
        self._hooks: dict[HookEvent, list[Callable]] = {
            event: [] for event in HookEvent
        }

    def register(self, event: HookEvent | str, callback: Callable):
        """Register a callback for an event."""
        if isinstance(event, str):
            event = HookEvent(event)
        self._hooks[event].append(callback)

    def unregister(self, event: HookEvent | str, callback: Callable):
        """Remove a callback."""
        if isinstance(event, str):
            event = HookEvent(event)
        self._hooks[event] = [
            cb for cb in self._hooks[event] if cb is not callback
        ]

    def dispatch(self, ctx: HookContext) -> HookContext:
        """Fire all callbacks for an event. Returns the (possibly modified) context."""
        for callback in self._hooks.get(ctx.event, []):
            try:
                callback(ctx)
            except Exception:
                pass  # hooks should never crash the agent
        return ctx

    def has_hooks(self, event: HookEvent) -> bool:
        return len(self._hooks.get(event, [])) > 0


# ── Convenience: pre-built hook functions ──────────────────────

def log_hook(verbose: bool = True) -> Callable:
    """Pre-built hook that logs all events to stdout."""
    def _log(ctx: HookContext):
        if ctx.event == HookEvent.BEFORE_RUN:
            print(f"\n{'='*50}")
            print(f"  Agent run: {ctx.user_input[:60]}")
            print(f"{'='*50}")
        elif ctx.event == HookEvent.BEFORE_TOOL:
            print(f"  → Calling {ctx.tool_name}({ctx.args})")
        elif ctx.event == HookEvent.AFTER_TOOL:
            status = "✓" if ctx.result and ctx.result.success else "✗"
            print(f"  {status} {ctx.tool_name} returned")
            if verbose and ctx.result:
                print(f"    {ctx.result.to_message()[:100]}")
        elif ctx.event == HookEvent.ON_VALIDATION_ERROR:
            print(f"  ⚠ Validation failed: {ctx.errors}")
        elif ctx.event == HookEvent.ON_LOOP:
            print(f"  ⛔ Loop detected on {ctx.tool_name}")
        elif ctx.event == HookEvent.ON_ERROR:
            print(f"  ✗ Error: {ctx.error}")
        elif ctx.event == HookEvent.AFTER_RUN:
            print(f"  ✓ Done ({ctx.elapsed_ms:.0f}ms)")
            print(f"{'='*50}\n")
    return _log


def cost_hook() -> tuple[Callable, Callable]:
    """
    Pre-built hook that tracks tool call counts and timing.
    Returns (hook_fn, get_stats_fn).

    Usage:
        track, stats = cost_hook()
        agent.on("before_tool", track)
        agent.on("after_tool", track)
        agent.run("...")
        print(stats())
    """
    state = {"calls": 0, "tools": {}, "errors": 0}

    def _track(ctx: HookContext):
        if ctx.event == HookEvent.BEFORE_TOOL:
            state["calls"] += 1
            state["tools"].setdefault(ctx.tool_name, 0)
            state["tools"][ctx.tool_name] += 1
        elif ctx.event == HookEvent.ON_ERROR:
            state["errors"] += 1

    def _stats():
        return dict(state)

    return _track, _stats
