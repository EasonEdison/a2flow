"""Runtime-local ASGI adapter. No listener, authentication scheme or job queue."""

from functools import partial
from typing import Annotated
import threading
import math

import anyio
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, JsonValue

from .models import ActionRejected
from .service import control_identifier, require_owner

BODY_LIMIT = 64 * 1024
RESPONSE_LIMIT = 256 * 1024

ERRORS = {
    "PROGRESS_NOT_FOUND": (404, "NOT_FOUND"),
    "PROGRESS_UNAVAILABLE": (503, "PROGRESS_UNAVAILABLE"),
    "PROGRESS_INTEGRITY_ERROR": (503, "PROGRESS_UNAVAILABLE"),
    "INVALID_EXECUTION_ID": (400, "INVALID_INPUT"),
    "INVALID_PROGRESS_LIMIT": (400, "INVALID_INPUT"),
    "INVALID_PROGRESS_CURSOR": (400, "INVALID_PROGRESS_CURSOR"),
    "FUTURE_PROGRESS_CURSOR": (400, "FUTURE_PROGRESS_CURSOR"),
    "TRUSTED_CONTEXT_REQUIRED": (401, "TRUSTED_CONTEXT_REQUIRED"),
    "RUN_NOT_FOUND": (404, "NOT_FOUND"),
    "CONTROL_NOT_FOUND": (404, "NOT_FOUND"),
    "INTERACTION_NOT_FOUND": (404, "NOT_FOUND"),
    "NOT_AUTHORIZED": (404, "NOT_FOUND"),
    "INVALID_JSON": (400, "INVALID_INPUT"),
    "INVALID_SERVICE_INPUT": (400, "INVALID_INPUT"),
    "INVALID_ACTION_INPUT": (400, "INVALID_INPUT"),
    "INVALID_ACTION_REQUEST": (400, "INVALID_INPUT"),
    "RESET_REQUIRED": (409, "RESET_REQUIRED"),
    "RUN_STOPPED": (409, "RUN_STOPPED"),
    "RUN_NOT_ACTIVE": (409, "RUN_NOT_ACTIVE"),
    "RUN_ALREADY_TERMINAL": (409, "RUN_ALREADY_TERMINAL"),
    "RESTART_SOURCE_OUTSIDE_THIS_SLICE": (409, "RESTART_SOURCE_OUTSIDE_THIS_SLICE"),
    "CONTROL_REQUEST_CONFLICT": (409, "CONTROL_REQUEST_CONFLICT"),
    "INTERACTION_NOT_WAITING": (409, "INTERACTION_NOT_WAITING"),
    "RUN_OPERATION_PENDING_OR_UNCONFIRMED": (409, "RUN_OPERATION_PENDING_OR_UNCONFIRMED"),
    "ACTION_NOT_ALLOWED": (409, "ACTION_NOT_ALLOWED"),
    "RUN_DEFINITION_MISMATCH": (409, "RUN_DEFINITION_MISMATCH"),
    "PROJECTION_UNAVAILABLE": (503, "PROJECTION_UNAVAILABLE"),
    "RUN_REPOSITORY_UNCONFIRMED": (503, "CONTROL_UNCONFIRMED"),
}


def error_response(status, code):
    return JSONResponse({"error": {"code": code}}, status_code=status)


def bounded_response(value):
    response = JSONResponse(value)
    if len(response.body) > RESPONSE_LIMIT:
        return error_response(507, "OUTPUT_TOO_LARGE")
    return response


