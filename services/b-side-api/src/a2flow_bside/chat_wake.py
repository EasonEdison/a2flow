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
        self._loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
        self._event = asyncio.Event()
        self._lock = threading.Lock()
        self._closed = False
        self._callback_pending = False

    def notify(self) -> None:
        """Hint after commit from any thread; closed objects safely ignore it."""
        with self._lock:
            if self._closed:
                return
            if self._callback_pending:
                return
            self._callback_pending = True
        try:
            self._loop.call_soon_threadsafe(self._deliver)
        except RuntimeError:
            # Shutdown may close the loop before posting; persisted facts survive.
            with self._lock:
                self._callback_pending = False

    def _deliver(self) -> None:
        with self._lock:
            if self._closed:
                return
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
            if self._closed:
                raise RuntimeError("CHAT_WAKE_CLOSED")
            if self._loop is not loop:
                raise RuntimeError("CHAT_WAKE_WRONG_LOOP")
            self._event.clear()

    async def wait(self) -> None:
        """Await the signal without clearing; the dispatcher owns timeout/stop."""
        loop = asyncio.get_running_loop()
        with self._lock:
            if self._closed:
                raise RuntimeError("CHAT_WAKE_CLOSED")
            if self._loop is not loop:
                raise RuntimeError("CHAT_WAKE_WRONG_LOOP")
            event = self._event
        await event.wait()

    def close(self) -> None:
        """Close permanently and release existing waiters; repeated close is a no-op."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._callback_pending = False
        with suppress(RuntimeError):
            self._loop.call_soon_threadsafe(self._event.set)
