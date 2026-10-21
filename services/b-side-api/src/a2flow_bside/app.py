"""B-side HTTP composition: explicit dependencies, guards and lifecycle.

Request models are re-exported for existing imports; domain routers own handlers.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import re
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from . import (
    account_routes,
    activity_routes,
    conversation_routes,
    notification_routes,
    run_routes,
    schedule_routes,
)
from .account_guard import AccountGuardError, PostgresAccountGuard
from .chat_runner import ChatRunner
from .durable_chat import DurableChat, DurableDispatcher
from .errors import BsideError, RemoteRuntimeError
from .identity import (
    SESSION_COOKIE,
    require_origin,
    resolve_identity,
)
from .notification_repository import NotificationsRepository
from .processing_tasks import ProcessingTasksRepository
from .repositories import (
    ConversationsRepository,
    MessagesRepository,
    RunOwnershipRepository,
    SchedulesRepository,
    SessionsRepository,
    UsersRepository,
)
from .route_dependencies import (
    ChatAction,
    ChatCards,
    JsonObject,
    MemoryReplace,
    MemoryView,
    WorkflowCatalog,
)
from .route_models import (
    ChatCardAction,
    ConversationCreate,
    CronRuleInput,
    InternalResume,
    InternalRunStart,
    LoginRequest,
    MemoryEntry,
    MemorySettings,
    MessageSend,
    ProcessingResolution,
    ProcessingTarget,
    RegisterRequest,
    RunAction,
    RunRefCreate,
    RunReference,
    RunStart,
    ScheduleCreate,
    ScheduleUpdate,
    WorkflowCardAction,
)
from .route_support import _bounded_run_reference, _iso, _iterate_thread, _schedule_json
from .runtime_client import RuntimeClient
from .schedule_history import (
    ScheduleHistoryRepository,
)
from .work_activities import WorkActivitiesRepository

__all__ = [
    "create_app",
    "MemoryEntry",
    "MemorySettings",
    "RegisterRequest",
    "LoginRequest",
    "ConversationCreate",
    "RunReference",
    "ProcessingTarget",
    "ProcessingResolution",
    "MessageSend",
    "RunStart",
    "RunRefCreate",
    "InternalRunStart",
    "RunAction",
    "ChatCardAction",
    "WorkflowCardAction",
    "InternalResume",
    "CronRuleInput",
    "ScheduleCreate",
    "ScheduleUpdate",
    "_iso",
    "_iterate_thread",
    "_bounded_run_reference",
    "_schedule_json",
]

_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _query_allowed(request: Request) -> bool:
    """Allow only declared GET query fields; identity checks still run in each route."""
    if request.method != "GET":
        return False
    path = request.url.path
    if path == "/api/conversations/messages":
        allowed = {"conversationId"}
    elif re.fullmatch(r"/api/internal/runs/[^/]+/cards/[^/]+/resume-status", path):
        allowed = {
            "userId",
            "environment",
            "nodeId",
            "interactionId",
            "requestId",
            "actionRequestId",
        }
    elif re.fullmatch(r"/api/runs/[^/]+/progress", path) or re.fullmatch(
        r"/api/runs/[^/]+/nodes/[^/]+/executions/[^/]+/(history|stream)", path
    ):
        allowed = {"after", "limit"}
    elif path == "/api/work-activities":
        allowed = {"group", "cursor", "limit"}
    elif re.fullmatch(r"/api/work-activities/[^/]+/result", path):
        allowed = {"nodeId", "offset", "limit"}
    else:
        return False
    pairs = request.query_params.multi_items()
    keys = [key for key, _ in pairs]
    return len(keys) == len(set(keys)) and set(keys) <= allowed


def create_app(
    *,
    users: UsersRepository,
    sessions: SessionsRepository,
    conversations: ConversationsRepository,
    messages: MessagesRepository,
    schedules: SchedulesRepository,
    notifications: NotificationsRepository,
    run_ownership: RunOwnershipRepository,
    runtime_client: RuntimeClient,
    chat_runner: ChatRunner,
    workflow_catalog: WorkflowCatalog,
    pepper: str,
    browser_origin: str,
    environment: str,
    session_seconds: int,
    now: Callable[[], dt.datetime] | None = None,
    schedule_history: ScheduleHistoryRepository | None = None,
    memory_view: MemoryView | None = None,
    memory_replace: MemoryReplace | None = None,
    work_activities: WorkActivitiesRepository | None = None,
    processing_tasks: ProcessingTasksRepository | None = None,
    chat_cards: ChatCards | None = None,
    chat_action: ChatAction | None = None,
    browser_origins: tuple[str, ...] = (),
    account_guard: PostgresAccountGuard | None = None,
    durable_chat: DurableChat | None = None,
) -> FastAPI:
    from .config import browser_origin as validate_origin

    allowed_origins = tuple(
        validate_origin(value) for value in (browser_origins or (browser_origin,))
    )
    if (
        validate_origin(browser_origin) not in allowed_origins
        or len({value.split(":", 1)[0] for value in allowed_origins}) != 1
    ):
        raise RuntimeError("INVALID_BSIDE_BROWSER_ORIGINS")
    clock = now or (lambda: dt.datetime.now(dt.timezone.utc))

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        stop = asyncio.Event()
        worker = None
        if durable_chat is not None:
            await asyncio.to_thread(durable_chat.check_ready)
            worker = asyncio.create_task(
                DurableDispatcher(
                    durable_chat, messages, chat_runner, processing_tasks
                ).run(stop)
            )
        try:
            yield
        finally:
            stop.set()
            if worker is not None:
                await worker
            # Card actions stay owned after the HTTP subscriber disconnects.
            while chat_tasks:
                await asyncio.gather(*tuple(chat_tasks), return_exceptions=True)

    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None, lifespan=lifespan)
    chat_tasks: set[asyncio.Task[JsonObject]] = set()
    app.state.chat_tasks = chat_tasks

    def retain_task(task: asyncio.Task[JsonObject]) -> None:
        chat_tasks.add(task)

        def finished(completed: asyncio.Task[JsonObject]) -> None:
            chat_tasks.discard(completed)
            # Detached HTTP requests still have an owner that observes failures.
            if not completed.cancelled():
                completed.exception()

        task.add_done_callback(finished)

    @app.middleware("http")
    async def bside_guard(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.url.path.startswith("/api"):
            internal = request.url.path.startswith("/api/internal/")
            try:
                if request.query_params and not _query_allowed(request):
                    raise BsideError("QUERY_PARAMETERS_NOT_ALLOWED", 400)
                lowered = {name.lower() for name in request.headers.keys()}
                if lowered & {
                    "x-a2flow-environment",
                    "x-a2flow-role",
                    "x-a2flow-roles",
                    "x-a2flow-user-id",
                    "x-environment",
                    "x-role",
                    "x-roles",
                    "x-user-id",
                }:
                    raise BsideError("IDENTITY_FIELDS_NOT_ALLOWED", 400)
                if request.method in _UNSAFE_METHODS and not internal:
                    require_origin(request.headers, allowed_origins)
            except BsideError as error:
                return JSONResponse(
                    {"error": {"code": error.code}}, status_code=error.status
                )
            if not internal:
                try:
                    request.scope["a2flow.bside.identity"] = await run_in_threadpool(
                        resolve_identity,
                        request.cookies.get(SESSION_COOKIE),
                        sessions=sessions,
                        now=clock,
                    )
                except Exception as error:
                    failure = PostgresAccountGuard.unavailable("bside_session", error)
                    return JSONResponse(
                        {"error": {"code": failure.code}},
                        status_code=failure.status,
                        headers=failure.headers(),
                    )
        return await call_next(request)

    @app.exception_handler(AccountGuardError)
    async def account_guard_failure(
        request: Request, error: AccountGuardError
    ) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": error.code}},
            status_code=error.status,
            headers=error.headers(),
        )

    @app.exception_handler(BsideError)
    async def bside_failure(request: Request, error: BsideError) -> JSONResponse:
        return JSONResponse({"error": {"code": error.code}}, status_code=error.status)

    @app.exception_handler(RemoteRuntimeError)
    async def runtime_failure(
        request: Request, error: RemoteRuntimeError
    ) -> JSONResponse:
        return JSONResponse({"error": {"code": error.code}}, status_code=error.status)

    @app.exception_handler(RequestValidationError)
    async def invalid_input(
        request: Request, error: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse({"error": {"code": "INVALID_INPUT"}}, status_code=400)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, error: Exception) -> JSONResponse:
        return JSONResponse({"error": {"code": "INTERNAL_ERROR"}}, status_code=500)

    app.include_router(
        account_routes.create_router(
            users=users,
            sessions=sessions,
            pepper=pepper,
            browser_origin=browser_origin,
            session_seconds=session_seconds,
            clock=clock,
            account_guard=account_guard,
            memory_view=memory_view,
            memory_replace=memory_replace,
        )
    )
    app.include_router(
        conversation_routes.create_router(
            conversations=conversations,
            messages=messages,
            run_ownership=run_ownership,
            environment=environment,
            work_activities=work_activities,
            processing_tasks=processing_tasks,
            chat_cards=chat_cards,
            chat_action=chat_action,
            durable_chat=durable_chat,
            retain_task=retain_task,
        )
    )
    app.include_router(
        activity_routes.create_router(
            environment=environment,
            work_activities=work_activities,
            processing_tasks=processing_tasks,
        )
    )
    app.include_router(
        run_routes.create_router(
            environment=environment,
            run_ownership=run_ownership,
            runtime_client=runtime_client,
            workflow_catalog=workflow_catalog,
        )
    )
    app.include_router(
        schedule_routes.create_router(
            environment=environment,
            schedules=schedules,
            schedule_history=schedule_history,
            runtime_client=runtime_client,
            clock=clock,
        )
    )
    app.include_router(notification_routes.create_router(notifications=notifications))
    return app
