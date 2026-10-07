"""Atomically advance schedules and save typed commands to the durable outbox."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from a2flow_bside.scheduling import advance_from, parse_rule
from pydantic import TypeAdapter

from a2flow_scheduler.contracts import CommandModel, StartWorkflow
from a2flow_scheduler.cron import CronSchedule
from a2flow_scheduler.outbox import PostgresOutbox


class RuleFields(CommandModel):
    at: str | None = None
    every: Literal["15m", "1h", "1d", "1w"] | None = None
    expression: str | None = None


ScheduleRow = tuple[
    int,
    int,
    str,
    Literal["PRT", "ONLINE"],
    Literal["once", "period", "cron"],
    str,
    str,
    str,
    datetime,
    datetime,
]
ROWS = TypeAdapter(list[ScheduleRow])


def trigger_due(outbox: PostgresOutbox, now: datetime, limit: int = 50) -> int:
    if now.utcoffset() is None:
        raise ValueError("SCHEDULER_REQUIRES_AWARE_TIME")
    db = outbox.connection
    with db.transaction():
        db.execute("SELECT pg_advisory_xact_lock(%s)", (0x41544E44,))
        rows = ROWS.validate_python(
            db.execute(
                "SELECT id,user_id,workflow_key,environment,rule_type,rule_json::text,timezone,"
                "input_text,next_run_at,created_at FROM workflow_schedules "
                "WHERE enabled AND next_run_at<=%s ORDER BY id FOR UPDATE SKIP LOCKED LIMIT %s",
                (now, limit),
            ).fetchall()
        )
        fired = 0
        for (
            schedule_id,
            user_id,
            workflow_key,
            environment,
            rule_type,
            raw,
            zone,
            text,
            due,
            anchor,
        ) in rows:
            fields = RuleFields.model_validate_json(raw)
            rule = parse_rule(rule_type, fields.model_dump(exclude_none=True), zone, anchor)
            future: datetime | None
            if rule_type == "cron":
                if fields.expression is None:
                    raise ValueError("CRON_REQUIRES_EXPRESSION")
                future = CronSchedule(fields.expression, zone).next_after(now)
                skipped = 0
                if due < now.astimezone(UTC).replace(second=0, microsecond=0):
                    db.execute(
                        "UPDATE workflow_schedules SET next_run_at=%s WHERE id=%s",
                        (future, schedule_id),
                    )
                    db.execute(
                        "INSERT INTO notifications "
                        "(user_id,kind,title,body,ref_type,ref_id,idempotency_key) "
                        "VALUES (%s,'system','错过了执行窗口',%s,'schedule',%s,%s) "
                        "ON CONFLICT(idempotency_key) DO NOTHING",
                        (
                            user_id,
                            f"工作流 {workflow_key} 的过期定时窗口已跳过。",
                            str(schedule_id),
                            f"miss:{schedule_id}:{due.isoformat()}",
                        ),
                    )
                    continue
            else:
                future, skipped = advance_from(rule, due, now)
            if rule_type == "once":
                skipped = 0
            message_id = str(
                uuid5(
                    NAMESPACE_URL,
                    f"a2flow:schedule:{schedule_id}:{due.astimezone(UTC).isoformat()}",
                )
            )
            outbox.enqueue(
                StartWorkflow(
                    message_id=message_id,
                    schedule_id=schedule_id,
                    scheduled_at=due,
                    environment=environment,
                    user_id=user_id,
                    workflow_key=workflow_key,
                    input_text=text,
                )
            )
            fired += 1
            db.execute(
                "UPDATE workflow_schedules SET next_run_at=%s,last_run_at=%s,enabled=%s "
                "WHERE id=%s",
                (future or due, due, future is not None, schedule_id),
            )
            if skipped:
                db.execute(
                    "INSERT INTO notifications "
                    "(user_id,kind,title,body,ref_type,ref_id,idempotency_key) "
                    "VALUES (%s,'system','错过了执行窗口',%s,'schedule',%s,%s) "
                    "ON CONFLICT(idempotency_key) DO NOTHING",
                    (
                        user_id,
                        f"工作流 {workflow_key} 错过 {skipped} 个执行窗口，已跳过。",  # noqa: RUF001
                        str(schedule_id),
                        f"miss:{message_id}",
                    ),
                )
        return fired
