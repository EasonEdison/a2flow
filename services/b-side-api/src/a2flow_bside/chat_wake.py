"""A coalesced process-local hint; durable database facts authorize dispatch.

The owner must clear BEFORE querying durable work, never between its query and
wait. Pre-clear hints are covered by that query; post-clear hints remain set.
This single-lifetime port owns no task, deadline, retry or execution state.
"""

from __future__ import annotations

import asyncio
import threading
from contextlib import suppress


class ChatWake:
    """One level-triggered Event and at most one queued notification callback."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._event: asyncio.Event | None = None
        self._closed = False
        self._callback_pending = False

    def bind(self) -> None:
        """Bind once on the dispatcher loop, before its unconditional first drain."""
        loop = asyncio.get_running_loop()
        with self._lock:
            if self._closed:
                raise RuntimeError("CHAT_WAKE_CLOSED")
            if self._loop is not None:
                raise RuntimeError("CHAT_WAKE_ALREADY_BOUND")
            self._loop = loop
            self._event = asyncio.Event()

    def notify(self) -> None:
        """Hint after commit from any thread; NEW/CLOSED objects safely ignore it."""
        with self._lock:
            loop, event = self._loop, self._event
            if self._closed or loop is None or event is None:
                return
            if self._callback_pending:
                return
            self._callback_pending = True
        try:
            loop.call_soon_threadsafe(self._deliver)
        except RuntimeError:
            # Shutdown may close the loop before posting; persisted facts survive.
            with self._lock:
                self._callback_pending = False

    def _deliver(self) -> None:
        with self._lock:
            if self._closed:
                return
            if self._event is not None:
                self._event.set()
            self._callback_pending = False

    def clear(self) -> None:
        """Owner loop only: clear BEFORE database drain, never after querying.

        Do not release the callback gate: a notifying thread may have reserved
        its callback but not yet posted it. That pending callback still delivers
        a signal after this clear, without queueing additional callbacks.
        """
        loop = asyncio.get_running_loop()
        with self._lock:
            if self._loop is not loop or self._event is None:
                raise RuntimeError("CHAT_WAKE_NOT_BOUND")
            self._event.clear()

    async def wait(self) -> None:
        """Await the signal without clearing; the dispatcher owns timeout/stop."""
        loop = asyncio.get_running_loop()
        with self._lock:
            if self._loop is not loop or self._event is None:
                raise RuntimeError("CHAT_WAKE_NOT_BOUND")
            event = self._event
        await event.wait()

    def close(self) -> None:
        """Close permanently and release existing waiters; repeated close is a no-op."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            loop, event = self._loop, self._event
            self._loop, self._event = None, None
            self._callback_pending = False
        if loop is not None and event is not None:
            with suppress(RuntimeError):
                loop.call_soon_threadsafe(event.set)
