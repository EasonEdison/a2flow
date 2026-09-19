import datetime as dt
import unittest

from a2flow_scheduler import workers

UTC = dt.timezone.utc


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class FakeDB:
    def __init__(self, rows_by_index=None):
        self.rows_by_index = rows_by_index or {}
        self.calls = []
        self._index = 0

    def execute(self, sql, params=None):
        index = self._index
        self._index += 1
        self.calls.append((sql, params))
        return FakeResult(self.rows_by_index.get(index, []))


class FakeQueue:
    def __init__(self):
        self.items = []

    def enqueue(self, queue, payload, *, dedup_key=None):
        self.items.append((queue, payload, dedup_key))


class FakeLark:
    def __init__(self):
        self.sends = []

    def send(self, card, *, dedup_key=None):
        self.sends.append((card, dedup_key))


class FakeHttp:
    def __init__(self):
        self.posts = []

    def post(self, path, *, json):
        self.posts.append((path, json))
        return {"ok": True}


def event(event_type, **overrides):
    value = {
        "event_id": "evt-1",
        "event_type": event_type,
        "run_id": "run-1",
        "user_id": "u1",
        "workflow_key": "wf/demo",
        "environment": "PRT",
        "occurred_at": "2026-09-19T10:00:00+00:00",
        "payload": {"node_title": "选择方案"},
    }
    value.update(overrides)
    return value


class HandleDomainEventTests(unittest.TestCase):
    def test_waiting_event_upserts_and_notifies(self):
        db = FakeDB(rows_by_index={1: [(0,)]})
        lark = FakeLark()
        workers.handle_domain_event(
            event("NODE_WAITING"), db=db, lark=lark,
            notifications=__import__("a2flow_scheduler.notifications", fromlist=["x"]),
        )

    def test_unresolved_owner_requeues(self):
        db = FakeDB()
        with self.assertRaises(workers.OwnerNotResolved):
            workers.handle_domain_event(
                event("NODE_WAITING"), db=db, lark=None,
                notifications=__import__("a2flow_scheduler.notifications", fromlist=["x"]),
                owner_resolver=lambda run_id: None,
            )

    def test_resolved_owner_receives_notification(self):
        db = FakeDB(rows_by_index={1: [(0,)]})
        workers.handle_domain_event(
            event("NODE_WAITING"), db=db, lark=None,
            notifications=__import__("a2flow_scheduler.notifications", fromlist=["x"]),
            owner_resolver=lambda run_id: "u-real-owner",
        )
        self.assertEqual("u-real-owner", db.calls[2][1][0])

    def test_terminal_event_clears_wait_and_notifies(self):
        db = FakeDB(rows_by_index={1: [(0,)]})
        lark = FakeLark()
        workers.handle_domain_event(
            event("RUN_FINISHED"), db=db, lark=lark,
            notifications=__import__("a2flow_scheduler.notifications", fromlist=["x"]),
        )
        self.assertIn("DELETE FROM run_wait_states", db.calls[0][0])
        self.assertEqual("finished", db.calls[2][1][1])

    def test_start_event_produces_nothing(self):
        db = FakeDB()
        workers.handle_domain_event(
            event("RUN_STARTED"), db=db, lark=FakeLark(),
            notifications=__import__("a2flow_scheduler.notifications", fromlist=["x"]),
        )
        self.assertEqual(0, len(db.calls))

    def test_cap_exceeded_merges(self):
        db = FakeDB(rows_by_index={1: [(20,)]})
        lark = FakeLark()
        workers.handle_domain_event(
            event("NODE_WAITING"), db=db, lark=lark,
            notifications=__import__("a2flow_scheduler.notifications", fromlist=["x"]),
        )
        self.assertEqual("system", db.calls[2][1][1])
        self.assertTrue(lark.sends[0][1].startswith("cap:u1:"))


class TriggerDueSchedulesTests(unittest.TestCase):
    def test_due_period_schedule_advances_enqueues_and_records_skips(self):
        row = (
            1, "u1", "wf/demo", "PRT", "period",
            {"every": "15m"}, "Asia/Shanghai", "输入文本",
            dt.datetime(2026, 9, 19, 9, 0, tzinfo=UTC),
            dt.datetime(2026, 9, 19, 9, 0, tzinfo=UTC),
        )
        db = FakeDB(rows_by_index={0: [row]})
        queue = FakeQueue()
        now = dt.datetime(2026, 9, 19, 10, 5, tzinfo=UTC)
        fired = workers.trigger_due_schedules(
            db=db, queue=queue, now=now,
            notifications=__import__("a2flow_scheduler.notifications", fromlist=["x"]),
        )
        self.assertEqual(1, fired)
        advance_params = db.calls[1][1]
        self.assertEqual(dt.datetime(2026, 9, 19, 10, 15, tzinfo=UTC), advance_params[0])
        self.assertTrue(advance_params[2])  # stays enabled
        self.assertEqual(1, len(queue.items))
        queue_name, payload, dedup = queue.items[0]
        self.assertEqual("run_workflow", queue_name)
        self.assertEqual("u1", payload["user_id"])
        self.assertEqual("输入文本", payload["input"])
        self.assertTrue(dedup.startswith("run:1:"))
        self.assertIn("错过 4 个执行窗口", db.calls[2][1][3])
        self.assertEqual("错过了执行窗口", db.calls[2][1][2])

    def test_consumed_once_disables(self):
        row = (
            2, "u1", "wf/demo", "PRT", "once",
            {"at": "2026-09-19T09:30:00+00:00"}, "Asia/Shanghai", "输入",
            dt.datetime(2026, 9, 19, 9, 30, tzinfo=UTC),
            dt.datetime(2026, 9, 19, 9, 0, tzinfo=UTC),
        )
        db = FakeDB(rows_by_index={0: [row]})
        queue = FakeQueue()
        fired = workers.trigger_due_schedules(
            db=db, queue=queue,
            now=dt.datetime(2026, 9, 19, 10, 0, tzinfo=UTC),
            notifications=__import__("a2flow_scheduler.notifications", fromlist=["x"]),
        )
        self.assertEqual(1, fired)
        self.assertIsNone(db.calls[1][1][0])
        self.assertFalse(db.calls[1][1][2])  # disabled after consumption


class WaitTimeoutTests(unittest.TestCase):
    def test_overdue_waits_are_stopped_and_notified(self):
        row = ("run-9", "u1", "wf/demo")
        db = FakeDB(rows_by_index={0: [row]})
        http = FakeHttp()
        stopped = workers.monitor_wait_timeouts(
            db=db, http=http, timeout_hours=24,
            now=dt.datetime(2026, 9, 20, 12, 0, tzinfo=UTC),
        )
        self.assertEqual(1, stopped)
        self.assertEqual("/api/runs/run-9/stop", http.posts[0][0])
        self.assertIn("已自动停止", db.calls[1][1][2])
        self.assertIn("DELETE FROM run_wait_states", db.calls[2][0])


if __name__ == "__main__":
    unittest.main()
