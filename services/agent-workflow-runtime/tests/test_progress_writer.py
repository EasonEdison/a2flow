"""Bounded observer failure tests; in-memory test port is not PostgreSQL proof."""

from threading import Event, Thread
from time import monotonic
import unittest

from agent_workflow_runtime.progress_writer import ProgressWriter, text_parts, encoded
from support import context


class Store:
    def __init__(self, *, blocked=False, fail=False):
        self.entered, self.release = Event(), Event()
        self.calls, self.health = [], []
        self.fail = fail
        if not blocked:
            self.release.set()

    def append(self, binding, batch, records, **state):
        self.entered.set()
        if not self.release.wait(2):
            raise TimeoutError("test store")
        if self.fail:
            raise RuntimeError("display storage unavailable")
        self.calls.append((binding, batch, records, state))

    def unavailable(self, binding):
        self.health.append(binding)


class ProgressWriterTest(unittest.TestCase):
    def records(self, store):
        return [record for _, _, records, _ in store.calls for record in records]

    def test_utf8_split_preserves_every_character(self):
        value = "中文🙂" * 4000
        parts = list(text_parts(value))
        self.assertEqual(value, "".join(parts))
        self.assertTrue(all(len(part.encode()) <= 8192 for part in parts))

    def test_adjacent_text_coalesces_and_capture_seals(self):
        store = Store()
        writer = ProgressWriter(store).start()
        with writer.capture(context()) as scope:
            scope.emit("TEXT_DELTA", {"modelCallId": "m", "text": "中"})
            scope.emit("TEXT_DELTA", {"modelCallId": "m", "text": "文🙂"})
        self.assertTrue(writer.shutdown())
        records = self.records(store)
        self.assertEqual(["中文🙂"], [r["payload"]["text"] for r in records])
        self.assertEqual("RETURNED", store.calls[-1][3]["seal"])
        self.assertFalse(store.calls[-1][3]["incomplete"])
        self.assertEqual((0, 0, {}), (writer._bytes, writer._entries, writer._segments))

    def test_text_quota_keeps_reserved_gap_and_seal(self):
        store = Store()
        writer = ProgressWriter(store, max_text=3).start()
        with writer.capture(context()) as scope:
            scope.emit("TEXT_DELTA", {"modelCallId": "m", "text": "中"})
            scope.emit("TEXT_DELTA", {"modelCallId": "m", "text": "文"})
        self.assertTrue(writer.shutdown())
        records = self.records(store)
        self.assertEqual(["TEXT_DELTA", "CAPTURE_INCOMPLETE"], [r["kind"] for r in records])
        self.assertEqual("DISPLAY_LIMIT", records[-1]["payload"]["code"])
        self.assertTrue(store.calls[-1][3]["incomplete"])

    def test_entry_quota_includes_inflight_batch_and_reserved_health(self):
        store = Store(blocked=True)
        writer = ProgressWriter(store, queue_entries=3).start()
        try:
            with writer.capture(context()) as scope:
                scope.emit("MODEL_STARTED", {"modelCallId": "m"})
                self.assertTrue(store.entered.wait(1))
                scope.emit("MODEL_RETURNED", {"modelCallId": "m"})
                self.assertTrue(scope.unavailable)
                self.assertLessEqual(writer._entries, 3)
            store.release.set()
            self.assertTrue(writer.shutdown())
            self.assertIn("QUEUE_LIMIT", [r["payload"].get("code") for r in self.records(store)])
            self.assertEqual(0, writer._entries)
        finally:
            store.release.set()
            writer.shutdown()

    def test_byte_quota_independent_of_entry_quota(self):
        store = Store()
        writer = ProgressWriter(store, queue_bytes=2200).start()
        with writer.capture(context()) as scope:
            scope.emit("TEXT_DELTA", {"modelCallId": "m", "text": "x" * 1000})
            self.assertTrue(scope.unavailable)
            self.assertLessEqual(writer._bytes, 2200)
        self.assertTrue(writer.shutdown())
        self.assertEqual(["CAPTURE_INCOMPLETE"], [r["kind"] for r in self.records(store)])
        self.assertEqual("QUEUE_LIMIT", self.records(store)[0]["payload"]["code"])

    def test_record_quota_reserves_one_gap(self):
        store = Store()
        writer = ProgressWriter(store, max_records=2).start()
        with writer.capture(context()) as scope:
            scope.emit("MODEL_STARTED", {"modelCallId": "m"})
            scope.emit("MODEL_RETURNED", {"modelCallId": "m"})
        self.assertTrue(writer.shutdown())
        self.assertEqual(2, len(self.records(store)))
        self.assertEqual("RECORD_LIMIT", self.records(store)[-1]["payload"]["code"])

    def test_write_failure_marks_health_without_business_exception(self):
        store = Store(fail=True)
        writer = ProgressWriter(store).start()
        with writer.capture(context()) as scope:
            scope.emit("MODEL_STARTED", {"modelCallId": "m"})
            business_result = "success"
        self.assertTrue(writer.shutdown())
        self.assertEqual("success", business_result)
        self.assertTrue(scope.unavailable)
        self.assertEqual(1, len(store.health))
        self.assertEqual((0, 0), (writer._bytes, writer._entries))

    def test_finite_drain_with_blocked_store_and_no_false_seal(self):
        store = Store(blocked=True)
        writer = ProgressWriter(store).start()
        try:
            with writer.capture(context()) as scope:
                scope.emit("MODEL_STARTED", {"modelCallId": "m"})
                self.assertTrue(store.entered.wait(1))
            started = monotonic()
            self.assertFalse(writer.shutdown(.05))
            self.assertLess(monotonic() - started, .5)
            store.release.set()
            self.assertTrue(writer.shutdown())
        finally:
            store.release.set()
            writer.shutdown()

    def test_invalid_display_payload_cannot_escape_to_records(self):
        store = Store()
        writer = ProgressWriter(store).start()
        with writer.capture(context()) as scope:
            scope.emit("MODEL_STARTED", {"modelCallId": "m", "raw": "PRIVATE"})
            self.assertTrue(scope.unavailable)
        self.assertTrue(writer.shutdown())
        self.assertNotIn(b"PRIVATE", encoded(self.records(store)))
        self.assertEqual("CAPTURE_UNAVAILABLE", self.records(store)[0]["payload"]["code"])

    def test_capture_without_observed_operations_has_no_invented_head(self):
        store = Store()
        writer = ProgressWriter(store).start()
        with writer.capture(context()):
            pass
        self.assertTrue(writer.shutdown())
        self.assertEqual([], store.calls)

    def test_failed_segment_cannot_be_recreated_by_already_admitted_emitter(self):
        entered, resume, removed, idle = Event(), Event(), Event(), Event()
        class FailOnceStore(Store):
            attempts = 0
            def append(self, *args, **kwargs):
                self.attempts += 1
                return super().append(*args, **kwargs)
        store = FailOnceStore(blocked=True, fail=True)
        writer = ProgressWriter(store).start()
        release_segment = writer._release
        def release_and_signal(segment):
            release_segment(segment)
            removed.set()
        writer._release = release_and_signal
        condition_wait = writer._condition.wait
        def wait_until_notified(timeout=None):
            if store.attempts and not writer._segments and writer._entries == 0:
                idle.set()
                return condition_wait()  # No timer wakeup competing with resumed offer.
            return condition_wait(timeout)
        writer._condition.wait = wait_until_notified
        class DelayedSink:
            def offer(self, scope, kind, payload):
                entered.set()  # ProgressScope.emit has already checked unavailable.
                if not resume.wait(2):
                    raise AssertionError("test emitter was not resumed")
                writer.offer(scope, kind, payload)
        emitter = None
        try:
            with writer.capture(context()) as scope:
                scope.emit("MODEL_STARTED", {"modelCallId": "m"})
                self.assertTrue(store.entered.wait(1))
                scope.sink = DelayedSink()
                emitter = Thread(target=scope.emit, args=(
                    "MODEL_RETURNED", {"modelCallId": "m"}))
                emitter.start()
                self.assertTrue(entered.wait(1))
                store.release.set()  # First append fails; health update has no head.
                self.assertTrue(removed.wait(1))
                self.assertTrue(idle.wait(1))
                with writer._condition:
                    pass  # Worker has entered its wait and released the queue lock.
                self.assertTrue(scope.unavailable)
                self.assertNotIn(scope.execution_id, writer._segments)
                store.fail = False  # A wrongly reopened segment would now persist.
                resume.set()
                emitter.join(1)
                self.assertFalse(emitter.is_alive())
            self.assertTrue(writer.shutdown())
            self.assertEqual(1, store.attempts)
            self.assertEqual([], store.calls)  # No new append or seal after failed capture.
            self.assertEqual(1, len(store.health))
            self.assertEqual((0, 0, {}), (writer._bytes, writer._entries, writer._segments))
        finally:
            resume.set()
            store.release.set()
            if emitter is not None:
                emitter.join(1)
            writer.shutdown()
