"""Real asyncio/thread races for the process-local dispatcher wake hint."""

from __future__ import annotations

import asyncio
import contextvars
import threading
import unittest
from collections.abc import Callable, Coroutine
from typing import Any

from a2flow_bside.chat_wake import ChatWake


class RecordingLoop(asyncio.SelectorEventLoop):
    """Count actual scheduled callbacks; optional latch models a delayed poster."""

    def __init__(self) -> None:
        super().__init__()
        self.wake_posts = 0
        self.post_lock = threading.Lock()
        self.pause_next_post: tuple[threading.Event, threading.Event] | None = None

    def call_soon_threadsafe(
        self,
        callback: Callable[..., object],
        *args: object,
        context: contextvars.Context | None = None,
    ) -> asyncio.Handle:
        pause = None
        if (
            isinstance(getattr(callback, "__self__", None), ChatWake)
            and getattr(callback, "__name__", None) == "_deliver"
        ):
            with self.post_lock:
                self.wake_posts += 1
                pause, self.pause_next_post = self.pause_next_post, None
        if pause is not None:
            entered, release = pause
            entered.set()
            if not release.wait(2):
                raise AssertionError("delayed notification poster was not released")
        return super().call_soon_threadsafe(callback, *args, context=context)


def notify_burst(wake: ChatWake, count: int) -> None:
    for _ in range(count):
        wake.notify()


def notify_after_release(release: threading.Event, wake: ChatWake) -> None:
    if not release.wait(2):
        raise AssertionError("notification thread was not released")
    wake.notify()


def capture_thread_failure(failures: list[BaseException], action: Callable[[], None]) -> None:
    try:
        action()
    except BaseException as error:
        failures.append(error)


