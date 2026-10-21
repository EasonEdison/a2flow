"""Activity routes HTTP routes with explicit typed dependencies."""

from __future__ import annotations

import asyncio
from typing import Annotated, Literal

from fastapi import APIRouter, Query

from .errors import BsideError
from .processing_tasks import ProcessingTasksRepository
from .route_dependencies import (
    JsonObject,
)
from .route_identity import CurrentIdentity
from .route_models import (
    ProcessingResolution,
)
from .work_activities import WorkActivitiesRepository


def create_router(
    *,
    environment: str,
    work_activities: WorkActivitiesRepository | None,
    processing_tasks: ProcessingTasksRepository | None,
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/processing-tasks/{task_id}", response_model=None)
    async def processing_task(*, task_id: str, identity: CurrentIdentity) -> JsonObject:
        if processing_tasks is None:
            raise BsideError("PROCESSING_UNAVAILABLE", 503)
        return await asyncio.to_thread(
            processing_tasks.get,
            user_id=identity.userId,
            environment=environment,
            task_id=task_id,
        )

    @router.post("/api/processing-tasks/{task_id}/resolve", response_model=None)
    async def resolve_processing_task(
        *, task_id: str, body: ProcessingResolution, identity: CurrentIdentity
    ) -> JsonObject:
        if processing_tasks is None:
            raise BsideError("PROCESSING_UNAVAILABLE", 503)
        return await asyncio.to_thread(
            processing_tasks.resolve,
            user_id=identity.userId,
            environment=environment,
            task_id=task_id,
            summary=body.summary,
        )

    def _activities() -> WorkActivitiesRepository:
        if work_activities is None:
            raise BsideError("WORK_ACTIVITIES_UNAVAILABLE", 503)
        return work_activities

    @router.get("/api/work-activities", response_model=None)
    async def list_work_activities(
        *,
        group: Literal["attention", "running", "completed"] | None = None,
        cursor: Annotated[str | None, Query(max_length=1024)] = None,
        limit: Annotated[int, Query(ge=1, le=50)] = 5,
        identity: CurrentIdentity,
    ) -> JsonObject:
        return await asyncio.to_thread(
            _activities().list_runs,
            user_id=identity.userId,
            environment=environment,
            group=group,
            cursor=cursor,
            limit=limit,
        )

    @router.get("/api/work-activities/{activity_id}/result", response_model=None)
    async def work_activity_result(
        *,
        activity_id: str,
        nodeId: str | None = None,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=12000)] = 12000,
        identity: CurrentIdentity,
    ) -> JsonObject:
        return await asyncio.to_thread(
            _activities().get_result,
            user_id=identity.userId,
            environment=environment,
            activity_id=activity_id,
            node_id=nodeId,
            offset=offset,
            limit=limit,
        )

    @router.get("/api/work-activities/{activity_id}", response_model=None)
    async def work_activity_detail(*, activity_id: str, identity: CurrentIdentity) -> JsonObject:
        return await asyncio.to_thread(
            _activities().get,
            user_id=identity.userId,
            environment=environment,
            activity_id=activity_id,
        )

    @router.post(
        "/api/work-activities/{activity_id}/attention/{attention_id}/ack",
        response_model=None,
    )
    async def work_activity_ack(
        *, activity_id: str, attention_id: str, identity: CurrentIdentity
    ) -> JsonObject:
        return await asyncio.to_thread(
            _activities().acknowledge,
            user_id=identity.userId,
            environment=environment,
            activity_id=activity_id,
            attention_id=attention_id,
        )

    return router
