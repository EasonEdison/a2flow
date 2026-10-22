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

    def test_constructor_requires_running_loop(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "no running event loop"):
            ChatWake()

    def test_thread_burst_posts_only_one_unexecuted_callback(self) -> None:
        async def case() -> None:
            loop = asyncio.get_running_loop()
            assert isinstance(loop, RecordingLoop)
            wake = ChatWake()
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

    def test_close_is_terminal_and_idempotent(self) -> None:
        async def case() -> None:
            wake = ChatWake()
            wake.close()
            wake.close()
            wake.notify()
            with self.assertRaisesRegex(RuntimeError, "CHAT_WAKE_CLOSED"):
                wake.clear()
            with self.assertRaisesRegex(RuntimeError, "CHAT_WAKE_CLOSED"):
                await wake.wait()

        self.run_async(case)

    def test_close_releases_waiter_and_closed_loop_notify_is_safe(self) -> None:
        created: list[ChatWake] = []

        async def first() -> None:
            wake = ChatWake()
            created.append(wake)
            waiter = asyncio.create_task(wake.wait())
            await self.assert_waiting(waiter)
            closer = threading.Thread(target=wake.close)
            closer.start()
            closer.join(2)
            self.assertFalse(closer.is_alive())
            await asyncio.wait_for(waiter, 1)
            wake.close()

        self.run_async(first)
        notify_burst(created[0], 100)

        async def leave_loop_closed() -> None:
            created.append(ChatWake())

        self.run_async(leave_loop_closed)
        created[1].notify()  # RuntimeError from closed-loop posting is isolated.
        created[1].close()

    def test_close_with_paused_poster_never_signals_a_fresh_object(self) -> None:
        async def case() -> None:
            loop = asyncio.get_running_loop()
            assert isinstance(loop, RecordingLoop)
            old = ChatWake()
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
        async def case() -> None:
            wake = ChatWake()

            def foreign_loop() -> None:
                async def wrong_owner() -> None:
                    with self.assertRaisesRegex(RuntimeError, "CHAT_WAKE_WRONG_LOOP"):
                        wake.clear()
                    with self.assertRaisesRegex(RuntimeError, "CHAT_WAKE_WRONG_LOOP"):
                        await wake.wait()

                asyncio.run(wrong_owner())

            failures: list[BaseException] = []
            thread = threading.Thread(target=capture_thread_failure, args=(failures, foreign_loop))
            thread.start()
            thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual([], failures)
            wake.close()

        self.run_async(case)

    def test_independent_event_loops_own_independent_signals(self) -> None:
        ready, observed = threading.Event(), threading.Event()
        created: list[ChatWake] = []
        failures: list[BaseException] = []

        def other_loop() -> None:
            async def own_signal() -> None:
                wake = ChatWake()
                created.append(wake)
                ready.set()
                try:
                    await asyncio.wait_for(wake.wait(), 2)
                    observed.set()
                finally:
                    wake.close()

            asyncio.run(own_signal())

        async def case() -> None:
            owner = threading.Thread(target=capture_thread_failure, args=(failures, other_loop))
            owner.start()
            self.assertTrue(await asyncio.to_thread(ready.wait, 1))
            current = ChatWake()
            waiter = asyncio.create_task(current.wait())
            try:
                created[0].notify()
                self.assertTrue(await asyncio.to_thread(observed.wait, 1))
                await self.assert_waiting(waiter)
                current.notify()
                await asyncio.wait_for(waiter, 1)
            finally:
                current.close()
                owner.join(2)
            self.assertFalse(owner.is_alive())
            self.assertEqual([], failures)

        self.run_async(case)
