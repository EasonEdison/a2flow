"""Per-user hourly cap and notification insert share one transaction."""

from datetime import UTC, datetime, timedelta

from pydantic import TypeAdapter

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from a2flow_scheduler.contracts import NotificationCommand
from a2flow_scheduler.notifications import cap_exceeded_plan, within_cap
from a2flow_scheduler.outbox import PostgresOutbox
from a2flow_scheduler.persistence import NotificationRow

_CAP_ROW = TypeAdapter(tuple[int, datetime])


def persist_notification(
    outbox: PostgresOutbox, command: NotificationCommand
) -> NotificationCommand | None:
    with outbox.transaction() as session:
        session.execute(
            select(
                func.pg_advisory_xact_lock(
                    func.hashtextextended(f"notification-cap:{command.user_id}", 0)
                )
            )
        )
        exists = session.scalar(
            select(NotificationRow.id).where(
                NotificationRow.idempotency_key == command.message_id
            )
        )
        if exists is not None:
            return None
        cap_row = session.execute(
            select(func.count(), func.now())
            .select_from(NotificationRow)
            .where(
                NotificationRow.user_id == command.user_id,
                NotificationRow.created_at >= func.now() - timedelta(hours=1),
            )
        ).one()
        count, moment = _CAP_ROW.validate_python(tuple(cap_row), strict=True)
        kind = "finished" if command.event == "completed" else command.event
        ref_type: str | None = "run"
        ref_id: str | None = command.run_id
        delivery = command
        if not within_cap(count):
            kind, title, body, key = cap_exceeded_plan(
                command.user_id, moment.astimezone(UTC), 1
            )
            delivery = NotificationCommand(
                message_id=key,
                user_id=command.user_id,
                run_id=command.run_id,
                event=command.event,
                title=title,
                body=body,
            )
            ref_type = None
            ref_id = None
        inserted = session.execute(
            insert(NotificationRow)
            .values(
                user_id=delivery.user_id,
                kind=kind,
                title=delivery.title,
                body=delivery.body,
                ref_type=ref_type,
                ref_id=ref_id,
                idempotency_key=delivery.message_id,
            )
            .on_conflict_do_nothing(index_elements=[NotificationRow.idempotency_key])
            .returning(NotificationRow.id)
        ).scalar_one_or_none()
        return delivery if inserted is not None else None
