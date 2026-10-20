"""Deployment-only translation of Runtime events into transactional notifications."""

from typing import Any, Literal

import psycopg

from agent_workflow_runtime.events import DomainEvent
from a2flow_scheduler.contracts import NotificationCommand
from a2flow_scheduler.outbox import enqueue_on_transaction


class SchedulerEventSink:
    """Deployment writer borrowing the Runtime-owned transaction, never committing."""

    def publish(self, connection: psycopg.Connection[Any], event: DomainEvent) -> None:
        names: dict[str, Literal["waiting", "completed", "failed", "stopped"]] = {
            "NODE_WAITING": "waiting", "RUN_FINISHED": "completed",
            "RUN_FAILED": "failed", "RUN_STOPPED": "stopped",
        }
        kind = names.get(event.event_type)
        if kind is None:
            return
        enqueue_on_transaction(connection, NotificationCommand(
            message_id="event:" + str(event.event_id), user_id=event.user_id,
            run_id=event.run_id, event=kind,
            title={"waiting": "工作流等待操作", "completed": "工作流已完成",
                   "failed": "工作流执行失败", "stopped": "工作流已停止"}[kind],
            body=("观察到工作流等待操作；是否仍可操作，请以当前运行详情为准。"
                  if kind == "waiting" else "请查看工作流运行详情。"),
        ))
