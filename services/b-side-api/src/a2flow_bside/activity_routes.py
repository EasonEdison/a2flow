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
    # 工作动态路由读取已提交事实; 异常处理接口独立保存处理任务状态。
    router = APIRouter()

    # 任务详情按可信用户和部署环境查询, 缺少组件时明确不可用。
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

    # 解决异常必须用户显式提交总结, 最终可否解决由仓库检查真实回执。
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

    # 集中检查动态仓库已装配, 不以空列表掩盖服务不可用。
    def _activities() -> WorkActivitiesRepository:
        if work_activities is None:
            raise BsideError("WORK_ACTIVITIES_UNAVAILABLE", 503)
        return work_activities

    # 右侧动态按需分页读取, 组别、游标长度和每页数量均受约束。
    @router.get("/api/work-activities", response_model=None)
    async def list_work_activities(
        *,
        # 待关注、运行中和已结束是产品分类, 不能用浏览器是否在线决定。
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

    # 结果只读接口支持指定节点和受限文本分页, 不重新执行工作流。
    @router.get("/api/work-activities/{activity_id}/result", response_model=None)
    async def work_activity_result(
        *,
        activity_id: str,
        nodeId: str | None = None,
        # 偏移和分页大小限制在明确范围内, 避免一次返回全部工具结果。
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

    # 单条详情仍携带用户和环境, 不能只凭动态 ID 跨账号读取。
    @router.get("/api/work-activities/{activity_id}", response_model=None)
    async def work_activity_detail(*, activity_id: str, identity: CurrentIdentity) -> JsonObject:
        return await asyncio.to_thread(
            _activities().get,
            user_id=identity.userId,
            environment=environment,
            activity_id=activity_id,
        )

    # 已查看只确认提醒已读; 等待表单必须真实提交, 不能用确认提醒替代。
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
