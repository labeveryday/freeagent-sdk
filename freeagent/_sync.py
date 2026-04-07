"""
Sync bridge — run async code from synchronous callers.

Uses a single persistent background event loop that stays alive for
the lifetime of the process. This prevents httpx connection pool issues
that occur when asyncio.run() creates/destroys loops on each call.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Coroutine, TypeVar

T = TypeVar("T")


class _SyncBridge:
    """
    Run async coroutines from sync code on a persistent background loop.

    The loop is created once and reused for all calls. This is critical
    for httpx AsyncClient — if the loop closes between calls, the client's
    connection pool becomes invalid.
    """

    _loop: asyncio.AbstractEventLoop | None = None
    _thread: threading.Thread | None = None
    _lock = threading.Lock()

    @classmethod
    def run(cls, coro: Coroutine[Any, Any, T]) -> T:
        """Run an async coroutine and return its result synchronously."""
        cls._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(coro, cls._loop)
        return future.result()

    @classmethod
    def _ensure_loop(cls):
        """Create the background loop + thread if not already running."""
        with cls._lock:
            if cls._loop is None or cls._loop.is_closed():
                cls._loop = asyncio.new_event_loop()
                cls._thread = threading.Thread(
                    target=cls._loop.run_forever,
                    daemon=True,
                    name="freeagent-sync-bridge",
                )
                cls._thread.start()