class ChatWakeTests(unittest.TestCase):
    def run_async(self, case: Callable[[], Coroutine[Any, Any, None]]) -> None:
        with asyncio.Runner(loop_factory=RecordingLoop) as runner:
            runner.run(case())

    def assert_no_wait_tasks(self) -> None:
        children = [
            task
            for task in asyncio.all_tasks()
            if task.get_name() in {"chat-wake-signal", "chat-wake-stop"}
        ]
        self.assertEqual([], children)

    def test_unbound_and_prebind_notifications_are_safe(self) -> None:
        wake = ChatWake()
        initial = wake.snapshot()
        for _ in range(10):
            wake.notify()
        self.assertEqual(initial + 10, wake.snapshot())

        async def case() -> None:
            wake.bind()
            await asyncio.wait_for(wake.wait_after(initial, 10, asyncio.Event()), 0.1)
            self.assert_no_wait_tasks()
            wake.close()
            wake.notify()

        self.run_async(case)

    def test_thread_burst_has_one_outstanding_callback(self) -> None:
        async def case() -> None:
            loop = asyncio.get_running_loop()
            assert isinstance(loop, RecordingLoop)
            wake = ChatWake()
            wake.bind()
            initial = wake.snapshot()
            threads = [threading.Thread(target=notify_burst, args=(wake, 2000)) for _ in range(8)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(2)
                self.assertFalse(thread.is_alive())
            # The event loop has not run a callback during these joins.
            self.assertEqual(1, loop.wake_posts)
            self.assertEqual(initial + 16000, wake.snapshot())
            await wake.wait_after(initial, 10, asyncio.Event())
            await asyncio.sleep(0)
            for _ in range(100):
                wake.notify()
            self.assertEqual(1, loop.wake_posts)  # Already signalled, no queue growth.
            wake.close()
            self.assert_no_wait_tasks()

        self.run_async(case)

    def test_notify_during_drain_is_not_lost_before_wait(self) -> None:
        async def case() -> None:
            wake = ChatWake()
            wake.bind()
            before_drain = wake.snapshot()
            thread = threading.Thread(target=wake.notify)
            thread.start()
            thread.join(2)
            self.assertFalse(thread.is_alive())
            await asyncio.wait_for(wake.wait_after(before_drain, 10, asyncio.Event()), 0.1)
            self.assert_no_wait_tasks()
            wake.close()

        self.run_async(case)

    def test_notify_after_clear_before_event_wait_starts(self) -> None:
        async def case() -> None:
            wake = ChatWake()
            wake.bind()
            stop = asyncio.Event()
            for _ in range(100):
                release = threading.Event()
                thread = threading.Thread(target=notify_after_release, args=(release, wake))
                thread.start()
                # This callback runs after wait_after clears/arms and before its
                # newly created event-wait child has its first loop turn.
                asyncio.get_running_loop().call_soon(release.set)
                try:
                    await asyncio.wait_for(wake.wait_after(wake.snapshot(), 1, stop), 2)
                finally:
                    release.set()
                    thread.join(2)
                self.assertFalse(thread.is_alive())
                self.assert_no_wait_tasks()
            wake.close()

        self.run_async(case)

    def test_pending_callback_and_rearm_still_coalesce(self) -> None:
        async def case() -> None:
            loop = asyncio.get_running_loop()
            assert isinstance(loop, RecordingLoop)
            wake = ChatWake()
            wake.bind()
            entered, release = threading.Event(), threading.Event()
            loop.pause_next_post = (entered, release)
            first = threading.Thread(target=wake.notify)
            first.start()
            self.assertTrue(entered.wait(1))
            # First notify advanced the counter but has not posted its actual
            # callback yet. Rearm clears dirty while that callback is pending.
            waiter = asyncio.create_task(wake.wait_after(wake.snapshot(), 1, asyncio.Event()))
            await asyncio.sleep(0)
            second = threading.Thread(target=wake.notify)
            try:
                second.start()
                second.join(1)
                self.assertFalse(second.is_alive())
                self.assertEqual(1, loop.wake_posts)
            finally:
                release.set()
                first.join(2)
            await asyncio.wait_for(waiter, 2)
            self.assert_no_wait_tasks()
            wake.close()

        self.run_async(case)

    def test_timeout_stop_and_cancel_observe_all_child_tasks(self) -> None:
        async def case() -> None:
            wake = ChatWake()
            wake.bind()
            stop = asyncio.Event()
            await wake.wait_after(wake.snapshot(), 0.001, stop)
            self.assert_no_wait_tasks()
            for timeout in (0,):
                await wake.wait_after(wake.snapshot(), timeout, stop)
                self.assert_no_wait_tasks()
            waiter = asyncio.create_task(wake.wait_after(wake.snapshot(), 10, stop))
            await asyncio.sleep(0)
            stop.set()
            await asyncio.wait_for(waiter, 1)
            self.assert_no_wait_tasks()
            stop.clear()
            waiter = asyncio.create_task(wake.wait_after(wake.snapshot(), 10, stop))
            await asyncio.sleep(0)
            waiter.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await waiter
            self.assert_no_wait_tasks()
            for invalid in (-1, float("inf"), float("nan")):
                with self.assertRaisesRegex(ValueError, "CHAT_WAKE_TIMEOUT_INVALID"):
                    await wake.wait_after(wake.snapshot(), invalid, stop)
            wake.close()

        self.run_async(case)

    def test_close_releases_waiter_and_repeated_close_is_terminal(self) -> None:
        wake = ChatWake()

        async def case() -> None:
            wake.bind()
            waiter = asyncio.create_task(wake.wait_after(wake.snapshot(), 10, asyncio.Event()))
            await asyncio.sleep(0)
            failures: list[BaseException] = []
            thread = threading.Thread(target=capture_thread_failure, args=(failures, wake.close))
            thread.start()
            thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual([], failures)
            await asyncio.wait_for(waiter, 1)
            self.assert_no_wait_tasks()
            frozen = wake.snapshot()
            wake.close()
            wake.close()
            wake.notify()
            self.assertEqual(frozen, wake.snapshot())
            with self.assertRaisesRegex(RuntimeError, "CHAT_WAKE_CLOSED"):
                wake.bind()

        self.run_async(case)
        frozen = wake.snapshot()
        wake.notify()
        wake.close()
        self.assertEqual(frozen, wake.snapshot())

    def test_delayed_callback_after_close_cannot_signal_a_replacement_object(self) -> None:
        async def case() -> None:
            loop = asyncio.get_running_loop()
            assert isinstance(loop, RecordingLoop)
            wake = ChatWake()
            wake.bind()
            entered, release = threading.Event(), threading.Event()
            loop.pause_next_post = (entered, release)
            failures: list[BaseException] = []
            old_poster = threading.Thread(
                target=capture_thread_failure, args=(failures, wake.notify)
            )
            old_poster.start()
            self.assertTrue(entered.wait(1))
            wake.close()
            frozen = wake.snapshot()
            with self.assertRaisesRegex(RuntimeError, "CHAT_WAKE_CLOSED"):
                wake.bind()
            replacement = ChatWake()
            replacement.bind()
            waiter = asyncio.create_task(
                replacement.wait_after(replacement.snapshot(), 10, asyncio.Event())
            )
            await asyncio.sleep(0)
            try:
                release.set()
                old_poster.join(2)
                self.assertFalse(old_poster.is_alive())
                self.assertEqual([], failures)
                await asyncio.sleep(0)
                await asyncio.sleep(0)
                self.assertFalse(waiter.done())
                for _ in range(100):
                    wake.notify()
                self.assertEqual(frozen, wake.snapshot())
                replacement.notify()
                await asyncio.wait_for(waiter, 1)
            finally:
                release.set()
                old_poster.join(2)
                wake.close()
                replacement.close()
            self.assert_no_wait_tasks()

        self.run_async(case)

    def test_zero_timeout_does_not_consume_a_simultaneous_hint(self) -> None:
        async def case() -> None:
            loop = asyncio.get_running_loop()
            assert isinstance(loop, RecordingLoop)
            wake = ChatWake()
            wake.bind()
            stop = asyncio.Event()
            wake.notify()
            await asyncio.sleep(0)
            version = wake.snapshot()
            await wake.wait_after(version, 0, stop)
            wake.notify()
            self.assertEqual(1, loop.wake_posts)
            await asyncio.wait_for(wake.wait_after(version, 10, stop), 0.1)
            self.assert_no_wait_tasks()
            wake.close()

        self.run_async(case)

    def test_wait_requires_current_loop_binding(self) -> None:
        async def case() -> None:
            wake = ChatWake()
            with self.assertRaisesRegex(RuntimeError, "CHAT_WAKE_NOT_BOUND"):
                await wake.wait_after(0, 1, asyncio.Event())
            wake.bind()
            wake.close()
            with self.assertRaisesRegex(RuntimeError, "CHAT_WAKE_NOT_BOUND"):
                await wake.wait_after(0, 1, asyncio.Event())

        self.run_async(case)

    def test_duplicate_bind_on_same_loop_preserves_existing_waiter(self) -> None:
        async def case() -> None:
            wake = ChatWake()
            wake.bind()
            waiter = asyncio.create_task(wake.wait_after(wake.snapshot(), 10, asyncio.Event()))
            await asyncio.sleep(0)
            with self.assertRaisesRegex(RuntimeError, "CHAT_WAKE_ALREADY_BOUND"):
                wake.bind()
            wake.notify()
            await asyncio.wait_for(waiter, 1)
            self.assert_no_wait_tasks()
            wake.close()

        self.run_async(case)

    def test_close_before_bind_is_terminal_and_freezes_prebind_hints(self) -> None:
        wake = ChatWake()
        wake.notify()
        frozen = wake.snapshot()
        wake.close()
        wake.close()
        failures: list[BaseException] = []
        threads = [
            threading.Thread(
                target=capture_thread_failure, args=(failures, lambda: notify_burst(wake, 1000))
            )
            for _ in range(4)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(2)
            self.assertFalse(thread.is_alive())
        self.assertEqual([], failures)
        self.assertEqual(frozen, wake.snapshot())

        async def case() -> None:
            with self.assertRaisesRegex(RuntimeError, "CHAT_WAKE_CLOSED"):
                wake.bind()
            with self.assertRaisesRegex(RuntimeError, "CHAT_WAKE_NOT_BOUND"):
                await wake.wait_after(frozen, 1, asyncio.Event())
            self.assert_no_wait_tasks()

        self.run_async(case)

    def test_closed_loop_cannot_be_rebound_but_a_fresh_object_can_bind(self) -> None:
        wake = ChatWake()

        async def first() -> None:
            wake.bind()

        self.run_async(first)
        before = wake.snapshot()
        # A loop may stop before its owner closes; the late hint must remain safe.
        failures: list[BaseException] = []
        thread = threading.Thread(target=capture_thread_failure, args=(failures, wake.notify))
        thread.start()
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual([], failures)
        self.assertEqual(before + 1, wake.snapshot())

        async def second() -> None:
            with self.assertRaisesRegex(RuntimeError, "CHAT_WAKE_ALREADY_BOUND"):
                wake.bind()
            wake.close()
            frozen = wake.snapshot()
            wake.notify()
            self.assertEqual(frozen, wake.snapshot())
            with self.assertRaisesRegex(RuntimeError, "CHAT_WAKE_CLOSED"):
                wake.bind()
            replacement = ChatWake()
            replacement.bind()
            version = replacement.snapshot()
            waiter = asyncio.create_task(replacement.wait_after(version, 10, asyncio.Event()))
            await asyncio.sleep(0)
            replacement.notify()
            await asyncio.wait_for(waiter, 1)
            self.assert_no_wait_tasks()
            replacement.close()

        self.run_async(second)

    def test_notify_poster_racing_close_and_loop_shutdown_is_safe(self) -> None:
        wake = ChatWake()
        entered, release = threading.Event(), threading.Event()
        failures: list[BaseException] = []
        thread = threading.Thread(target=capture_thread_failure, args=(failures, wake.notify))

        async def case() -> None:
            loop = asyncio.get_running_loop()
            assert isinstance(loop, RecordingLoop)
            wake.bind()
            loop.pause_next_post = (entered, release)
            thread.start()
            self.assertTrue(entered.wait(1))
            wake.close()
            self.assert_no_wait_tasks()

        try:
            self.run_async(case)
            frozen = wake.snapshot()
        finally:
            # Release only after Runner has actually closed the target loop.
            release.set()
            thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual([], failures)
        wake.notify()
        wake.close()
        self.assertEqual(frozen, wake.snapshot())
