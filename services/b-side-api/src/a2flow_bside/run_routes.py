"""Run routes HTTP routes with explicit typed dependencies."""

from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from skillweave_contracts.user_id import user_id_from_wire

from .errors import BsideError, RemoteRuntimeError
from .identity import RequestIdentity
from .repositories import (
    RunOwnershipRepository,
)
from .route_dependencies import (
    JsonObject,
    WorkflowCatalog,
)
from .route_identity import identity
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
    router = APIRouter()
    workflow = WorkflowApplicationService(
        environment=environment,
        run_ownership=run_ownership,
        runtime_client=runtime_client,
        workflow_catalog=workflow_catalog,
    )
    _LOGGER = logging.getLogger(__name__)

    @router.get("/api/workflows", response_model=None)
    async def workflows(identity: RequestIdentity = Depends(identity)) -> JsonObject:
        return {"workflows": list(workflow_catalog(identity.userId))}

    @router.post("/api/runs", response_model=None)
    async def start_run(
        body: RunStart, identity: RequestIdentity = Depends(identity)
    ) -> JsonObject:
        return await workflow.start_for(
            identity.userId, body.workflowKey, body.input, body.sourceType
        )

    @router.post("/api/internal/runs", response_model=None)
    async def internal_start(request: Request, body: InternalRunStart) -> JsonObject:
        workflow.require_internal(request)
        if body.environment != environment:
            raise BsideError("ENVIRONMENT_MISMATCH", 400)
        if body.workflowKey.startswith("personal-wf-"):
            raise BsideError("PERSONAL_WORKFLOW_SCHEDULING_UNSUPPORTED", 400)
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
        view = await asyncio.to_thread(
            workflow.runtime(body.userId).start,
            body.requestId,
            body.workflowKey,
            inputs,
        )
        if view.get("runId"):
            run_ownership.bind_run_id(body.requestId, view["runId"])
        return {"controlRequestId": body.requestId, "status": "SUBMITTED"}

    @router.get("/api/internal/runs/{request_id}", response_model=None)
    async def internal_run_status(request: Request, request_id: str) -> JsonObject:
        workflow.require_internal(request)
        owner = run_ownership.owner(request_id)
        if owner is None:
            raise BsideError("NOT_FOUND", 404)
        view = await asyncio.to_thread(workflow.runtime(owner).control, request_id)
        if view.get("runId"):
            run_ownership.bind_run_id(request_id, view["runId"])
        return {"controlRequestId": request_id, "status": "SUBMITTED", "view": view}

    @router.get("/api/runs/{control_id}/cards", response_model=None)
    async def workflow_cards(
        control_id: str,
        identity: RequestIdentity = Depends(identity),
    ) -> JsonObject:
        workflow.require_run_owner(control_id, identity.userId)
        try:
            run_id = await asyncio.to_thread(
                workflow.resolve_run_id, control_id, identity.userId
            )
        except BsideError as error:
            if error.code == "RUN_NOT_RESOLVED":
                return {"cards": []}
            raise
        except RemoteRuntimeError as error:
            if error.code == "CONTROL_NOT_FOUND":
                return {"cards": []}
            raise
        return await asyncio.to_thread(workflow.runtime(identity.userId).cards, run_id)

    @router.post(
        "/api/internal/runs/{run_id}/cards/{card_id}/resume", response_model=None
    )
    async def internal_resume(
        request: Request,
        run_id: str,
        card_id: str,
        body: InternalResume,
    ) -> JsonObject:
        workflow.require_internal(request)
        if body.environment != environment:
            raise BsideError("ENVIRONMENT_MISMATCH", 400)
        if run_ownership.owner_by_run(run_id) != body.userId:
            raise BsideError("NOT_FOUND", 404)
        await asyncio.to_thread(
            workflow.runtime(body.userId).resume_card,
            run_id,
            card_id,
            body.model_dump(exclude={"userId", "environment"}),
        )
        return {"controlRequestId": body.requestId, "status": "SUBMITTED"}

    @router.get(
        "/api/internal/runs/{run_id}/cards/{card_id}/resume-status", response_model=None
    )
    async def internal_resume_status(
        request: Request,
        run_id: str,
        card_id: str,
        userId: str,
        nodeId: str,
        interactionId: str,
        requestId: str,
        actionRequestId: str,
        requested_environment: str = Query(alias="environment"),
    ) -> JsonObject:
        workflow.require_internal(request)
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

    @router.post("/api/runs/{control_id}/cards/{card_id}/actions", response_model=None)
    async def workflow_card_action(
        control_id: str,
        card_id: str,
        body: WorkflowCardAction,
        identity: RequestIdentity = Depends(identity),
    ) -> JsonObject:
        workflow.require_run_owner(control_id, identity.userId)
        run_id = await asyncio.to_thread(
            workflow.resolve_run_id, control_id, identity.userId
        )
        return await asyncio.to_thread(
            workflow.runtime(identity.userId).card_action,
            run_id,
            card_id,
            body.model_dump(),
        )

    @router.get("/api/runs", response_model=None)
    async def list_runs(identity: RequestIdentity = Depends(identity)) -> JsonObject:
        items = []
        for row in run_ownership.list_for(identity.userId):
            item = {
                "controlRequestId": row["control_id"],
                "workflowKey": row["workflow_key"],
                "createdAt": _iso(row["created_at"]),
            }
            try:
                item["view"] = workflow.runtime(identity.userId).control(
                    row["control_id"]
                )
            except RemoteRuntimeError:
                item["view"] = None
            if item["view"] and item["view"].get("runId"):
                run_ownership.bind_run_id(row["control_id"], item["view"]["runId"])
                try:
                    actual = await asyncio.to_thread(
                        workflow.runtime(identity.userId).view,
                        item["view"]["runId"],
                    )
                    item["lifecycle"] = actual.get("lifecycle")
                    item["title"] = actual.get("title")
                    item["requirement"] = actual.get("requirement")
                except RemoteRuntimeError:
                    item["lifecycle"] = "UNKNOWN"
            items.append(item)
        return {"runs": items}

    @router.get("/api/runs/{run_id}", response_model=None)
    async def run_detail(
        run_id: str, identity: RequestIdentity = Depends(identity)
    ) -> JsonObject:
        workflow.require_run_owner(run_id, identity.userId)
        receipt = workflow.runtime(identity.userId).control(run_id)
        runtime_run_id = receipt.get("runId") if isinstance(receipt, dict) else None
        if runtime_run_id:
            try:
                return workflow.runtime(identity.userId).view(runtime_run_id)
            except RemoteRuntimeError:
                pass
        return receipt

    @router.post("/api/runs/{run_id}/stop", response_model=None)
    async def stop_run(
        run_id: str, identity: RequestIdentity = Depends(identity)
    ) -> JsonObject:
        workflow.require_run_owner(run_id, identity.userId)
        runtime_run_id = workflow.resolve_run_id(run_id, identity.userId)
        return workflow.runtime(identity.userId).stop(runtime_run_id, uuid.uuid4().hex)

    @router.post("/api/runs/{run_id}/actions", response_model=None)
    async def run_action(
        run_id: str, body: RunAction, identity: RequestIdentity = Depends(identity)
    ) -> StreamingResponse:
        workflow.require_run_owner(run_id, identity.userId)
        runtime_run_id = workflow.resolve_run_id(run_id, identity.userId)
        return StreamingResponse(
            _iterate_thread(
                workflow.runtime(identity.userId).action_stream(
                    runtime_run_id,
                    body.nodeId,
                    {
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

    @router.get("/api/runs/{run_id}/surface", response_model=None)
    async def run_surface(
        run_id: str, identity: RequestIdentity = Depends(identity)
    ) -> StreamingResponse:
        workflow.require_run_owner(run_id, identity.userId)
        runtime_run_id = workflow.resolve_run_id(run_id, identity.userId)
        return StreamingResponse(
            _iterate_thread(
                workflow.runtime(identity.userId).surface_stream(runtime_run_id)
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    @router.get("/api/runs/{control_id}/progress")
    async def run_progress_catalog(
        request: Request,
        control_id: str,
        identity: RequestIdentity = Depends(identity),
    ) -> dict[str, object]:
        workflow.require_run_owner(control_id, identity.userId)
        query = workflow.progress_query(request)
        # An unbound run returns the existing explicit RUN_NOT_RESOLVED error.
        run_id = await asyncio.to_thread(
            workflow.resolve_run_id, control_id, identity.userId
        )
        return await asyncio.to_thread(
            workflow.runtime(identity.userId).progress_catalog, run_id, query
        )

    @router.get(
        "/api/runs/{control_id}/nodes/{node_id}/executions/{execution_id}/history"
    )
    async def run_progress_history(
        request: Request,
        control_id: str,
        node_id: str,
        execution_id: str,
        identity: RequestIdentity = Depends(identity),
    ) -> dict[str, object]:
        workflow.require_run_owner(control_id, identity.userId)
        query = workflow.progress_query(request)
        run_id = await asyncio.to_thread(
            workflow.resolve_run_id, control_id, identity.userId
        )
        return await asyncio.to_thread(
            workflow.runtime(identity.userId).progress_history,
            run_id,
            node_id,
            execution_id,
            query,
        )

    @router.get(
        "/api/runs/{control_id}/nodes/{node_id}/executions/{execution_id}/stream"
    )
    async def run_progress_stream(
        request: Request,
        control_id: str,
        node_id: str,
        execution_id: str,
        identity: RequestIdentity = Depends(identity),
    ) -> StreamingResponse:
        workflow.require_run_owner(control_id, identity.userId)
        query = workflow.progress_query(request, streaming=True)
        run_id = await asyncio.to_thread(
            workflow.resolve_run_id, control_id, identity.userId
        )
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
