"""A process-local, coalescing hint for the durable Chat dispatcher.

Only the database authorizes execution. A missed hint, including one before
bind(), is covered by startup and periodic reconciliation. This port owns no
background task, database connection, per-request queue or execution state.
"""

from __future__ import annotations

import asyncio
import math
import threading
from contextlib import suppress


class ChatWake:
    """Thread-safe monotonic notifications with at most one queued callback.

    The counter closes drain/clear/wait races. Dirty and callback-pending are
    separate: clearing an event cannot enqueue another callback while an older
    callback is still waiting to run. Each binding has a unique identity, so an
    old loop's delayed callback cannot signal or clear a newer binding.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._version = 0
        self._loop: asyncio.AbstractEventLoop | None = None
        self._event: asyncio.Event | None = None
        self._binding: object | None = None
        self._dirty = False
        self._callback_pending = False

    def bind(self) -> None:
        """Bind during dispatcher startup, followed by an unconditional scan."""
        loop = asyncio.get_running_loop()
        with self._lock:
            if self._loop is loop:
                return
            if self._loop is not None:
                raise RuntimeError("CHAT_WAKE_ALREADY_BOUND")
            self._loop = loop
            self._event = asyncio.Event()
            self._binding = object()
            self._dirty = False
            self._callback_pending = False

    def snapshot(self) -> int:
        """Take a counter before draining durable facts, not after the drain."""
        with self._lock:
            return self._version

    def notify(self) -> None:
        """Hint only after commit; safe in worker threads or while unbound."""
        with self._lock:
            self._version += 1
            loop, binding = self._loop, self._binding
            if loop is None or binding is None or self._dirty:
                return
            self._dirty = True
            if self._callback_pending:
                return
            self._callback_pending = True
        try:
            loop.call_soon_threadsafe(self._deliver, binding)
        except RuntimeError:
            # Loop shutdown can race scheduling. Facts remain durable and the
            # version still advances; never touch a replacement loop's flags.
            with self._lock:
                if self._binding is binding:
                    self._dirty = False
                    self._callback_pending = False

    def _deliver(self, binding: object) -> None:
        with self._lock:
            if self._binding is not binding:
                return
            self._callback_pending = False
            if self._dirty and self._event is not None:
                self._event.set()

    async def wait_after(self, version: int, timeout: float, stop: asyncio.Event) -> None:
        """Wait for a newer hint, a deadline or stop without owning child tasks.

        Check the counter and clear the level-triggered signal under the same
        lock used by notify(). A notify after this check either wakes the event
        or is already covered by an outstanding coalesced callback.
        """
        if not math.isfinite(timeout) or timeout < 0:
            raise ValueError("CHAT_WAKE_TIMEOUT_INVALID")
        loop = asyncio.get_running_loop()
        with self._lock:
            if self._loop is not loop or self._event is None:
                raise RuntimeError("CHAT_WAKE_NOT_BOUND")
            if self._version != version or stop.is_set() or timeout == 0:
                return
            event = self._event
            event.clear()
            self._dirty = False
        signal_wait = asyncio.create_task(event.wait(), name="chat-wake-signal")
        stop_wait = asyncio.create_task(stop.wait(), name="chat-wake-stop")
        tasks = (signal_wait, stop_wait)
        try:
            done, _ = await asyncio.wait(
                tasks, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
            )
            for task in done:
                task.result()
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    def close(self) -> None:
        """Unbind; wake existing waiters without notifying any future binding."""
        with self._lock:
            loop, event = self._loop, self._event
            self._loop, self._event, self._binding = None, None, None
            self._dirty = False
            self._callback_pending = False
        if loop is not None and event is not None:
            # An already closed loop has no live waiters to wake. This callback
            # captures the old event, never self._event or a future binding.
            with suppress(RuntimeError):
                loop.call_soon_threadsafe(event.set)
