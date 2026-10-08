"""Advance schedules and enqueue commands in one SQLAlchemy transaction."""

from datetime import UTC, datetime
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from a2flow_bside.scheduling import advance_from, parse_rule
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from a2flow_scheduler.contracts import CommandModel, StartWorkflow
from a2flow_scheduler.cron import CronSchedule
from a2flow_scheduler.outbox import PostgresOutbox
from a2flow_scheduler.persistence import NotificationRow, ScheduleRow


class RuleFields(CommandModel):
    at: str | None = None
    every: Literal["15m", "1h", "1d", "1w"] | None = None
    expression: str | None = None


class DueSchedule(CommandModel):
    id: int
    user_id: int
    workflow_key: str
    environment: Literal["PRT", "ONLINE"]
    rule_type: Literal["once", "period", "cron"]
    rule_json: RuleFields
    timezone: str
    input_text: str
    next_run_at: datetime
    created_at: datetime


def _notify_missed(
    session: Session, schedule: DueSchedule, body: str, key: str
) -> None:
    session.execute(
        insert(NotificationRow)
        .values(
            user_id=schedule.user_id,
            kind="system",
            title="错过了执行窗口",
            body=body,
            ref_type="schedule",
            ref_id=str(schedule.id),
            idempotency_key=key,
        )
        .on_conflict_do_nothing(index_elements=[NotificationRow.idempotency_key])
    )


def trigger_due(outbox: PostgresOutbox, now: datetime, limit: int = 50) -> int:
    if now.utcoffset() is None:
        raise ValueError("SCHEDULER_REQUIRES_AWARE_TIME")
    with outbox.transaction() as session:
        session.execute(select(func.pg_advisory_xact_lock(0x41544E44)))
        schedules = session.scalars(
            select(ScheduleRow)
            .where(
                ScheduleRow.enabled.is_(True),
                ScheduleRow.next_run_at <= now,
            )
            .order_by(ScheduleRow.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        ).all()
        fired = 0
        for record in schedules:
            schedule = DueSchedule.model_validate(record, from_attributes=True)
            fields = schedule.rule_json
            rule = parse_rule(
                schedule.rule_type,
                fields.model_dump(exclude_none=True),
                schedule.timezone,
                schedule.created_at,
            )
            future: datetime | None
            if schedule.rule_type == "cron":
                if fields.expression is None:
                    raise ValueError("CRON_REQUIRES_EXPRESSION")
                future = CronSchedule(fields.expression, schedule.timezone).next_after(
                    now
                )
                skipped = 0
                if schedule.next_run_at < now.astimezone(UTC).replace(
                    second=0, microsecond=0
                ):
                    session.execute(
                        update(ScheduleRow)
                        .where(ScheduleRow.id == schedule.id)
                        .values(next_run_at=future)
                    )
                    _notify_missed(
                        session,
                        schedule,
                        f"工作流 {schedule.workflow_key} 的过期定时窗口已跳过。",
                        f"miss:{schedule.id}:{schedule.next_run_at.isoformat()}",
                    )
                    continue
            else:
                future, skipped = advance_from(rule, schedule.next_run_at, now)
            if schedule.rule_type == "once":
                skipped = 0
            message_id = str(
                uuid5(
                    NAMESPACE_URL,
                    f"a2flow:schedule:{schedule.id}:{schedule.next_run_at.astimezone(UTC).isoformat()}",
                )
            )
            outbox.enqueue(
                StartWorkflow(
                    message_id=message_id,
                    schedule_id=schedule.id,
                    scheduled_at=schedule.next_run_at,
                    environment=schedule.environment,
                    user_id=schedule.user_id,
                    workflow_key=schedule.workflow_key,
                    input_text=schedule.input_text,
                ),
                session=session,
            )
            fired += 1
            session.execute(
                update(ScheduleRow)
                .where(ScheduleRow.id == schedule.id)
                .values(
                    next_run_at=future or schedule.next_run_at,
                    last_run_at=schedule.next_run_at,
                    enabled=future is not None,
                )
            )
            if skipped:
                _notify_missed(
                    session,
                    schedule,
                    f"工作流 {schedule.workflow_key} 错过 {skipped} 个执行窗口，已跳过。",
                    f"miss:{message_id}",
                )
        return fired
