"""Scheduler-mq worker loops. Every dependency is injected for offline tests.

- handle_domain_event: wait-state bookkeeping + notification planning +
  in-app insert + Feishu delivery (idempotent per event, hourly cap).
- trigger_due_schedules: claims due schedules (SKIP LOCKED), advances rules
  with the missed-window policy, enqueues run_workflow jobs.
- monitor_wait_timeouts: stops runs waiting longer than the configured timeout.

The trigger loop takes an advisory lock before claiming (multi-instance safe);
the function below only implements the claim/advance/enqueue step.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Protocol

from a2flow_bside import scheduling as schedule_rules

# event types that end a wait on a run
_WAIT_CLEAR_EVENTS = frozenset(
    {"NODE_UNBLOCKED", "RUN_FINISHED", "RUN_STOPPED", "RUN_FAILED"}
)

_WAIT_UPSERT_SQL = """
INSERT INTO run_wait_states
    (run_id, user_id, workflow_key, waiting_since, last_event_at)
VALUES (%s, %s, %s, %s, %s)
ON CONFLICT (run_id) DO UPDATE SET
    waiting_since = EXCLUDED.waiting_since,
    last_event_at = EXCLUDED.last_event_at
"""

_WAIT_DELETE_SQL = "DELETE FROM run_wait_states WHERE run_id = %s"

_NOTIFY_INSERT_SQL = """
INSERT INTO notifications
    (user_id, kind, title, body, ref_type, ref_id, idempotency_key)
