"""Run routes HTTP routes with explicit typed dependencies."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from skillweave_contracts.user_id import user_id_from_wire

from .errors import BsideError, RemoteRuntimeError
from .repositories import (
    RunOwnershipRepository,
)
from .route_dependencies import (
    JsonObject,
    WorkflowCatalog,
)
from .route_identity import CurrentIdentity
from .route_models import (
    InternalResume,
    InternalRunStart,
    RunAction,
    RunStart,
    WorkflowCardAction,
)
from .route_support import _iso, _iterate_thread
from .runtime_client import RuntimeClient
from .workflow_application import WorkflowApplicationService


def create_router(
    *,
    environment: str,
    run_ownership: RunOwnershipRepository,
    runtime_client: RuntimeClient,
    workflow_catalog: WorkflowCatalog,
) -> APIRouter:
    # 路由只装配工作流应用服务, 执行控制与归属规则共用一处实现。
    router = APIRouter()
    workflow = WorkflowApplicationService(
        environment=environment,
        run_ownership=run_ownership,
        runtime_client=runtime_client,
        workflow_catalog=workflow_catalog,
    )
    _LOGGER = logging.getLogger(__name__)

    # 工作流目录根据当前用户读取, 预制和个人资产的可见性由目录服务处理。
    @router.get("/api/workflows", response_model=None)
    async def workflows(*, identity: CurrentIdentity) -> JsonObject:
        return {"workflows": list(workflow_catalog(identity.userId))}

    # 用户启动沿用统一输入解析、归属预留和控制提交。
    @router.post("/api/runs", response_model=None)
    async def start_run(*, body: RunStart, identity: CurrentIdentity) -> JsonObject:
        return await workflow.start_for(
            identity.userId, body.workflowKey, body.input, body.sourceType
        )

    # 调度内部启动必须验证内部令牌和固定环境, 不能复用浏览器权限。
    @router.post("/api/internal/runs", response_model=None)
    async def internal_start(*, request: Request, body: InternalRunStart) -> JsonObject:
        workflow.require_internal(request)
        if body.environment != environment:
            raise BsideError("ENVIRONMENT_MISMATCH", 400)
        # 当前内部调度不支持个人工作流, 明确拒绝而不是静默改用其他资产。
        if body.workflowKey.startswith("personal-wf-"):
            raise BsideError("PERSONAL_WORKFLOW_SCHEDULING_UNSUPPORTED", 400)
        # 内部启动也检查用户可见目录并解析入参, 不因来自调度器而跳过。
        inputs = workflow.resolve_inputs(body.workflowKey, body.userId, body.input)
        # Commit ownership before calling Runtime. A timeout must not cause a
        # new control ID; Runtime's durable allocation deduplicates this ID.
        await asyncio.to_thread(
            run_ownership.reserve,
            control_id=body.requestId,
            user_id=body.userId,
            workflow_key=body.workflowKey,
            environment=environment,
            source_type="unknown",
        )
        # 执行服务使用原 requestId 去重, 内部重发不得生成新的控制号。
        view = await asyncio.to_thread(
            workflow.runtime(body.userId).start,
            body.requestId,
            body.workflowKey,
            inputs,
        )
        if view.get("runId"):
            run_ownership.bind_run_id(body.requestId, view["runId"])
        return {"controlRequestId": body.requestId, "status": "SUBMITTED"}

    # 内部状态查询只读取原控制请求, 并在获得真实运行号后补齐绑定。
    @router.get("/api/internal/runs/{request_id}", response_model=None)
    async def internal_run_status(*, request: Request, request_id: str) -> JsonObject:
        workflow.require_internal(request)
        owner = run_ownership.owner(request_id)
        if owner is None:
            raise BsideError("NOT_FOUND", 404)
        view = await asyncio.to_thread(workflow.runtime(owner).control, request_id)
        if view.get("runId"):
            run_ownership.bind_run_id(request_id, view["runId"])
        return {"controlRequestId": request_id, "status": "SUBMITTED", "view": view}

    # 卡片读取先校验运行归属, 尚未分配真实运行时只返回空卡片集合。
    @router.get("/api/runs/{control_id}/cards", response_model=None)
    async def workflow_cards(*, control_id: str, identity: CurrentIdentity) -> JsonObject:
        workflow.require_run_owner(control_id, identity.userId)
        try:
            run_id = await asyncio.to_thread(workflow.resolve_run_id, control_id, identity.userId)
        # 仅对明确尚未解析的运行返回空集合, 其他错误仍传播。
        except BsideError as error:
            if error.code == "RUN_NOT_RESOLVED":
                return {"cards": []}
            raise
        # 控制请求尚不存在不代表已完成; 卡片列表此时为空。
        except RemoteRuntimeError as error:
            if error.code == "CONTROL_NOT_FOUND":
                return {"cards": []}
            raise
        return await asyncio.to_thread(workflow.runtime(identity.userId).cards, run_id)

    # 恢复入口同时检查内部凭据、环境和真实运行的用户归属。
    @router.post("/api/internal/runs/{run_id}/cards/{card_id}/resume", response_model=None)
    async def internal_resume(
        *, request: Request, run_id: str, card_id: str, body: InternalResume
    ) -> JsonObject:
        workflow.require_internal(request)
        if body.environment != environment:
            raise BsideError("ENVIRONMENT_MISMATCH", 400)
        if run_ownership.owner_by_run(run_id) != body.userId:
            raise BsideError("NOT_FOUND", 404)
        # 只转发恢复协议字段, 可信身份由内部客户端单独绑定。
        await asyncio.to_thread(
            workflow.runtime(body.userId).resume_card,
            run_id,
            card_id,
            body.model_dump(exclude={"userId", "environment"}),
        )
        return {"controlRequestId": body.requestId, "status": "SUBMITTED"}

    # 恢复状态按原动作和续聊请求定位, 只查询既有事实。
    @router.get("/api/internal/runs/{run_id}/cards/{card_id}/resume-status", response_model=None)
    async def internal_resume_status(
        *,
        request: Request,
        run_id: str,
        card_id: str,
        userId: str,
        nodeId: str,
        interactionId: str,
        requestId: str,
        actionRequestId: str,
        requested_environment: Annotated[str, Query(alias="environment")],
    ) -> JsonObject:
        workflow.require_internal(request)
        # 内部查询也解析共享用户 ID 并复核环境, 禁止跨用户查看恢复结果。
        owner = user_id_from_wire(userId)
        if requested_environment != environment:
            raise BsideError("ENVIRONMENT_MISMATCH", 400)
        if run_ownership.owner_by_run(run_id) != owner:
            raise BsideError("NOT_FOUND", 404)
        return await asyncio.to_thread(
            workflow.runtime(owner).resume_status,
            run_id,
            card_id,
            {
                "nodeId": nodeId,
                "interactionId": interactionId,
                "requestId": requestId,
                "actionRequestId": actionRequestId,
            },
        )

    # 用户提交卡片只推进所属运行的指定节点与交互, 不能恢复无关流程。
    @router.post("/api/runs/{control_id}/cards/{card_id}/actions", response_model=None)
    async def workflow_card_action(
        *,
        control_id: str,
        card_id: str,
        body: WorkflowCardAction,
        identity: CurrentIdentity,
    ) -> JsonObject:
        workflow.require_run_owner(control_id, identity.userId)
        run_id = await asyncio.to_thread(workflow.resolve_run_id, control_id, identity.userId)
        return await asyncio.to_thread(
            workflow.runtime(identity.userId).card_action,
            run_id,
            card_id,
            body.model_dump(),
        )

    # 运行历史先读取产品归属记录, 再补充执行层的真实状态和标题。
    @router.get("/api/runs", response_model=None)
    async def list_runs(*, identity: CurrentIdentity) -> JsonObject:
        items = []
        for row in run_ownership.list_for(identity.userId):
            item = {
                "controlRequestId": row["control_id"],
                "workflowKey": row["workflow_key"],
                "createdAt": _iso(row["created_at"]),
            }
            # 远端控制查询不可用时保留记录, 不能把缺少运行视图当作执行成功。
            try:
                item["view"] = workflow.runtime(identity.userId).control(row["control_id"])
            except RemoteRuntimeError:
                item["view"] = None
            # 有真实运行号才读取生命周期, 控制提交状态不等于节点已完成。
            if item["view"] and item["view"].get("runId"):
                run_ownership.bind_run_id(row["control_id"], item["view"]["runId"])
                try:
                    actual = await asyncio.to_thread(
                        workflow.runtime(identity.userId).view,
                        item["view"]["runId"],
                    )
                    # 生命周期、标题和需求来自实际运行视图, 便于用户理解历史。
                    item["lifecycle"] = actual.get("lifecycle")
                    item["title"] = actual.get("title")
                    item["requirement"] = actual.get("requirement")
                # 生命周期查询失败显示 UNKNOWN, 保留结果未知而非伪造完成。
                except RemoteRuntimeError:
                    item["lifecycle"] = "UNKNOWN"
            items.append(item)
        return {"runs": items}

    # 详情先验证产品归属, 再尝试读取真实运行视图, 未取得时保留控制回执。
    @router.get("/api/runs/{run_id}", response_model=None)
    async def run_detail(*, run_id: str, identity: CurrentIdentity) -> JsonObject:
        workflow.require_run_owner(run_id, identity.userId)
        receipt = workflow.runtime(identity.userId).control(run_id)
        runtime_run_id = receipt.get("runId") if isinstance(receipt, dict) else None
        if runtime_run_id:
            try:
                return workflow.runtime(identity.userId).view(runtime_run_id)
            except RemoteRuntimeError:
                pass
        return receipt

    # 停止使用独立控制请求号, 具体停止准入与晚到结果由执行服务处理。
    @router.post("/api/runs/{run_id}/stop", response_model=None)
    async def stop_run(*, run_id: str, identity: CurrentIdentity) -> JsonObject:
        workflow.require_run_owner(run_id, identity.userId)
        runtime_run_id = workflow.resolve_run_id(run_id, identity.userId)
        return workflow.runtime(identity.userId).stop(runtime_run_id, uuid.uuid4().hex)

    # 旧动作入口定位具体节点与交互, 通过工作线程转发阻塞 SSE。
    @router.post("/api/runs/{run_id}/actions", response_model=None)
    async def run_action(
        *, run_id: str, body: RunAction, identity: CurrentIdentity
    ) -> StreamingResponse:
        workflow.require_run_owner(run_id, identity.userId)
        runtime_run_id = workflow.resolve_run_id(run_id, identity.userId)
        return StreamingResponse(
            _iterate_thread(
                workflow.runtime(identity.userId).action_stream(
                    runtime_run_id,
                    body.nodeId,
                    {
                        # 每次动作有控制身份, 节点与交互字段不能从正文中模糊匹配。
                        "controlRequestId": uuid.uuid4().hex,
                        "inputs": body.inputs,
                        "interactionId": body.interactionId,
                        "actionName": body.actionName,
                    },
                )
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    # 展示订阅先解析真实运行, 不在刷新页面时重新发起工作流。
    @router.get("/api/runs/{run_id}/surface", response_model=None)
    async def run_surface(*, run_id: str, identity: CurrentIdentity) -> StreamingResponse:
        workflow.require_run_owner(run_id, identity.userId)
        runtime_run_id = workflow.resolve_run_id(run_id, identity.userId)
        return StreamingResponse(
            _iterate_thread(workflow.runtime(identity.userId).surface_stream(runtime_run_id)),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    # 进度目录只代理原生已保存执行信息, 未绑定运行明确返回错误。
    @router.get("/api/runs/{control_id}/progress")
    async def run_progress_catalog(
        *, request: Request, control_id: str, identity: CurrentIdentity
    ) -> dict[str, object]:
        workflow.require_run_owner(control_id, identity.userId)
        query = workflow.progress_query(request)
        # An unbound run returns the existing explicit RUN_NOT_RESOLVED error.
        run_id = await asyncio.to_thread(workflow.resolve_run_id, control_id, identity.userId)
        return await asyncio.to_thread(
            workflow.runtime(identity.userId).progress_catalog, run_id, query
        )

    # 历史按节点与执行实例定位, 游标由原生接口严格校验。
    @router.get("/api/runs/{control_id}/nodes/{node_id}/executions/{execution_id}/history")
    async def run_progress_history(
        *,
        request: Request,
        control_id: str,
        node_id: str,
        execution_id: str,
        identity: CurrentIdentity,
    ) -> dict[str, object]:
        workflow.require_run_owner(control_id, identity.userId)
        query = workflow.progress_query(request)
        run_id = await asyncio.to_thread(workflow.resolve_run_id, control_id, identity.userId)
        return await asyncio.to_thread(
            workflow.runtime(identity.userId).progress_history,
            run_id,
            node_id,
            execution_id,
            query,
        )

    # 进度 SSE 使用原生同步迭代器, 由框架线程池消费, 不另建无界事件队列。
    @router.get("/api/runs/{control_id}/nodes/{node_id}/executions/{execution_id}/stream")
    async def run_progress_stream(
        *,
        request: Request,
        control_id: str,
        node_id: str,
        execution_id: str,
        identity: CurrentIdentity,
    ) -> StreamingResponse:
        workflow.require_run_owner(control_id, identity.userId)
        query = workflow.progress_query(request, streaming=True)
        run_id = await asyncio.to_thread(workflow.resolve_run_id, control_id, identity.userId)
        # 建立订阅连接也放在线程中, 保留 Last-Event-ID 供原生断点读取。
        stream = await asyncio.to_thread(
            workflow.runtime(identity.userId).progress_stream,
            run_id,
            node_id,
            execution_id,
            query,
            request.headers.get("last-event-id"),
        )
        # StreamingResponse consumes this sync iterator in its worker pool;
        # no unbounded queue or synthetic progress events are introduced.
        return StreamingResponse(
            stream,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    return router
