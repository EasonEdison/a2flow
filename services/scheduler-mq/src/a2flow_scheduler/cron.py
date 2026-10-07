"""Five-field cron calculation in an explicit IANA timezone."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from croniter import croniter


@dataclass(frozen=True)
class CronSchedule:
    expression: str
    timezone: str

    def __post_init__(self) -> None:
        fields = self.expression.split()
        if len(fields) != 5 or any(re.fullmatch(r"[0-9*,/\-]+", field) is None for field in fields):
            raise ValueError("CRON_REQUIRES_FIVE_NUMERIC_FIELDS")
        if not croniter.is_valid(self.expression):
            raise ValueError("INVALID_CRON_EXPRESSION")
        ZoneInfo(self.timezone)

    def next_after(self, instant: datetime) -> datetime:
        if instant.utcoffset() is None:
            raise ValueError("CRON_REQUIRES_AWARE_DATETIME")
        iterator = croniter(
            self.expression,
            instant.astimezone(ZoneInfo(self.timezone)),
            max_years_between_matches=8,
        )
        result = iterator.get_next(datetime).astimezone(UTC)
        if result <= instant:
            raise ValueError("CRON_DID_NOT_ADVANCE")
        return result