VALUES (%s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (idempotency_key) DO NOTHING
"""

_HOURLY_COUNT_SQL = """
SELECT count(*) FROM notifications
WHERE user_id = %s AND created_at >= now() - interval '1 hour'
"""

_DUE_SCHEDULES_SQL = """
SELECT id, user_id, workflow_key, environment, rule_type, rule_json,
       timezone, input_text, next_run_at, created_at
FROM workflow_schedules
WHERE enabled AND next_run_at <= %s
ORDER BY id
FOR UPDATE SKIP LOCKED
LIMIT %s
"""

_SCHEDULE_ADVANCE_SQL = """
UPDATE workflow_schedules
SET next_run_at = %s, last_run_at = %s, enabled = %s
WHERE id = %s
"""

_OVERDUE_WAITS_SQL = """
SELECT run_id, user_id, workflow_key FROM run_wait_states
WHERE waiting_since <= %s
ORDER BY waiting_since
LIMIT %s
"""

ADVISORY_LOCK_KEY = 0x41544E44  # "ATND"


class HttpClient(Protocol):
    def post(self, path: str, *, json: dict[str, Any]) -> Any: ...


class LarkSender(Protocol):
    def send(self, card: dict, *, dedup_key: str | None = None) -> None: ...


class OwnerNotResolved(Exception):
    """Raised when a run owner cannot be resolved yet; the loop requeues."""


def _parse_ts(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _lark_card(title: str, body: str) -> dict[str, Any]:
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": title},
        },
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": body}}
        ],
    }


def handle_domain_event(
    event: dict[str, Any],
    *,
    db,
    lark: LarkSender,
    notifications,
    owner_resolver=None,
) -> None:
    """Consume one domain event: wait-state bookkeeping + notifications."""
    event_type = event.get("event_type", "")
    run_id = event.get("run_id")
    if run_id and event_type == "NODE_WAITING":
        db.execute(
            _WAIT_UPSERT_SQL,
            (
                run_id,
                event.get("user_id", ""),
                event.get("workflow_key", ""),
                _parse_ts(event.get("occurred_at") or ""),
                dt.datetime.now(dt.timezone.utc),
            ),
        )
    elif run_id and event_type in _WAIT_CLEAR_EVENTS:
        db.execute(_WAIT_DELETE_SQL, (run_id,))

    plan = notifications.notification_plan(event)
    if plan is None:
        return
    kind, title, body = plan
    user_id = event.get("user_id") or ""
    if owner_resolver is not None and event.get("run_id"):
        resolved = owner_resolver(event.get("run_id"))
        if not resolved:
            # Ownership is bound shortly after a run starts; retry later
            # instead of notifying the runtime's fixed principal.
            raise OwnerNotResolved(event.get("run_id"))
        user_id = resolved
    event_id = event.get("event_id") or ""
    count = db.execute(_HOURLY_COUNT_SQL, (user_id,)).fetchall()[0][0]
    if notifications.within_cap(count):
        db.execute(
            _NOTIFY_INSERT_SQL,
            (user_id, kind, title, body, "run", run_id, event_id),
        )
        if lark is not None:
            lark.send(_lark_card(title, body), dedup_key=event_id)
        return
    merged_kind, merged_title, merged_body, merged_key = (
        notifications.cap_exceeded_plan(
            user_id, dt.datetime.now(dt.timezone.utc), 1
        )
    )
    db.execute(
        _NOTIFY_INSERT_SQL,
        (user_id, merged_kind, merged_title, merged_body, None, None, merged_key),
    )
    if lark is not None:
        lark.send(_lark_card(merged_title, merged_body), dedup_key=merged_key)


def trigger_due_schedules(
    *, db, queue, now: dt.datetime, claim_limit: int = 50, notifications
) -> int:
    """Claim due schedules and enqueue their run jobs. Returns fired count."""
    rows = db.execute(_DUE_SCHEDULES_SQL, (now, claim_limit)).fetchall()
    fired = 0
    for (
        schedule_id,
        user_id,
        workflow_key,
        environment,
        rule_type,
        rule_json,
        timezone,
        input_text,
        next_run_at,
        created_at,
    ) in rows:
        rule = schedule_rules.parse_rule(
            rule_type, rule_json, timezone, created_at
        )
        next_at = next_run_at
        if next_at.tzinfo is None:
            next_at = next_at.replace(tzinfo=dt.timezone.utc)
        next_future, skipped = schedule_rules.advance_from(rule, next_at, now)
        db.execute(
            _SCHEDULE_ADVANCE_SQL,
            (next_future, next_at, next_future is not None, schedule_id),
        )
        if skipped:
            db.execute(
                _NOTIFY_INSERT_SQL,
                (
                    user_id,
                    "system",
                    "错过了执行窗口",
                    f"工作流 {workflow_key} 错过 {skipped} 个执行窗口，已跳过。",
                    "schedule",
                    str(schedule_id),
                    f"miss:{schedule_id}:{next_at.isoformat()}",
                ),
            )
        run_key = f"run:{schedule_id}:{next_at.isoformat()}"
        queue.enqueue(
            "run_workflow",
            {
                "user_id": user_id,
                "workflow_key": workflow_key,
                "environment": environment,
                "input": input_text,
                "schedule_id": schedule_id,
            },
            dedup_key=run_key,
        )
        fired += 1
    return fired


def monitor_wait_timeouts(
    *,
    db,
    http: HttpClient,
    now: dt.datetime,
    timeout_hours: float = 24.0,
    claim_limit: int = 50,
) -> int:
    """Stop runs that have been waiting past the timeout. Returns stopped count."""
    deadline = now - dt.timedelta(hours=timeout_hours)
    rows = db.execute(_OVERDUE_WAITS_SQL, (deadline, claim_limit)).fetchall()
    stopped = 0
    for run_id, user_id, workflow_key in rows:
        http.post(f"/api/runs/{run_id}/stop", json={})
        db.execute(
            _NOTIFY_INSERT_SQL,
            (
                user_id,
                "stopped",
                "等待超时，已自动停止",
                f"工作流 {workflow_key} 等待确认超过 {timeout_hours:g} 小时，已自动停止。",
                "run",
                run_id,
                f"timeout:{run_id}",
            ),
        )
        db.execute(_WAIT_DELETE_SQL, (run_id,))
        stopped += 1
    return stopped
