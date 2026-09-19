"""Domain-event → notification mapping and rate limiting (pure functions).

The engine publishes generic domain events; this module decides which of them
become user notifications and what they say. No secrets, no delivery here —
delivery belongs to lark.py and the in-app table.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

# event_type -> notification kind; events not listed produce no notification.
EVENT_TO_KIND = {
    "NODE_WAITING": "waiting",
    "RUN_FINISHED": "finished",
    "RUN_STOPPED": "stopped",
    "RUN_FAILED": "failed",
}

_KIND_COPY = {
    "waiting": ("需要你的确认", "工作流 {workflow} 在节点「{node}」等待你确认。"),
    "finished": ("运行完成", "工作流 {workflow} 已完成。"),
    "stopped": ("已停止", "工作流 {workflow} 已停止，本次运行不再继续。"),
    "failed": ("运行失败", "工作流 {workflow} 运行失败。"),
}

USER_HOURLY_CAP = 20


def notification_plan(
    event: dict[str, Any],
) -> tuple[str, str, str] | None:
    """Return (kind, title, body) for notifiable events, else None."""
    kind = EVENT_TO_KIND.get(event.get("event_type", ""))
    if kind is None:
        return None
    title_template, body_template = _KIND_COPY[kind]
    workflow = event.get("workflow_key") or "未知工作流"
    payload = event.get("payload") or {}
    node = payload.get("node_title") or payload.get("nodeId") or "未命名节点"
    title = title_template
    body = body_template.format(workflow=workflow, node=node)
    return kind, title, body


def hour_bucket(user_id: str, moment: dt.datetime) -> str:
    """Idempotent merge key for the hourly rate cap."""
    return f"cap:{user_id}:{moment:%Y%m%d%H}"


def within_cap(existing_this_hour: int) -> bool:
    return existing_this_hour < USER_HOURLY_CAP


def cap_exceeded_plan(
    user_id: str, moment: dt.datetime, overflow_count: int
) -> tuple[str, str, str, str]:
    """One merged summary notification per hour bucket once the cap is hit."""
    title = "通知较多，已为你合并"
    body = f"过去一小时内还有 {overflow_count} 条未单独展示的通知，请前往通知中心查看。"
    return ("system", title, body, hour_bucket(user_id, moment))
