import contextlib
import datetime as dt
import unittest

from a2flow_bside.queue import QueueItem
from a2flow_scheduler import loops

UTC = dt.timezone.utc


class FakeDB:
    def __init__(self, rows_by_index=None):
        self.rows_by_index = rows_by_index or {}
        self.calls = []
        self._index = 0

    def execute(self, sql, params=None):
        index = self._index
        self._index += 1
        self.calls.append((sql, params))
        rows = self.rows_by_index.get(index, [])
        return FakeResult(rows)

    @contextlib.contextmanager
    def transaction(self):
        yield self


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class FakeQueue:
    def __init__(self, items=()):
        self.items = list(items)
        self.enqueued = []
        self.completed = []
        self.requeued = []

    def enqueue(self, queue, payload, *, dedup_key=None):
        self.enqueued.append((queue, payload, dedup_key))

    def claim(self, queue, limit=10, lease_seconds=120):
        return self.items[:limit]

    def complete(self, item_id):
        self.completed.append(item_id)

    def requeue_failed(self, item_id):
        self.requeued.append(item_id)


class FakeHttp:
    def __init__(self, fail_paths=()):
        self.posts = []
        self.fail_paths = set(fail_paths)

    def post(self, path, *, json):
        self.posts.append((path, json))
        if path in self.fail_paths:
            raise OSError("http down")
        return {"ok": True}


class FakeLark:
    def __init__(self):
        self.sends = []

    def send(self, card, *, dedup_key=None):
        self.sends.append((card, dedup_key))


def wait_event(event_id="evt-1", run_id="run-1"):
    return {
        "event_id": event_id,
        "event_type": "NODE_WAITING",
        "run_id": run_id,
        "user_id": "u1",
        "workflow_key": "wf/demo",
        "environment": "PRT",
        "occurred_at": "2026-09-19T10:00:00+00:00",
        "payload": {"node_title": "选择方案"},
    }


class TriggerIterationTests(unittest.TestCase):
    def test_takes_advisory_lock_then_claims(self):
        row = (
            1, "u1", "wf/demo", "PRT", "period", {"every": "15m"},
            "Asia/Shanghai", "输入",
            dt.datetime(2026, 9, 19, 9, 0, tzinfo=UTC),
            dt.datetime(2026, 9, 19, 9, 0, tzinfo=UTC),
        )
        db = FakeDB(rows_by_index={1: [row]})
        queue = FakeQueue()
        fired = loops.run_trigger_iteration(
            conn=db, queue=queue,
            now=dt.datetime(2026, 9, 19, 10, 5, tzinfo=UTC),
        )
        self.assertEqual(1, fired)
        self.assertIn("pg_advisory_xact_lock", db.calls[0][0])
        self.assertEqual(1, len(queue.enqueued))


class RunWorkflowConsumerTests(unittest.TestCase):
    def test_success_completes(self):
        queue = FakeQueue(
            items=[
                QueueItem(
                    item_id=1, queue="run_workflow",
                    payload={"workflow_key": "wf/demo", "input": "hi",
                             "user_id": "u1"}, attempts=1,
                )
            ]
        )
        http = FakeHttp()
        processed = loops.run_workflow_consumer_iteration(
            conn=FakeDB(), queue=queue, http=http
        )
        self.assertEqual(1, processed)
        self.assertEqual("/api/runs", http.posts[0][0])
        self.assertEqual("wf/demo", http.posts[0][1]["workflowKey"])
        self.assertEqual([1], queue.completed)

    def test_http_failure_requeues(self):
        queue = FakeQueue(
            items=[
                QueueItem(
                    item_id=2, queue="run_workflow",
                    payload={"workflow_key": "wf/demo"}, attempts=1,
                )
            ]
        )
        http = FakeHttp(fail_paths={"/api/runs"})
        processed = loops.run_workflow_consumer_iteration(
            conn=FakeDB(), queue=queue, http=http
        )
        self.assertEqual(0, processed)
        self.assertEqual([2], queue.requeued)


class EventConsumerTests(unittest.TestCase):
    def test_waiting_event_completes_and_notifies(self):
        queue = FakeQueue(items=[QueueItem(
            item_id=3, queue="domain_events",
            payload=wait_event(), attempts=1,
        )])
        db = FakeDB(rows_by_index={1: [("u1",)], 2: [(0,)]})
        processed = loops.run_event_consumer_iteration(
            conn=db, queue=queue, lark=FakeLark()
        )
        self.assertEqual(1, processed)
        self.assertEqual([3], queue.completed)
        self.assertIn("run_wait_states", db.calls[0][0])

    def test_bad_event_requeues(self):
        queue = FakeQueue(items=[QueueItem(
            item_id=4, queue="domain_events",
            payload={"event_type": "NODE_WAITING"}, attempts=1,  # missing ts
        )])
        db = FakeDB()
        processed = loops.run_event_consumer_iteration(
            conn=db, queue=queue, lark=FakeLark()
        )
        self.assertEqual(0, processed)
        self.assertEqual([4], queue.requeued)


class MonitorIterationTests(unittest.TestCase):
    def test_overdue_run_stopped(self):
        db = FakeDB(rows_by_index={0: [("run-9", "u1", "wf/demo")]})
        http = FakeHttp()
        stopped = loops.run_monitor_iteration(conn=db, http=http)
        self.assertEqual(1, stopped)


if __name__ == "__main__":
    unittest.main()
