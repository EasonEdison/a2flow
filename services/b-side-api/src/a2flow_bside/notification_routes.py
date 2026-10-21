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
    router = APIRouter()

    @router.get("/api/notifications", response_model=None)
    async def list_notifications(*, identity: CurrentIdentity) -> JsonObject:
        return {
            "notifications": [
                {
                    "id": row.id,
                    "kind": row.kind,
                    "title": row.title,
                    "body": row.body,
                    "refType": row.ref_type,
                    "refId": row.ref_id,
                    "read": row.read,
                    "createdAt": row.created_at.isoformat(),
                }
                for row in notifications.list_for(identity.userId)
            ]
        }

    @router.post("/api/notifications/{notification_id}/read", response_model=None)
    async def mark_notification_read(
        *, notification_id: int, identity: CurrentIdentity
    ) -> JsonObject:
        if not notifications.mark_read(notification_id, identity.userId):
            raise BsideError("NOT_FOUND", 404)
        return {"ok": True}

    return router
