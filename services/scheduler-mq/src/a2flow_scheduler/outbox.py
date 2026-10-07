"""Durable typed commands. Redis contains references, never business payloads."""

from __future__ import annotations

from typing import Literal

from psycopg import Connection
from pydantic import TypeAdapter

from a2flow_scheduler.contracts import CommandModel, WorkflowCommand
from a2flow_scheduler.streams import RedisStreamTransport, StreamChannel

Database = Connection[tuple[object, ...]]
COMMANDS: TypeAdapter[WorkflowCommand] = TypeAdapter(WorkflowCommand)


class OutboxRecord(CommandModel):
    message_id: str
    channel: StreamChannel
    payload: str
    state: Literal["pending", "dispatching", "completed", "unknown", "rejected"]


class PostgresOutbox:
    """enqueue joins the caller transaction; no Redis call during business writes."""

    def __init__(self, connection: Database) -> None:
        self.connection = connection

    def enqueue(self, command: WorkflowCommand) -> None:
        channel = (
            StreamChannel.NOTIFICATIONS if command.kind == "notify" else StreamChannel.WORKFLOW
        )
        row = self.connection.execute(
            "INSERT INTO scheduler_outbox (message_id, channel, payload) VALUES (%s,%s,%s::jsonb) "
            "ON CONFLICT (message_id) DO UPDATE SET message_id=EXCLUDED.message_id "
            "WHERE scheduler_outbox.payload=EXCLUDED.payload RETURNING message_id",
            (command.message_id, channel.value, command.model_dump_json()),
        ).fetchone()
        if row is None:
            raise ValueError("OUTBOX_MESSAGE_ID_CONFLICT")

    def publish(self, transport: RedisStreamTransport, limit: int = 50) -> int:
        with self.connection.transaction():
            rows = self.connection.execute(
                "SELECT message_id, channel FROM scheduler_outbox WHERE state='pending' "
                "AND available_at <= now() "
                "AND (published_at IS NULL OR published_at < now()-interval '60 seconds') "
                "ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT %s",
                (limit,),
            ).fetchall()
            for message_id, channel in rows:
                if not isinstance(message_id, str) or not isinstance(channel, str):
                    raise ValueError("INVALID_OUTBOX_REFERENCE")
                transport.publish(StreamChannel(channel), message_id)
                self.connection.execute(
                    "UPDATE scheduler_outbox SET published_at=now() WHERE message_id=%s",
                    (message_id,),
                )
            return len(rows)

    def claim(self, message_id: str) -> WorkflowCommand | None:
        with self.connection.transaction():
            row = self.connection.execute(
                "UPDATE scheduler_outbox SET state='dispatching',claimed_at=now() "
                "WHERE message_id=%s AND state='pending' AND available_at <= now() "
                "RETURNING payload::text",
                (message_id,),
            ).fetchone()
            if row is None:
                return None
            payload = row[0]
            if not isinstance(payload, str):
                raise ValueError("INVALID_OUTBOX_PAYLOAD")
            return COMMANDS.validate_json(payload)

    def defer_unadmitted(self, message_id: str) -> None:
        """Only a proved pre-admission capacity rejection can re-enter pending."""
        self.connection.execute(
            "UPDATE scheduler_outbox SET state='pending',available_at=now()+interval '30 seconds',"
            "claimed_at=NULL,published_at=NULL,error_code='CAPACITY_EXHAUSTED' "
            "WHERE message_id=%s AND state='dispatching'",
            (message_id,),
        )

    def finish(
        self,
        message_id: str,
        state: Literal["completed", "unknown", "rejected"],
        error_code: str | None = None,
    ) -> None:
        self.connection.execute(
            "UPDATE scheduler_outbox SET state=%s,error_code=%s,completed_at="
            "CASE WHEN %s='completed' THEN now() ELSE NULL END WHERE message_id=%s "
            "AND state IN ('dispatching','unknown')",
            (state, error_code, state, message_id),
        )

    def uncertain_workflows(self, limit: int = 50) -> list[WorkflowCommand]:
        # A process may die after dispatch but before storing the response. Never replay it.
        self.connection.execute(
            "UPDATE scheduler_outbox SET state='unknown',error_code='DISPATCH_INTERRUPTED' "
            "WHERE state='dispatching' AND claimed_at < now()-interval '5 minutes'"
        )
        rows = self.connection.execute(
            "WITH candidates AS (SELECT message_id FROM scheduler_outbox "
            "WHERE state='unknown' AND channel='workflow' "
            "AND (reconciled_at IS NULL OR reconciled_at < now()-interval '30 seconds') "
            "ORDER BY COALESCE(reconciled_at,created_at) FOR UPDATE SKIP LOCKED LIMIT %s) "
            "UPDATE scheduler_outbox SET reconciled_at=now() FROM candidates "
            "WHERE scheduler_outbox.message_id=candidates.message_id RETURNING payload::text",
            (limit,),
        ).fetchall()
        payloads = TypeAdapter(list[str]).validate_python([row[0] for row in rows])
        return [COMMANDS.validate_json(payload) for payload in payloads]
