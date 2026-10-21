"""Notification routes HTTP routes with explicit typed dependencies."""

from __future__ import annotations

from fastapi import APIRouter

from .errors import BsideError
from .notification_repository import NotificationsRepository
from .route_dependencies import (
    JsonObject,
)
from .route_identity import CurrentIdentity


def create_router(
    *,
    notifications: NotificationsRepository,
) -> APIRouter:
    # 通知入口只操作当前登录用户的阅读投影, 不推进工作流或业务处理状态。
    router = APIRouter()

    # 列表返回标题、内容及来源引用, 时间采用 ISO 协议。
    @router.get("/api/notifications", response_model=None)
    async def list_notifications(*, identity: CurrentIdentity) -> JsonObject:
        return {
            "notifications": [
                {
                    "id": row.id,
                    "kind": row.kind,
                    "title": row.title,
                    "body": row.body,
                    # 引用类型与引用 ID 一起使用, 阅读状态独立于运行结果。
                    "refType": row.ref_type,
                    "refId": row.ref_id,
                    "read": row.read,
                    "createdAt": row.created_at.isoformat(),
                }
                for row in notifications.list_for(identity.userId)
            ]
        }

    # 标记已读仍带用户条件; 已读不等于审批通过或异常已解决。
    @router.post("/api/notifications/{notification_id}/read", response_model=None)
    async def mark_notification_read(
        *, notification_id: int, identity: CurrentIdentity
    ) -> JsonObject:
        # 不存在和他人通知统一返回未找到, 避免泄露通知归属。
        if not notifications.mark_read(notification_id, identity.userId):
            raise BsideError("NOT_FOUND", 404)
        return {"ok": True}

    return router
