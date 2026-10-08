"""Typed durable outbox. Admission commits before external dispatch."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from typing import Literal

from psycopg import Connection
from pydantic import TypeAdapter
from sqlalchemy import Text, cast, func, literal, or_, select, update
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from a2flow_scheduler.contracts import WorkflowCommand
from a2flow_scheduler.persistence import OutboxRow
from a2flow_scheduler.streams import RedisStreamTransport, StreamChannel

COMMANDS: TypeAdapter[WorkflowCommand] = TypeAdapter(WorkflowCommand)

# The card store owns this psycopg transaction: never commit or close it here.
_CARD_ENQUEUE_SQL = """
INSERT INTO scheduler_outbox (message_id, channel, payload)
VALUES (%s, %s, %s::jsonb)
ON CONFLICT (message_id) DO UPDATE SET message_id = EXCLUDED.message_id
WHERE scheduler_outbox.payload = EXCLUDED.payload
RETURNING message_id
"""


def command_channel(command: WorkflowCommand) -> StreamChannel:
    return (
        StreamChannel.NOTIFICATIONS
        if command.kind == "notify"
        else StreamChannel.WORKFLOW
    )


def enqueue_on_card_transaction(
    connection: Connection[tuple[object, ...]],
    command: WorkflowCommand,
) -> None:
    if (
        connection.execute(
            _CARD_ENQUEUE_SQL,
            (
                command.message_id,
                command_channel(command).value,
                command.model_dump_json(),
            ),
        ).fetchone()
        is None
    ):
        raise ValueError("OUTBOX_MESSAGE_ID_CONFLICT")


class PostgresOutbox:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @contextmanager
    def transaction(self) -> Iterator[Session]:
        with Session(self.engine) as session, session.begin():
            yield session

    def enqueue(self, command: WorkflowCommand, *, session: Session) -> None:
        """Join caller transaction; no commit or Redis call."""
        statement = insert(OutboxRow).values(
            message_id=command.message_id,
            channel=command_channel(command).value,
            payload=cast(literal(command.model_dump_json(), type_=Text), JSONB),
        )
        upsert = statement.on_conflict_do_update(
            index_elements=[OutboxRow.message_id],
            set_={OutboxRow.message_id: statement.excluded.message_id},
            where=OutboxRow.payload == statement.excluded.payload,
        ).returning(OutboxRow.message_id)
        if session.execute(upsert).scalar_one_or_none() is None:
            raise ValueError("OUTBOX_MESSAGE_ID_CONFLICT")

    def publish(self, transport: RedisStreamTransport, limit: int = 50) -> int:
        with self.transaction() as session:
            references = (
                session.execute(
                    select(OutboxRow.message_id, OutboxRow.channel)
                    .where(
                        OutboxRow.state == "pending",
                        OutboxRow.available_at <= func.now(),
                        or_(
                            OutboxRow.published_at.is_(None),
                            OutboxRow.published_at < func.now() - timedelta(seconds=60),
                        ),
                    )
                    .order_by(OutboxRow.created_at)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
                .tuples()
                .all()
            )
            for message_id, channel in references:
                transport.publish(StreamChannel(channel), message_id)
                session.execute(
                    update(OutboxRow)
                    .where(OutboxRow.message_id == message_id)
                    .values(published_at=func.now())
                )
            return len(references)

    def claim(self, message_id: str) -> WorkflowCommand | None:
        with self.transaction() as session:
            payload = session.execute(
                update(OutboxRow)
                .where(
                    OutboxRow.message_id == message_id,
                    OutboxRow.state == "pending",
                    OutboxRow.available_at <= func.now(),
                )
                .values(state="dispatching", claimed_at=func.now())
                .returning(cast(OutboxRow.payload, Text))
            ).scalar_one_or_none()
            return None if payload is None else COMMANDS.validate_json(payload)

    def defer_unadmitted(self, message_id: str) -> None:
        with self.transaction() as session:
            session.execute(
                update(OutboxRow)
                .where(
                    OutboxRow.message_id == message_id,
                    OutboxRow.state == "dispatching",
                )
                .values(
                    state="pending",
                    available_at=func.now() + timedelta(seconds=30),
                    claimed_at=None,
                    published_at=None,
                    error_code="CAPACITY_EXHAUSTED",
                )
            )

    def finish(
        self,
        message_id: str,
        state: Literal["completed", "unknown", "rejected"],
        error_code: str | None = None,
    ) -> None:
        with self.transaction() as session:
            session.execute(
                update(OutboxRow)
                .where(
                    OutboxRow.message_id == message_id,
                    OutboxRow.state.in_(["dispatching", "unknown"]),
                )
                .values(
                    state=state,
                    error_code=error_code,
                    completed_at=func.now() if state == "completed" else None,
                )
            )

    def uncertain_workflows(self, limit: int = 50) -> list[WorkflowCommand]:
        with self.transaction() as session:
            session.execute(
                update(OutboxRow)
                .where(
                    OutboxRow.state == "dispatching",
                    OutboxRow.claimed_at < func.now() - timedelta(minutes=5),
                )
                .values(state="unknown", error_code="DISPATCH_INTERRUPTED")
            )
            candidates = (
                select(OutboxRow.message_id)
                .where(
                    OutboxRow.state == "unknown",
                    OutboxRow.channel == "workflow",
                    or_(
                        OutboxRow.reconciled_at.is_(None),
                        OutboxRow.reconciled_at < func.now() - timedelta(seconds=30),
                    ),
                )
                .order_by(func.coalesce(OutboxRow.reconciled_at, OutboxRow.created_at))
                .limit(limit)
                .with_for_update(skip_locked=True)
                .cte("candidates")
            )
            payloads = session.execute(
                update(OutboxRow)
                .where(
                    OutboxRow.message_id == candidates.c.message_id,
                )
                .values(reconciled_at=func.now())
                .returning(cast(OutboxRow.payload, Text))
            ).scalars()
            return [COMMANDS.validate_json(payload) for payload in payloads]
