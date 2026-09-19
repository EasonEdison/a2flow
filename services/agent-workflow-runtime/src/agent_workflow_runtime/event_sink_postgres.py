"""Deployment-only PostgreSQL event sink for the runtime.

Writes DomainEvents into queue_items (queue='domain_events') with the event id
as the dedup key. The runtime never imports platform services; this adapter
only needs a psycopg connection supplied by the deployment wiring.
"""

from __future__ import annotations

import json

from .events import DomainEvent

QUEUE_DOMAIN_EVENTS = "domain_events"


def _to_dict(event: DomainEvent) -> dict:
    return {
        "event_id": str(event.event_id),
        "event_type": event.event_type,
        "run_id": event.run_id,
        "workflow_key": event.workflow_key,
        "user_id": event.user_id,
        "environment": event.environment,
        "occurred_at": event.occurred_at.isoformat(),
        "payload": dict(event.payload),
    }


class PostgresEventSink:
    """Publish each event as one queue_items row (at-least-once, idempotent)."""

    def __init__(self, connection) -> None:
        self._connection = connection

    def publish(self, event: DomainEvent) -> None:
        if not isinstance(event, DomainEvent):
            raise TypeError("EXPECTED_DOMAIN_EVENT")
        self._connection.execute(
            "INSERT INTO queue_items (queue, payload, dedup_key) "
            "VALUES (%s, %s::jsonb, %s) "
            "ON CONFLICT (dedup_key) DO NOTHING",
            (
                QUEUE_DOMAIN_EVENTS,
                json.dumps(_to_dict(event), ensure_ascii=False, separators=(",", ":")),
                str(event.event_id),
            ),
        )
