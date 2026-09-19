import datetime as dt
import unittest

from a2flow_bside import scheduling


UTC = dt.timezone.utc
SH = "Asia/Shanghai"
ANCHOR = dt.datetime(2026, 9, 19, 8, 0, tzinfo=UTC)


class OnceRuleTests(unittest.TestCase):
    def test_future_once_returns_at(self):
        rule = scheduling.parse_rule(
            "once", {"at": "2026-09-20T10:00:00+08:00"}, SH, ANCHOR
        )
        self.assertEqual(
            dt.datetime(2026, 9, 20, 2, 0, tzinfo=UTC),
            scheduling.next_run_after(
                rule, dt.datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
            ),
        )

    def test_past_once_is_consumed(self):
        rule = scheduling.parse_rule(
            "once", {"at": "2026-09-18T10:00:00+08:00"}, SH, ANCHOR
        )
        self.assertIsNone(
            scheduling.next_run_after(
                rule, dt.datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
            )
        )
        self.assertEqual(
            (None, 1),
            scheduling.advance_from(
                rule, ANCHOR, dt.datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
            ),
        )


class MinuteHourPeriodTests(unittest.TestCase):
    def test_quarter_hour_step(self):
        rule = scheduling.parse_rule("period", {"every": "15m"}, SH, ANCHOR)
        after = dt.datetime(2026, 9, 19, 10, 3, tzinfo=UTC)
        self.assertEqual(
            dt.datetime(2026, 9, 19, 10, 18, tzinfo=UTC),
            scheduling.next_run_after(rule, after),
        )

    def test_hourly_step(self):
        rule = scheduling.parse_rule("period", {"every": "1h"}, SH, ANCHOR)
        after = dt.datetime(2026, 9, 19, 10, 59, tzinfo=UTC)
        self.assertEqual(
            dt.datetime(2026, 9, 19, 11, 59, tzinfo=UTC),
            scheduling.next_run_after(rule, after),
        )

    def test_advance_counts_missed_minute_windows(self):
        rule = scheduling.parse_rule("period", {"every": "15m"}, SH, ANCHOR)
        now = dt.datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
        nxt, skipped = scheduling.advance_from(rule, ANCHOR, now)
        self.assertGreater(nxt, now)
        self.assertGreater(skipped, 0)
        self.assertEqual(
            dt.timedelta(minutes=15) * (skipped + 1), nxt - ANCHOR
        )


class DailyWeeklyPeriodTests(unittest.TestCase):
    def test_daily_at_time_next_day_when_passed(self):
        rule = scheduling.parse_rule(
            "period", {"every": "1d", "at": "09:30"}, SH, ANCHOR
        )
        after = dt.datetime(2026, 9, 19, 2, 30, tzinfo=UTC)  # 10:30 local
        nxt = scheduling.next_run_after(rule, after)
        self.assertEqual(
            dt.datetime(2026, 9, 20, 1, 30, tzinfo=UTC), nxt  # 09:30 +08:00
        )

    def test_daily_skips_missed_days(self):
        rule = scheduling.parse_rule(
            "period", {"every": "1d", "at": "09:30"}, SH, ANCHOR
        )
        now = dt.datetime(2026, 9, 22, 2, 0, tzinfo=UTC)
        nxt, skipped = scheduling.advance_from(
            rule, dt.datetime(2026, 9, 19, 1, 0, tzinfo=UTC), now
        )
        self.assertEqual(
            dt.datetime(2026, 9, 23, 1, 30, tzinfo=UTC), nxt
        )
        self.assertGreaterEqual(skipped, 3)

    def test_weekly_keeps_anchor_weekday(self):
        # 2026-09-19 is a Saturday; anchor weekday = 5
        rule = scheduling.parse_rule(
            "period", {"every": "1w", "at": "09:00"}, SH, ANCHOR
        )
        after = dt.datetime(2026, 9, 19, 10, 0, tzinfo=UTC)  # 18:00 Sat local
        nxt = scheduling.next_run_after(rule, after)
        self.assertEqual(5, nxt.astimezone(rule.zone).weekday())
        self.assertGreater(nxt, after)


class ValidationTests(unittest.TestCase):
    def test_invalid_rule_types_rejected(self):
        for kwargs in (
            {"rule_type": "cron", "rule_json": {}, "timezone": SH},
            {"rule_type": "period", "rule_json": {"every": "2d"}, "timezone": SH},
            {"rule_type": "period", "rule_json": {"every": "1d", "at": "25:00"}, "timezone": SH},
            {"rule_type": "once", "rule_json": {}, "timezone": SH},
            {"rule_type": "once", "rule_json": {"at": "x"}, "timezone": SH},
            {"rule_type": "period", "rule_json": {"every": "1d"}, "timezone": "Mars/Olympus"},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(scheduling.ScheduleRuleError):
                    scheduling.parse_rule(anchor=ANCHOR, **kwargs)

    def test_anchor_requires_timezone(self):
        with self.assertRaises(scheduling.ScheduleRuleError):
            scheduling.parse_rule(
                "period",
                {"every": "1d"},
                SH,
                dt.datetime(2026, 9, 19, 8, 0),  # naive
            )


if __name__ == "__main__":
    unittest.main()
