"""Domain events published at trusted run-lifecycle boundaries.

The engine depends only on the EventSink protocol. Delivery (queues,
notifications, scheduling) belongs to other services and is never imported
or referenced here. Event payloads carry non-sensitive platform identifiers
only: never credentials, model text or business secrets.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID, uuid4

RUN_STARTED = "RUN_STARTED"
NODE_WAITING = "NODE_WAITING"
NODE_UNBLOCKED = "NODE_UNBLOCKED"
RUN_FINISHED = "RUN_FINISHED"
RUN_STOPPED = "RUN_STOPPED"
RUN_FAILED = "RUN_FAILED"


@dataclass(frozen=True)
class DomainEvent:
    """One engine event; event_id is the idempotency key for consumers."""

    event_id: UUID
    event_type: str
    run_id: str
    workflow_key: str
    user_id: str
    environment: str
    occurred_at: datetime
    payload: dict

    @classmethod
    def create(cls, event_type, run_id, workflow_key, user_id, environment, *,
               payload=None, occurred_at=None):
        return cls(
            event_id=uuid4(),
            event_type=event_type,
            run_id=run_id,
            workflow_key=workflow_key,
            user_id=user_id,
            environment=environment,
            occurred_at=occurred_at if occurred_at is not None
            else datetime.now(timezone.utc),
            payload=dict(payload or {}),
        )


class EventSink(Protocol):
    def publish(self, event: DomainEvent) -> None: ...


class NullSink:
    """Default no-op sink: the engine never requires a delivery backend."""

    def publish(self, event: DomainEvent) -> None:
        return None


class RecordingSink:
    """In-memory sink for tests; never a production persistence path."""

    def __init__(self):
        self.events = []

    def publish(self, event: DomainEvent) -> None:
        self.events.append(event)
