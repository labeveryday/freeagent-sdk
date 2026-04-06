"""
Sync bridge — run async code from synchronous callers safely.

Handles the tricky cases:
- No running loop → just use asyncio.run()
- Already in an async context (Jupyter, nested calls) → use a background thread

This replaces the fragile asyncio.run() / ThreadPoolExecutor pattern.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Coroutine, TypeVar

T = TypeVar("T")


class _SyncBridge:
    """
    Run async coroutines from sync code without conflicting with
    an existing event loop.
    """

    _loop: asyncio.AbstractEventLoop | None = None
    _thread: threading.Thread | None = None
    _lock = threading.Lock()

    @classmethod
    def run(cls, coro: Coroutine[Any, Any, T]) -> T:
        """
        Run an async coroutine and return its result synchronously.

        If no event loop is running, uses asyncio.run() directly.
        If an event loop is already running (e.g. Jupyter), schedules
        the coroutine on a background thread's loop.
        """
        try:
            asyncio.get_running_loop()
            # We're inside an async context — use the background loop
            return cls._run_in_background(coro)
        except RuntimeError:
            # No running loop — safe to use asyncio.run()
            return asyncio.run(coro)

    @classmethod
    def _run_in_background(cls, coro: Coroutine[Any, Any, T]) -> T:
        """Schedule on a dedicated background event loop thread."""
        with cls._lock:
            if cls._loop is None or cls._loop.is_closed():
                cls._loop = asyncio.new_event_loop()
                cls._thread = threading.Thread(
                    target=cls._loop.run_forever,
                    daemon=True,
                    name="freeagent-sync-bridge",
                )
                cls._thread.start()

        future = asyncio.run_coroutine_threadsafe(coro, cls._loop)
        return future.result()
