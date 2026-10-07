"""Schedule rule computation (pure, timezone-aware, deterministic).

v1 rule kinds:
- once:   {"at": ISO8601}
- period: {"every": "15m"|"1h"|"1d"|"1w", "at": "HH:MM" optional}
  For daily/weekly rules without "at", the schedule creation time's local
  clock is the anchor. Weekly rules keep the creation weekday.

All results are tz-aware datetimes (UTC where inputs were UTC). Missed windows
are counted and skipped (never replayed) per the accepted policy.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import re
from zoneinfo import ZoneInfo
from croniter import croniter

_RULE_TYPES = frozenset({"once", "period", "cron"})
_PERIOD_STEPS = frozenset({"15m", "1h", "1d", "1w"})
_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_STEP_DELTAS = {
    "15m": dt.timedelta(minutes=15),
    "1h": dt.timedelta(hours=1),
    "1d": dt.timedelta(days=1),
    "1w": dt.timedelta(weeks=1),
}
_MAX_ADVANCES = 1_000_000


class ScheduleRuleError(ValueError):
    """Invalid schedule rule configuration."""


@dataclasses.dataclass(frozen=True)
class ScheduleRule:
    rule_type: str
    rule_json: dict
    timezone: str
    anchor: dt.datetime  # tz-aware creation time

    def __post_init__(self):
        if self.rule_type not in _RULE_TYPES:
            raise ScheduleRuleError("INVALID_RULE_TYPE")
        if not isinstance(self.rule_json, dict):
            raise ScheduleRuleError("INVALID_RULE_JSON")
        if self.rule_type == "once":
            at = self.rule_json.get("at")
            if not isinstance(at, str):
                raise ScheduleRuleError("ONCE_REQUIRES_AT")
            try:
                dt.datetime.fromisoformat(at)
            except ValueError:
                raise ScheduleRuleError("INVALID_ONCE_AT") from None
        elif self.rule_type == "cron":
            expression = self.rule_json.get("expression")
            if not isinstance(expression, str) or len(expression.split()) != 5:
                raise ScheduleRuleError("CRON_REQUIRES_FIVE_FIELDS")
            if any(re.fullmatch(r"[0-9*,/\-]+", field) is None for field in expression.split()):
                raise ScheduleRuleError("CRON_REQUIRES_NUMERIC_FIELDS")
            if not croniter.is_valid(expression):
                raise ScheduleRuleError("INVALID_CRON_EXPRESSION")
        else:
            every = self.rule_json.get("every")
            if every not in _PERIOD_STEPS:
                raise ScheduleRuleError("INVALID_PERIOD_STEP")
        if self.rule_type == "period":
            at = self.rule_json.get("at")
            if at is not None and (
                not isinstance(at, str) or not _HHMM.match(at)
            ):
                raise ScheduleRuleError("INVALID_AT_TIME")
        if not isinstance(self.timezone, str):
            raise ScheduleRuleError("INVALID_TIMEZONE")
        try:
            ZoneInfo(self.timezone)
        except Exception:
            raise ScheduleRuleError("INVALID_TIMEZONE") from None
        if self.anchor.tzinfo is None:
            raise ScheduleRuleError("ANCHOR_REQUIRES_TIMEZONE")

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def _at_time(self) -> dt.time:
        at = self.rule_json.get("at")
        if at is not None:
            hour, minute = _HHMM.match(at).groups()
            return dt.time(int(hour), int(minute))
        return self.anchor.astimezone(self.zone).timetz().replace(
            tzinfo=None, microsecond=0
        )


def parse_rule(
    rule_type: str, rule_json: dict, timezone: str, anchor: dt.datetime
) -> ScheduleRule:
    return ScheduleRule(rule_type, rule_json, timezone, anchor)


def _next_period_candidate(rule: ScheduleRule, after: dt.datetime) -> dt.datetime:
    if rule.rule_type == "cron":
        return croniter(rule.rule_json["expression"], after.astimezone(rule.zone),
                        max_years_between_matches=8).get_next(dt.datetime).astimezone(dt.timezone.utc)
    if rule.rule_type != "period":
        raise ScheduleRuleError("NOT_A_PERIOD_RULE")
    every = rule.rule_json["every"]
    zone = rule.zone
    local = after.astimezone(zone)
    if every in {"15m", "1h"}:
        return after + _STEP_DELTAS[every]
    at = rule._at_time()
    candidate = dt.datetime.combine(local.date(), at, tzinfo=zone)
    if candidate <= after:
        candidate += dt.timedelta(days=1)
    if every == "1w":
        anchor_weekday = rule.anchor.astimezone(zone).weekday()
        delta = (anchor_weekday - candidate.weekday()) % 7
        if delta == 0 and candidate <= after:
            delta = 7
        candidate += dt.timedelta(days=delta)
        while candidate <= after:  # safety; normally a single pass suffices
            candidate += dt.timedelta(weeks=1)
    return candidate


def next_run_after(rule: ScheduleRule, after: dt.datetime) -> dt.datetime | None:
    if rule.rule_type == "once":
        at = dt.datetime.fromisoformat(rule.rule_json["at"])
        if at.tzinfo is None:
            at = at.replace(tzinfo=rule.zone)
        return at if at > after else None
    return _next_period_candidate(rule, after)


def advance_from(
    rule: ScheduleRule, last: dt.datetime, now: dt.datetime
) -> tuple[dt.datetime | None, int]:
    """Return (next future run, missed window count) advancing past `now`.

    Missed windows are counted and skipped; a fully consumed one-shot returns
    (None, 1).
    """
    if rule.rule_type == "once":
        at = dt.datetime.fromisoformat(rule.rule_json["at"])
        if at.tzinfo is None:
            at = at.replace(tzinfo=rule.zone)
        return (None, 1) if at <= now else (at, 0)
    candidate = _next_period_candidate(rule, last)
    skipped = 0
    while candidate <= now:
        candidate = _next_period_candidate(rule, candidate)
        skipped += 1
        if skipped > _MAX_ADVANCES:  # defensive: pathological rules
            raise ScheduleRuleError("RULE_ADVANCE_OVERFLOW")
    return candidate, skipped
