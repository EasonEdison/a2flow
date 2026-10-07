"""Preserve the existing per-user hourly cap with transactional publication."""

from datetime import UTC, datetime

from a2flow_scheduler.contracts import NotificationCommand
from a2flow_scheduler.notifications import cap_exceeded_plan, within_cap
from a2flow_scheduler.outbox import PostgresOutbox


def persist_notification(
    outbox: PostgresOutbox, command: NotificationCommand
) -> NotificationCommand | None:
    db = outbox.connection
    with db.transaction():
        db.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
            (f"notification-cap:{command.user_id}",),
        )
        exists = db.execute(
            "SELECT id FROM notifications WHERE idempotency_key=%s", (command.message_id,)
        ).fetchone()
        if exists is not None:
            return None
        row = db.execute(
            "SELECT count(*),now() FROM notifications "
            "WHERE user_id=%s AND created_at >= now()-interval '1 hour'",
            (command.user_id,),
        ).fetchone()
        if row is None or not isinstance(row[0], int) or not isinstance(row[1], datetime):
            raise ValueError("INVALID_NOTIFICATION_CAP_ROW")
        kind = "finished" if command.event == "completed" else command.event
        ref_type: str | None = "run"
        ref_id: str | None = command.run_id
        delivery = command
        if not within_cap(row[0]):
            kind, title, body, key = cap_exceeded_plan(command.user_id, row[1].astimezone(UTC), 1)
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
        inserted = db.execute(
            "INSERT INTO notifications "
            "(user_id,kind,title,body,ref_type,ref_id,idempotency_key) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(idempotency_key) DO NOTHING RETURNING id",
            (
                delivery.user_id,
                kind,
                delivery.title,
                delivery.body,
                ref_type,
                ref_id,
                delivery.message_id,
            ),
        ).fetchone()
        return delivery if inserted is not None else None
