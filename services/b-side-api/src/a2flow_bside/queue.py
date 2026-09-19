"""Swappable work/event queue. v1 implementation is PostgreSQL (SKIP LOCKED).

Callers depend only on the QueueClient protocol; the PostgreSQL implementation
can be replaced by Redis/RabbitMQ without touching callers. Delivery is
at-least-once: consumers must be idempotent (dedup_key on enqueue, guarded
UPDATEs on completion).
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any, Protocol


class QueueError(Exception):
    """Unrecoverable queue operation failure."""


@dataclasses.dataclass(frozen=True)
class QueueItem:
    item_id: int
    queue: str
    payload: dict[str, Any]
    attempts: int


class QueueClient(Protocol):
    def enqueue(
        self,
        queue: str,
        payload: dict[str, Any],
        *,
        dedup_key: str | None = None,
    ) -> None: ...

    def claim(
        self, queue: str, limit: int = 10, lease_seconds: int = 120
    ) -> list[QueueItem]: ...

    def complete(self, item_id: int) -> None: ...

    def extend(self, item_id: int, lease_seconds: int) -> None: ...

    def requeue_failed(self, item_id: int) -> None: ...


class PostgresQueueClient:
    """Queue over the queue_items table; the caller owns the psycopg connection.

    claim() atomically marks rows claimed under SKIP LOCKED and grants a lease
    (claimed_until). Expired leases become claimable again, so a crashed worker
    never permanently loses an item (at-least-once).
    """

    _CLAIM_SQL = """
        WITH candidates AS (
            SELECT id
            FROM queue_items
            WHERE queue = %s
              AND (state = 'pending'
                   OR (state = 'claimed' AND claimed_until <= now()))
            ORDER BY id
            FOR UPDATE SKIP LOCKED
            LIMIT %s
        )
        UPDATE queue_items AS item
        SET state = 'claimed',
            claimed_until = now() + make_interval(secs => %s),
            attempts = attempts + 1
        FROM candidates
        WHERE item.id = candidates.id
        RETURNING item.id, item.queue, item.payload, item.attempts
    """

    def __init__(self, connection) -> None:
        self._connection = connection

    def enqueue(
        self, queue: str, payload: dict[str, Any], *, dedup_key: str | None = None
    ) -> None:
        if not isinstance(queue, str) or not queue:
            raise QueueError("INVALID_QUEUE_NAME")
        if dedup_key is not None and (
            not isinstance(dedup_key, str) or not dedup_key
        ):
            raise QueueError("INVALID_DEDUP_KEY")
        self._connection.execute(
            "INSERT INTO queue_items (queue, payload, dedup_key) "
            "VALUES (%s, %s::jsonb, %s) "
            "ON CONFLICT (dedup_key) DO NOTHING",
            (
                queue,
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                dedup_key,
            ),
        )

    def claim(
        self, queue: str, limit: int = 10, lease_seconds: int = 120
    ) -> list[QueueItem]:
        if not isinstance(queue, str) or not queue:
            raise QueueError("INVALID_QUEUE_NAME")
        if limit < 1 or lease_seconds < 1:
            raise QueueError("INVALID_CLAIM_ARGUMENTS")
        result = self._connection.execute(
            self._CLAIM_SQL, (queue, limit, lease_seconds)
        )
        return [
            QueueItem(
                item_id=row[0],
                queue=row[1],
                payload=row[2] if isinstance(row[2], dict) else {},
                attempts=row[3],
            )
            for row in result.fetchall()
        ]

    def complete(self, item_id: int) -> None:
        self._connection.execute(
            "UPDATE queue_items SET state = 'done', claimed_until = NULL "
            "WHERE id = %s AND state = 'claimed'",
            (item_id,),
        )

    def extend(self, item_id: int, lease_seconds: int) -> None:
        if lease_seconds < 1:
            raise QueueError("INVALID_CLAIM_ARGUMENTS")
        self._connection.execute(
            "UPDATE queue_items "
            "SET claimed_until = now() + make_interval(secs => %s) "
            "WHERE id = %s AND state = 'claimed'",
            (lease_seconds, item_id),
        )

    def requeue_failed(self, item_id: int) -> None:
        self._connection.execute(
            "UPDATE queue_items SET state = 'pending', claimed_until = NULL "
            "WHERE id = %s AND state = 'claimed'",
            (item_id,),
        )
