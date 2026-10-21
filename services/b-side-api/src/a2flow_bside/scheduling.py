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

# 计算层保留一次、周期与 cron 规则, HTTP 当前开放范围由路由另行约束。
_RULE_TYPES = frozenset({"once", "period", "cron"})
_PERIOD_STEPS = frozenset({"15m", "1h", "1d", "1w"})
_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
# 短周期按固定时长推进, 日周规则按目标时区的本地日历计算。
_STEP_DELTAS = {
    "15m": dt.timedelta(minutes=15),
    "1h": dt.timedelta(hours=1),
    "1d": dt.timedelta(days=1),
    "1w": dt.timedelta(weeks=1),
}
# 历史窗口推进设防御上限, 异常规则不能造成无限循环。
_MAX_ADVANCES = 1_000_000


class ScheduleRuleError(ValueError):
    """Invalid schedule rule configuration."""


@dataclasses.dataclass(frozen=True)
# 冻结规则及创建锚点, 保证相同输入得到确定的下一触发时间。
class ScheduleRule:
    rule_type: str
    rule_json: dict
    timezone: str
    anchor: dt.datetime  # tz-aware creation time

    # 构造时检查规则类型、结构、具体表达式及合法时区。
    def __post_init__(self):
        if self.rule_type not in _RULE_TYPES:
            raise ScheduleRuleError("INVALID_RULE_TYPE")
        if not isinstance(self.rule_json, dict):
            raise ScheduleRuleError("INVALID_RULE_JSON")
        # 一次规则要求 ISO 时间; 缺少时区的时间在计算时按计划时区解释。
        if self.rule_type == "once":
            at = self.rule_json.get("at")
            if not isinstance(at, str):
                raise ScheduleRuleError("ONCE_REQUIRES_AT")
            # 只接受可解析日期, 不在校验失败时猜测默认触发点。
            try:
                dt.datetime.fromisoformat(at)
            except ValueError:
                raise ScheduleRuleError("INVALID_ONCE_AT") from None
        # cron 限定为五段数字表达式, 再交成熟库校验各字段范围。
        elif self.rule_type == "cron":
            expression = self.rule_json.get("expression")
            if not isinstance(expression, str) or len(expression.split()) != 5:
                raise ScheduleRuleError("CRON_REQUIRES_FIVE_FIELDS")
            # 禁止额外命名语法, 避免不同实现对表达式含义理解不一致。
            if any(re.fullmatch(r"[0-9*,/\-]+", field) is None for field in expression.split()):
                raise ScheduleRuleError("CRON_REQUIRES_NUMERIC_FIELDS")
            if not croniter.is_valid(expression):
                raise ScheduleRuleError("INVALID_CRON_EXPRESSION")
        # 周期只能从固定集合中选择, 不能从请求动态构造任意时间跨度。
        else:
            every = self.rule_json.get("every")
            if every not in _PERIOD_STEPS:
                raise ScheduleRuleError("INVALID_PERIOD_STEP")
        # 可选的日历时刻严格使用 HH:MM, 避免非法时分溢出。
        if self.rule_type == "period":
            at = self.rule_json.get("at")
            if at is not None and (
                not isinstance(at, str) or not _HHMM.match(at)
            ):
                raise ScheduleRuleError("INVALID_AT_TIME")
        # 时区必须能由系统时区数据库识别, 锚点本身也必须携带时区。
        if not isinstance(self.timezone, str):
            raise ScheduleRuleError("INVALID_TIMEZONE")
        try:
            ZoneInfo(self.timezone)
        except Exception:
            raise ScheduleRuleError("INVALID_TIMEZONE") from None
        if self.anchor.tzinfo is None:
            raise ScheduleRuleError("ANCHOR_REQUIRES_TIMEZONE")

    # 每次按明确计划时区构建对象, 不依赖服务器本地时区。
    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    # 显式时刻优先, 否则保留创建锚点在目标时区的钟表时间。
    def _at_time(self) -> dt.time:
        at = self.rule_json.get("at")
        if at is not None:
            hour, minute = _HHMM.match(at).groups()
            return dt.time(int(hour), int(minute))
        return self.anchor.astimezone(self.zone).timetz().replace(
            tzinfo=None, microsecond=0
        )


# 规则构造统一经过不可变模型校验, 计算入口不绕过校验。
def parse_rule(
    rule_type: str, rule_json: dict, timezone: str, anchor: dt.datetime
) -> ScheduleRule:
    return ScheduleRule(rule_type, rule_json, timezone, anchor)


def _next_period_candidate(rule: ScheduleRule, after: dt.datetime) -> dt.datetime:
    # cron 在计划时区求下一匹配, 搜索范围有界, 返回值转换为 UTC。
    if rule.rule_type == "cron":
        return croniter(rule.rule_json["expression"], after.astimezone(rule.zone),
                        max_years_between_matches=8).get_next(dt.datetime).astimezone(dt.timezone.utc)
    if rule.rule_type != "period":
        raise ScheduleRuleError("NOT_A_PERIOD_RULE")
    # 日周计算先转本地日期, 短周期仍直接累加固定时长。
    every = rule.rule_json["every"]
    zone = rule.zone
    local = after.astimezone(zone)
    if every in {"15m", "1h"}:
        return after + _STEP_DELTAS[every]
    # 日规则取今天的目标时刻, 已过去则推进一天。
    at = rule._at_time()
    candidate = dt.datetime.combine(local.date(), at, tzinfo=zone)
    if candidate <= after:
        candidate += dt.timedelta(days=1)
    # 周规则保持创建时所在星期几, 不随最近执行时间漂移。
    if every == "1w":
        anchor_weekday = rule.anchor.astimezone(zone).weekday()
        delta = (anchor_weekday - candidate.weekday()) % 7
        if delta == 0 and candidate <= after:
            delta = 7
        candidate += dt.timedelta(days=delta)
        # 确保计算结果严格晚于基准时刻, 避免重复触发同一窗口。
        while candidate <= after:  # safety; normally a single pass suffices
            candidate += dt.timedelta(weeks=1)
    return candidate


# 返回严格未来的触发点, 一次计划已经过期时返回空值。
def next_run_after(rule: ScheduleRule, after: dt.datetime) -> dt.datetime | None:
    if rule.rule_type == "once":
        at = dt.datetime.fromisoformat(rule.rule_json["at"])
        if at.tzinfo is None:
            at = at.replace(tzinfo=rule.zone)
        return at if at > after else None
    return _next_period_candidate(rule, after)


# 错过的窗口只计数并跳过, 不补跑历史业务操作。
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
    # 从上次计划点向未来推进, 保持规则原有节奏。
    candidate = _next_period_candidate(rule, last)
    skipped = 0
    # 逐个跳过已错过窗口, 过多推进直接报告规则溢出。
    while candidate <= now:
        candidate = _next_period_candidate(rule, candidate)
        skipped += 1
        if skipped > _MAX_ADVANCES:  # defensive: pathological rules
            raise ScheduleRuleError("RULE_ADVANCE_OVERFLOW")
    return candidate, skipped