class BodyLimit:
    """Count actual ASGI bytes before parsing; never trust Content-Length."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        chunks, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                continue
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > BODY_LIMIT:
                return await error_response(413, "BODY_TOO_LARGE")(scope, receive, send)
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)
        delivered = False

        async def buffered_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, buffered_receive, send)


class _Lane:
    """Capacity remains owned by a dispatched thread even if its waiter cancels."""

    def __init__(self, capacity):
        if type(capacity) is not int or capacity < 1:
            raise ValueError("positive lane capacity required")
        self._slots = threading.BoundedSemaphore(capacity)
        self._limiter = anyio.CapacityLimiter(capacity)

    async def call(self, function, *, timeout=None):
        if not self._slots.acquire(blocking=False):
            return error_response(503, "CAPACITY_EXHAUSTED")
        lock = threading.Lock()
        state = {"started": False, "released": False}

        def work():
            with lock:
                if state["released"]:
                    return None  # cancelled before dispatch; never allocate
                state["started"] = True
            try:
                return function()
            finally:
                with lock:
                    state["released"] = True
                    self._slots.release()

        try:
            with anyio.fail_after(timeout) as deadline:
                value = await anyio.to_thread.run_sync(
                    work, abandon_on_cancel=True, limiter=self._limiter,
                )
            return bounded_response(value)
        except TimeoutError:
            if not deadline.cancel_called:
                raise  # a business TimeoutError is not an observer deadline
            return error_response(504, "READ_TIMEOUT")
        finally:
            with lock:
                if not state["started"] and not state["released"]:
                    state["released"] = True
                    self._slots.release()


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


ControlId = Annotated[str, BeforeValidator(control_identifier)]


class Start(_Closed):
    controlRequestId: ControlId
    definitionKey: str = Field(min_length=1, max_length=256)
    inputs: dict[str, JsonValue]


class Control(_Closed):
    controlRequestId: ControlId


class Restart(Control):
    inputs: dict[str, JsonValue]


class Action(Restart):
    interactionId: str = Field(min_length=1, max_length=256)
    actionName: str = Field(min_length=1, max_length=256)


def create_app(service, *, execution_capacity=2, read_capacity=2, stop_capacity=1, read_timeout=3):
    """Host middleware must set scope['a2flow.trusted_context'] to TrustedContext.

    Client headers/body/query cannot populate this scope key. The host is the
    identity authority and supplies all execution/configuration factories.
    Initialization is eager, not lifespan-dependent. Tests need no listener.
    """
    if type(read_timeout) not in (int, float) or not math.isfinite(read_timeout) or not 0 < read_timeout <= 10:
        raise ValueError("read timeout must be finite and within (0, 10] seconds")
    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)
    app.add_middleware(BodyLimit)
    execution, reads, stops = (_Lane(execution_capacity), _Lane(read_capacity), _Lane(stop_capacity))

    def owner(request):
        if request.query_params:
            raise ActionRejected("INVALID_SERVICE_INPUT")
        return require_owner(request.scope.get("a2flow.trusted_context"))

    @app.exception_handler(RequestValidationError)
    async def invalid(request, error):
        return error_response(400, "INVALID_INPUT")

    @app.exception_handler(ActionRejected)
    async def rejected(request, error):
        status, code = ERRORS.get(str(error), (500, "RUNTIME_ERROR"))
        return error_response(status, code)

    @app.exception_handler(Exception)
    async def unexpected(request, error):
        return error_response(500, "INTERNAL_ERROR")

    @app.post("/runtime/runs")
    async def start(request: Request, body: Start):
        who = owner(request)
        return await execution.call(partial(
            service.start, who, body.controlRequestId, body.definitionKey, body.inputs,
        ))

    @app.get("/runtime/controls/{control_id:path}")
    async def control(request: Request, control_id: str):
        who = owner(request)
        return await reads.call(partial(service.control, who, control_id), timeout=read_timeout)

    @app.get("/runtime/runs/{run_id}")
    async def inspect(request: Request, run_id: str):
        who = owner(request)
        return await reads.call(partial(service.inspect, who, run_id), timeout=read_timeout)

    @app.get("/runtime/runs/{run_id}/events")
    async def events(request: Request, run_id: str):
        who = owner(request)
        def observe():
            value = service.inspect(who, run_id)
            return {"type": "runtime.snapshot", "observedAt": value["observedAt"],
                    "delivery": "snapshot", "replay": False, "snapshot": value}
        if request.headers.get("last-event-id") is not None:
            return error_response(400, "REPLAY_UNSUPPORTED")
        return await reads.call(observe, timeout=read_timeout)

    @app.post("/runtime/runs/{run_id}/stop")
    async def stop(request: Request, run_id: str, body: Control):
        who = owner(request)
        return await stops.call(partial(service.stop, who, run_id, body.controlRequestId))

    @app.post("/runtime/runs/{run_id}/restart")
    async def restart(request: Request, run_id: str, body: Restart):
        who = owner(request)
        return await execution.call(partial(service.restart, who, run_id, body.controlRequestId, body.inputs))

    @app.post("/runtime/runs/{run_id}/nodes/{node_id}/actions")
    async def action(request: Request, run_id: str, node_id: str, body: Action):
        who = owner(request)
        return await execution.call(partial(service.action, who, run_id, node_id, body.model_dump()))

    from .progress_http import add_progress_routes
    add_progress_routes(app, service, read_capacity=read_capacity, read_timeout=read_timeout)
    return app
