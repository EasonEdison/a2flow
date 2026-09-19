import json
import unittest

from agent_workflow_runtime.events import DomainEvent
from agent_workflow_runtime.event_sink_postgres import (
    PostgresEventSink,
    QUEUE_DOMAIN_EVENTS,
)


class FakeResult:
    def fetchall(self):
        return []


class FakeConnection:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return FakeResult()


class PostgresEventSinkTests(unittest.TestCase):
    def test_publish_inserts_envelope_with_event_dedup(self):
        connection = FakeConnection()
        sink = PostgresEventSink(connection)
        event = DomainEvent.create(
            "RUN_FINISHED", "run-1", "wf/demo", "u1", "PRT",
            payload={"nodeId": "n1"},
        )
        sink.publish(event)
        self.assertEqual(1, len(connection.calls))
        sql, params = connection.calls[0]
        self.assertIn("INSERT INTO queue_items", sql)
        self.assertIn("ON CONFLICT (dedup_key) DO NOTHING", sql)
        self.assertEqual(QUEUE_DOMAIN_EVENTS, params[0])
        payload = json.loads(params[1])
        self.assertEqual("run-1", payload["run_id"])
        self.assertEqual("wf/demo", payload["workflow_key"])
        self.assertEqual("u1", payload["user_id"])
        self.assertEqual("PRT", payload["environment"])
        self.assertEqual({"nodeId": "n1"}, payload["payload"])
        self.assertEqual(str(event.event_id), params[2])
        self.assertEqual(str(event.event_id), payload["event_id"])

    def test_rejects_non_events(self):
        sink = PostgresEventSink(FakeConnection())
        with self.assertRaises(TypeError):
            sink.publish({"event_type": "x"})


if __name__ == "__main__":
    unittest.main()
