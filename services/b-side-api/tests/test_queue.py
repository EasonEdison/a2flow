import json
import unittest

from a2flow_bside import queue as queue_module


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class FakeConnection:
    """Records (sql, params) per call and returns canned rows by call index."""

    def __init__(self, rows_by_index=None):
        self.rows_by_index = rows_by_index or {}
        self.calls = []
        self._index = 0

    def execute(self, sql, params=None):
        index = self._index
        self._index += 1
        self.calls.append((sql, params))
        return FakeResult(self.rows_by_index.get(index, []))


class PostgresQueueClientTests(unittest.TestCase):
    def test_enqueue_builds_insert_with_dedup(self):
        connection = FakeConnection()
        client = queue_module.PostgresQueueClient(connection)
        client.enqueue(
            "run_workflow", {"run": 1}, dedup_key="schedule-1:2026-09-19"
        )
        sql, params = connection.calls[0]
        self.assertIn("INSERT INTO queue_items", sql)
        self.assertIn("ON CONFLICT (dedup_key) DO NOTHING", sql)
        self.assertEqual("run_workflow", params[0])
        self.assertEqual({"run": 1}, json.loads(params[1]))
        self.assertEqual("schedule-1:2026-09-19", params[2])

    def test_enqueue_rejects_invalid_inputs(self):
        client = queue_module.PostgresQueueClient(FakeConnection())
        with self.assertRaises(queue_module.QueueError):
            client.enqueue("", {"a": 1})
        with self.assertRaises(queue_module.QueueError):
            client.enqueue("q", {"a": 1}, dedup_key="")

    def test_claim_maps_rows_and_guards_lease(self):
        connection = FakeConnection(
            rows_by_index={0: [(7, "run_workflow", {"k": "v"}, 1)]}
        )
        client = queue_module.PostgresQueueClient(connection)
        items = client.claim("run_workflow", limit=5, lease_seconds=90)
        sql, params = connection.calls[0]
        self.assertIn("FOR UPDATE SKIP LOCKED", sql)
        self.assertEqual(("run_workflow", 5, 90), params)
        self.assertEqual(1, len(items))
        item = items[0]
        self.assertEqual(7, item.item_id)
        self.assertEqual("run_workflow", item.queue)
        self.assertEqual({"k": "v"}, item.payload)
        self.assertEqual(1, item.attempts)

    def test_claim_rejects_bad_arguments(self):
        client = queue_module.PostgresQueueClient(FakeConnection())
        with self.assertRaises(queue_module.QueueError):
            client.claim("q", limit=0)
        with self.assertRaises(queue_module.QueueError):
            client.claim("q", lease_seconds=0)

    def test_complete_extend_requeue_guard_state(self):
        connection = FakeConnection()
        client = queue_module.PostgresQueueClient(connection)
        client.complete(3)
        client.extend(3, 300)
        client.requeue_failed(3)
        self.assertIn("state = 'done'", connection.calls[0][0])
        self.assertIn("WHERE id = %s AND state = 'claimed'", connection.calls[0][0])
        self.assertIn("make_interval", connection.calls[1][0])
        self.assertIn("state = 'pending'", connection.calls[2][0])


if __name__ == "__main__":
    unittest.main()
