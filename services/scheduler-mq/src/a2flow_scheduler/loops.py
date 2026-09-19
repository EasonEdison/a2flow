"""Scheduler-mq loop iterations (one bounded pass each; offline-testable).

Each iteration runs inside its own transaction. The trigger iteration takes a
PostgreSQL advisory xact lock so multiple instances never double-fire.
"""

from __future__ import annotations

import os

import datetime as dt
from typing import Any

from a2flow_bside.queue import QueueClient, PostgresQueueClient
from a2flow_scheduler import notifications, workers

QUEUE_RUN_WORKFLOW = "run_workflow"
QUEUE_DOMAIN_EVENTS = "domain_events"
ADVISORY_LOCK_KEY = 0x41544E44  # "ATND"


def run_trigger_iteration(
    *,
    conn,
    queue: QueueClient,
    now: dt.datetime,
    claim_limit: int = 50,
) -> int:
    with conn.transaction():
        conn.execute(
            "SELECT pg_advisory_xact_lock(%s)", (ADVISORY_LOCK_KEY,)
        )
        return workers.trigger_due_schedules(
            db=conn, queue=queue, now=now, claim_limit=claim_limit,
            notifications=notifications,
        )


def run_workflow_consumer_iteration(
    *,
    conn,
    queue: QueueClient,
    http: Any,
    claim_limit: int = 10,
    lease_seconds: int = 300,
) -> int:
    """Consume run_workflow jobs by starting runs through the b-side API."""
    processed = 0
    for item in queue.claim(
        QUEUE_RUN_WORKFLOW, limit=claim_limit, lease_seconds=lease_seconds
    ):
        payload = item.payload
        try:
            http.post_internal(
                "/api/internal/runs",
                token=os.environ.get("A2FLOW_SCHEDULER_INTERNAL_TOKEN") or "",
                json={
                    "workflowKey": payload.get("workflow_key"),
                    "input": payload.get("input", ""),
                    "userId": payload.get("user_id"),
                },
            )
            queue.complete(item.item_id)
            processed += 1
        except Exception:
            queue.requeue_failed(item.item_id)
    return processed


def run_event_consumer_iteration(
    *,
    conn,
    queue: QueueClient,
    lark: Any,
    claim_limit: int = 50,
    lease_seconds: int = 120,
) -> int:
    processed = 0
    for item in queue.claim(
        QUEUE_DOMAIN_EVENTS, limit=claim_limit, lease_seconds=lease_seconds
    ):
        try:
            def _owner(run_id):
                row = conn.execute(
                    "SELECT user_id FROM run_ownership WHERE run_id = %s",
                    (run_id,),
                ).fetchall()
                return row[0][0] if row else None

            workers.handle_domain_event(
                item.payload, db=conn, lark=lark,
                notifications=notifications, owner_resolver=_owner,
            )
            queue.complete(item.item_id)
            processed += 1
        except Exception:
            queue.requeue_failed(item.item_id)
    return processed


def run_monitor_iteration(
    *,
    conn,
    http: Any,
    timeout_hours: float = 24.0,
    now: dt.datetime | None = None,
    claim_limit: int = 50,
) -> int:
    moment = now or dt.datetime.now(dt.timezone.utc)
    return workers.monitor_wait_timeouts(
        db=conn, http=http, now=moment,
        timeout_hours=timeout_hours, claim_limit=claim_limit,
    )


__all__ = [
    "PostgresQueueClient",
    "QUEUE_DOMAIN_EVENTS",
    "QUEUE_RUN_WORKFLOW",
    "run_event_consumer_iteration",
    "run_monitor_iteration",
    "run_trigger_iteration",
    "run_workflow_consumer_iteration",
]
