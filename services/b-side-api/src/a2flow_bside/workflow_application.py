"""Workflow control operations with explicit runtime and ownership dependencies."""

from __future__ import annotations

import asyncio
import hmac
import logging
import os
import uuid

from fastapi import Request

from .errors import BsideError, RemoteRuntimeError
from .repositories import (
    RunOwnershipRepository,
)
from .route_dependencies import (
    JsonObject,
    WorkflowCatalog,
)
from .runtime_client import RuntimeClient

_LOGGER = logging.getLogger(__name__)


class WorkflowApplicationService:
    def __init__(
        self,
        *,
        environment: str,
        run_ownership: RunOwnershipRepository,
        runtime_client: RuntimeClient,
        workflow_catalog: WorkflowCatalog,
    ) -> None:
        self.environment = environment
        self.run_ownership = run_ownership
        self.runtime_client = runtime_client
        self.workflow_catalog = workflow_catalog

    def require_run_owner(self, control_id: str, owner_user: int) -> None:
        recorded = self.run_ownership.owner(control_id)
        if recorded is None:
            raise BsideError("NOT_FOUND", 404)
        if recorded != owner_user:
            raise BsideError("NOT_FOUND", 404)

    def runtime(self, user_id: int) -> RuntimeClient:
        return self.runtime_client.for_user(user_id, self.environment)

    def resolve_run_id(self, control_id: str, user_id: int) -> str:
        view = self.runtime(user_id).control(control_id)
        run_id = view.get("runId") or view.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            raise BsideError("RUN_NOT_RESOLVED", 409)
        self.run_ownership.bind_run_id(control_id, run_id)
        return run_id

    def resolve_inputs(
        self, workflow_key: str, user_id: int, raw_input: JsonObject | str
    ) -> JsonObject:
        # Every start, including object inputs, must resolve the caller's catalog.
        # Scheduled runs carry a plain prompt; wrap it into the workflow's
        # single required string property when it has one.
        entry = next(
            (
                item
                for item in self.workflow_catalog(user_id)
                if item.get("definitionKey") == workflow_key
            ),
            None,
        )
        if entry is None:
            raise BsideError("WORKFLOW_NOT_FOUND", 404)
        if not isinstance(raw_input, str):
            return raw_input
        schema = entry.get("inputSchema") or {}
        required = schema.get("required") or []
        properties = schema.get("properties") or {}
        if (
            len(required) == 1
            and properties.get(required[0], {}).get("type") == "string"
        ):
            return {required[0]: raw_input}
        raise BsideError("INVALID_INPUT", 400)

    async def start_for(
        self,
        user_id: int,
        workflow_key: str,
        raw_input: dict[str, object] | str,
        source_type: str = "manual",
    ) -> dict[str, str]:
        control_id = uuid.uuid4().hex
        inputs = await asyncio.to_thread(
            self.resolve_inputs,
            workflow_key,
            user_id,
            raw_input,
        )
        await asyncio.to_thread(
            self.run_ownership.reserve,
            control_id=control_id,
            user_id=user_id,
            workflow_key=workflow_key,
            environment=self.environment,
            source_type=source_type,
        )
        runtime = self.runtime(user_id)
        try:
            view = await asyncio.to_thread(
                runtime.start, control_id, workflow_key, inputs
            )
        except Exception as start_error:
            _LOGGER.warning(
                "Runtime start failed category=%s control_id=%s",
                type(start_error).__name__,
                control_id,
            )
            if (
                not isinstance(start_error, RemoteRuntimeError)
                or start_error.code != "RUNTIME_UNREACHABLE"
            ):
                raise
            # A failed HTTP response does not prove failed admission. Read the
            # same durable control once; never submit the business start again.
            try:
                view = await asyncio.to_thread(runtime.control, control_id)
                if (
                    view.get("controlRequestId") != control_id
                    or not isinstance(view.get("runId"), str)
                    or not view["runId"]
                ):
                    raise ValueError("INVALID_CONTROL_ADMISSION")
            except Exception as query_error:
                _LOGGER.warning(
                    "Runtime start unresolved category=%s control_id=%s",
                    type(query_error).__name__,
                    control_id,
                )
                # Keep ownership visible in My Runs, but do not claim success.
                raise start_error from None
        run_id = view.get("runId")
        if isinstance(run_id, str) and run_id:
            await asyncio.to_thread(self.run_ownership.bind_run_id, control_id, run_id)
        return {"controlRequestId": control_id, "status": "SUBMITTED"}

    def require_internal(self, request: Request) -> None:
        token = os.environ.get("A2FLOW_BSIDE_INTERNAL_TOKEN")
        if not token:
            raise BsideError("INTERNAL_API_DISABLED", 503)
        provided = request.headers.get("x-a2flow-internal-token") or ""
        if not hmac.compare_digest(provided, token):
            raise BsideError("INTERNAL_TOKEN_REQUIRED", 401)

    def progress_query(
        self, request: Request, *, streaming: bool = False
    ) -> list[tuple[str, str]]:
        query = request.query_params.multi_items()
        if request.headers.get("last-event-id") is not None and (
            not streaming or "after" in request.query_params
        ):
            raise BsideError("INVALID_PROGRESS_CURSOR", 400)
        # Keep all pairs, including duplicate or unknown keys, for native validation.
        return query
