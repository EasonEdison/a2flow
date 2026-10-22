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

    async def assert_waiting(self, task: asyncio.Task[None]) -> None:
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        self.assertFalse(task.done())

    def test_new_notifications_are_noop_and_startup_reads_committed_facts(self) -> None:
        wake = ChatWake()
        committed = ["accepted-before-startup"]
        notify_burst(wake, 100)

        async def case() -> None:
            loop = asyncio.get_running_loop()
            assert isinstance(loop, RecordingLoop)
            wake.bind()
            wake.clear()
            self.assertEqual(["accepted-before-startup"], list(committed))
            self.assertEqual(0, loop.wake_posts)
            waiter = asyncio.create_task(wake.wait())
            await self.assert_waiting(waiter)
            waiter.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await waiter
            wake.close()

        self.run_async(case)

    def test_thread_burst_posts_only_one_unexecuted_callback(self) -> None:
        async def case() -> None:
            loop = asyncio.get_running_loop()
            assert isinstance(loop, RecordingLoop)
            wake = ChatWake()
            wake.bind()
            wake.clear()
            failures: list[BaseException] = []
            threads = [
                threading.Thread(
                    target=capture_thread_failure, args=(failures, lambda: notify_burst(wake, 2000))
                )
                for _ in range(8)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(2)
                self.assertFalse(thread.is_alive())
            self.assertEqual([], failures)
            self.assertEqual(1, loop.wake_posts)
            await asyncio.wait_for(wake.wait(), 1)
            later = threading.Thread(
                target=capture_thread_failure, args=(failures, lambda: notify_burst(wake, 100))
            )
            later.start()
            later.join(2)
            self.assertFalse(later.is_alive())
            self.assertEqual([], failures)
            # Already-set signals can post one more callback; no Event method
            # is read from producer threads and concurrent posting stays bounded.
            self.assertEqual(2, loop.wake_posts)
            await asyncio.wait_for(wake.wait(), 1)  # Waiting never consumes the level.
            wake.close()

        self.run_async(case)

    def test_delivered_hint_before_clear_is_covered_by_following_drain(self) -> None:
        async def case() -> None:
            wake = ChatWake()
            wake.bind()
            facts: list[str] = []

            def commit() -> None:
                facts.append("committed")
                wake.notify()

            producer = threading.Thread(target=commit)
            producer.start()
            producer.join(2)
            self.assertFalse(producer.is_alive())
            await asyncio.wait_for(wake.wait(), 1)
            wake.clear()  # Legal order: clear, then read durable facts.
            self.assertEqual(["committed"], list(facts))
            waiter = asyncio.create_task(wake.wait())
            await self.assert_waiting(waiter)
            waiter.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await waiter
            wake.close()

        self.run_async(case)

    def test_hint_during_fact_query_survives_until_wait(self) -> None:
        async def case() -> None:
            wake = ChatWake()
            wake.bind()
            facts: list[str] = []
            query_started, query_release = threading.Event(), threading.Event()

            def read_facts() -> list[str]:
                result = list(facts)
                query_started.set()
                if not query_release.wait(2):
                    raise AssertionError("query was not released")
                return result

            wake.clear()
            query = asyncio.create_task(asyncio.to_thread(read_facts))
            self.assertTrue(await asyncio.to_thread(query_started.wait, 1))

            def commit() -> None:
                facts.append("committed-after-query-snapshot")
                wake.notify()
                query_release.set()

            producer = threading.Thread(target=commit)
            producer.start()
            try:
                self.assertEqual([], await query)
                await asyncio.wait_for(wake.wait(), 1)
                self.assertEqual(["committed-after-query-snapshot"], facts)
            finally:
                query_release.set()
                producer.join(2)
                wake.close()
            self.assertFalse(producer.is_alive())

        self.run_async(case)

    def test_notify_after_clear_before_wait_interleaving(self) -> None:
        async def case() -> None:
            wake = ChatWake()
            wake.bind()
            failures: list[BaseException] = []
            for _ in range(100):
                wake.clear()
                release = threading.Event()
                thread = threading.Thread(
                    target=capture_thread_failure,
                    args=(failures, lambda release=release: notify_after_release(release, wake)),
                )
                thread.start()
                asyncio.get_running_loop().call_soon(release.set)
                try:
                    await asyncio.wait_for(wake.wait(), 1)
                finally:
                    release.set()
                    thread.join(2)
                self.assertFalse(thread.is_alive())
            self.assertEqual([], failures)
            wake.close()

        self.run_async(case)

    def test_clear_never_releases_a_paused_notification_callback_gate(self) -> None:
        async def case() -> None:
            loop = asyncio.get_running_loop()
            assert isinstance(loop, RecordingLoop)
            wake = ChatWake()
            wake.bind()
            entered, release = threading.Event(), threading.Event()
            failures: list[BaseException] = []
            loop.pause_next_post = (entered, release)
            first = threading.Thread(target=capture_thread_failure, args=(failures, wake.notify))
            first.start()
            self.assertTrue(entered.wait(1))
            try:
                for _ in range(100):
                    wake.clear()
                second = threading.Thread(
                    target=capture_thread_failure, args=(failures, lambda: notify_burst(wake, 1000))
                )
                second.start()
                second.join(2)
                self.assertFalse(second.is_alive())
                self.assertEqual(1, loop.wake_posts)
            finally:
                release.set()
                first.join(2)
            await asyncio.wait_for(wake.wait(), 1)
            self.assertEqual([], failures)
            self.assertFalse(first.is_alive())
            wake.close()

        self.run_async(case)

    def test_timeout_and_cancel_use_event_waiter_cleanup(self) -> None:
        async def case() -> None:
            wake = ChatWake()
            wake.bind()
            wake.clear()
            before = asyncio.all_tasks()
            with self.assertRaises(asyncio.TimeoutError):
                await asyncio.wait_for(wake.wait(), 0.001)
            self.assertEqual(before, asyncio.all_tasks())
            waiter = asyncio.create_task(wake.wait())
            await self.assert_waiting(waiter)
            waiter.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await waiter
            self.assertEqual(before, asyncio.all_tasks())
            wake.notify()
            await asyncio.wait_for(wake.wait(), 1)
            wake.clear()
            # A cancelled/expired waiter does not swallow the next notification.
            wake.notify()
            await asyncio.wait_for(wake.wait(), 1)
            wake.close()

        self.run_async(case)

    def test_duplicate_bind_and_new_close_are_terminal(self) -> None:
        wake = ChatWake()
        wake.close()
        wake.close()
        wake.notify()

        async def case() -> None:
            with self.assertRaisesRegex(RuntimeError, "CHAT_WAKE_CLOSED"):
                wake.bind()
            current = ChatWake()
            current.bind()
            with self.assertRaisesRegex(RuntimeError, "CHAT_WAKE_ALREADY_BOUND"):
                current.bind()
            current.close()
            current.close()
            current.notify()
            with self.assertRaisesRegex(RuntimeError, "CHAT_WAKE_CLOSED"):
                current.bind()

        self.run_async(case)

    def test_close_releases_waiter_and_closed_loop_notify_is_safe(self) -> None:
        wake = ChatWake()

        async def first() -> None:
            wake.bind()
            waiter = asyncio.create_task(wake.wait())
            await self.assert_waiting(waiter)
            closer = threading.Thread(target=wake.close)
            closer.start()
            closer.join(2)
            self.assertFalse(closer.is_alive())
            await asyncio.wait_for(waiter, 1)
            wake.close()

        self.run_async(first)
        notify_burst(wake, 100)
        abandoned = ChatWake()

        async def leave_loop_closed() -> None:
            abandoned.bind()

        self.run_async(leave_loop_closed)
        abandoned.notify()  # RuntimeError from closed-loop posting is isolated.
        abandoned.close()

    def test_close_with_paused_poster_never_signals_a_fresh_object(self) -> None:
        async def case() -> None:
            loop = asyncio.get_running_loop()
            assert isinstance(loop, RecordingLoop)
            old = ChatWake()
            old.bind()
            entered, release = threading.Event(), threading.Event()
            failures: list[BaseException] = []
            loop.pause_next_post = (entered, release)
            old_poster = threading.Thread(
                target=capture_thread_failure, args=(failures, old.notify)
            )
            old_poster.start()
            self.assertTrue(entered.wait(1))
            old.close()
            old.close()
            notify_burst(old, 100)
            self.assertEqual(1, loop.wake_posts)
            fresh = ChatWake()
            fresh.bind()
            fresh.clear()
            waiter = asyncio.create_task(fresh.wait())
            await self.assert_waiting(waiter)
            try:
                release.set()
                old_poster.join(2)
                await self.assert_waiting(waiter)
                fresh.notify()
                await asyncio.wait_for(waiter, 1)
                self.assertEqual([], failures)
                self.assertFalse(old_poster.is_alive())
            finally:
                release.set()
                old_poster.join(2)
                fresh.close()

        self.run_async(case)

    def test_clear_and_wait_require_owner_loop(self) -> None:
        wake = ChatWake()

        async def case() -> None:
            with self.assertRaisesRegex(RuntimeError, "CHAT_WAKE_NOT_BOUND"):
                wake.clear()
            with self.assertRaisesRegex(RuntimeError, "CHAT_WAKE_NOT_BOUND"):
                await wake.wait()
            wake.bind()

            def foreign_loop() -> None:
                async def wrong_owner() -> None:
                    with self.assertRaisesRegex(RuntimeError, "CHAT_WAKE_NOT_BOUND"):
                        wake.clear()
                    with self.assertRaisesRegex(RuntimeError, "CHAT_WAKE_NOT_BOUND"):
                        await wake.wait()

                asyncio.run(wrong_owner())

            failures: list[BaseException] = []
            thread = threading.Thread(target=capture_thread_failure, args=(failures, foreign_loop))
            thread.start()
            thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual([], failures)
            wake.close()
            with self.assertRaisesRegex(RuntimeError, "CHAT_WAKE_NOT_BOUND"):
                wake.clear()
            with self.assertRaisesRegex(RuntimeError, "CHAT_WAKE_NOT_BOUND"):
                await wake.wait()

        self.run_async(case)
