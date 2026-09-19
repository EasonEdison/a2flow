import datetime as dt
import unittest

from a2flow_scheduler import notifications

UTC = dt.timezone.utc


def event(event_type, workflow_key="wf/demo", node_title="选择方案"):
    return {
        "event_type": event_type,
        "workflow_key": workflow_key,
        "payload": {"node_title": node_title},
    }


class NotificationPlanTests(unittest.TestCase):
    def test_waiting_maps_with_node_title(self):
        plan = notifications.notification_plan(
            event("NODE_WAITING", workflow_key="wf/a", node_title="确认安排")
        )
        self.assertIsNotNone(plan)
        kind, title, body = plan
        self.assertEqual("waiting", kind)
        self.assertIn("确认安排", body)
        self.assertIn("wf/a", body)

    def test_terminal_events_map(self):
        for event_type, kind in (
            ("RUN_FINISHED", "finished"),
            ("RUN_STOPPED", "stopped"),
            ("RUN_FAILED", "failed"),
        ):
            with self.subTest(event_type=event_type):
                plan = notifications.notification_plan(event(event_type))
                self.assertEqual(kind, plan[0])

    def test_non_notifiable_events_are_none(self):
        for event_type in ("RUN_STARTED", "NODE_UNBLOCKED", "UNKNOWN"):
            with self.subTest(event_type=event_type):
                self.assertIsNone(
                    notifications.notification_plan(event(event_type))
                )

    def test_missing_metadata_uses_fallbacks(self):
        plan = notifications.notification_plan({"event_type": "RUN_FINISHED"})
        self.assertIsNotNone(plan)
        self.assertIn("未知工作流", plan[2])

    def test_waiting_uses_node_id_fallback(self):
        plan = notifications.notification_plan(
            {
                "event_type": "NODE_WAITING",
                "workflow_key": "wf/demo",
                "payload": {"nodeId": "node-test"},
            }
        )
        self.assertIsNotNone(plan)
        self.assertIn("node-test", plan[2])


class RateCapTests(unittest.TestCase):
    def test_hour_bucket_stable_within_hour(self):
        moment = dt.datetime(2026, 9, 19, 14, 30, tzinfo=UTC)
        self.assertEqual(
            notifications.hour_bucket("u1", moment),
            notifications.hour_bucket(
                "u1", dt.datetime(2026, 9, 19, 14, 59, tzinfo=UTC)
            ),
        )
        self.assertNotEqual(
            notifications.hour_bucket("u1", moment),
            notifications.hour_bucket(
                "u1", dt.datetime(2026, 9, 19, 15, 1, tzinfo=UTC)
            ),
        )

    def test_cap_boundary(self):
        self.assertTrue(notifications.within_cap(19))
        self.assertFalse(notifications.within_cap(20))
        self.assertFalse(notifications.within_cap(21))

    def test_cap_exceeded_plan(self):
        moment = dt.datetime(2026, 9, 19, 14, 30, tzinfo=UTC)
        kind, title, body, dedup = notifications.cap_exceeded_plan(
            "u1", moment, overflow_count=7
        )
        self.assertEqual("system", kind)
        self.assertIn("7", body)
        self.assertEqual("cap:u1:2026091914", dedup)


if __name__ == "__main__":
    unittest.main()
