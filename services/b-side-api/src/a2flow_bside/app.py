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
from .chat_application import ChatApplicationService
from .chat_runtime import ChatRuntimeFactory
from .chat_wake import ChatWake
from .durable_chat import DurableDispatcher
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

# 保留原模块的模型和工具导出, 拆分路由后兼容已有导入方。
__all__ = [
    "ChatCardAction",
    "ConversationCreate",
    "CronRuleInput",
    "InternalResume",
    "InternalRunStart",
    "LoginRequest",
    "MemoryEntry",
    "MemorySettings",
    "MessageSend",
    "ProcessingResolution",
    "ProcessingTarget",
    "RegisterRequest",
    "RunAction",
    "RunRefCreate",
    "RunReference",
    "RunStart",
    "ScheduleCreate",
    "ScheduleUpdate",
    "WorkflowCardAction",
    "_bounded_run_reference",
    "_iso",
    "_iterate_thread",
    "_schedule_json",
    "create_app",
]

# 这些方法会修改状态, 外部 Cookie 请求必须通过来源检查。
_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _query_allowed(request: Request) -> bool:
    """Allow only declared GET query fields; identity checks still run in each route."""
    # 只为已声明的只读路由开放查询参数, 其他请求拒绝携带查询字段。
    if request.method != "GET":
        return False
    path = request.url.path
    # 消息查询把会话 ID 放在参数中; 仍需在路由内验证归属。
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
    # 进度查询只接受游标和数量, 具体取值交由执行服务校验。
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
    # 重复字段同样拒绝, 避免中间层与路由对同一参数解释不一致。
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
    browser_origins: tuple[str, ...] = (),
    account_guard: PostgresAccountGuard | None = None,
    chat_runtime_factory: ChatRuntimeFactory | None = None,
) -> FastAPI:
    from .config import browser_origin as validate_origin

    # 启动时规范化允许的站点列表, 不能从来访请求扩展来源信任。
    allowed_origins = tuple(
        validate_origin(value) for value in (browser_origins or (browser_origin,))
    )
    if (
        validate_origin(browser_origin) not in allowed_origins
        or len({value.split(":", 1)[0] for value in allowed_origins}) != 1
    ):
        raise RuntimeError("INVALID_BSIDE_BROWSER_ORIGINS")
    # 生产使用 UTC 时钟, 测试可显式注入, 不在业务方法里读取隐式全局时间。
    clock = now or (lambda: dt.datetime.now(dt.UTC))

    # 只有启动成功后的具体服务才可用于请求;此引用只表达 HTTP 就绪状态。
    chat: ChatApplicationService | None = None

    def current_chat() -> ChatApplicationService:
        if chat is None:
            raise BsideError("CHAT_APPLICATION_UNAVAILABLE", 503)
        return chat

    # running loop 内完成构造;同一 wake 注入接收、卡片完成和分发依赖。
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        nonlocal chat
        wake = ChatWake()
        stop = asyncio.Event()
        worker: asyncio.Task[None] | None = None
        try:
            runtime = chat_runtime_factory(wake) if chat_runtime_factory is not None else None
            if runtime is not None:
                await asyncio.to_thread(runtime.durable_chat.check_ready)
                worker = asyncio.create_task(
                    DurableDispatcher(
                        runtime.durable_chat, messages, runtime.runner, processing_tasks
                    ).run(stop)
                )
                # 启动任务先取得一次执行机会;立即失败不能被公布为已就绪。
                await asyncio.sleep(0)
                if worker.done():
                    worker.result()
                    raise RuntimeError("CHAT_DISPATCH_STARTUP_FAILED")
            chat = ChatApplicationService(
                messages=messages,
                environment=environment,
                work_activities=work_activities,
                processing_tasks=processing_tasks,
                durable_chat=runtime.durable_chat if runtime is not None else None,
                chat_cards=runtime.cards if runtime is not None else None,
                chat_action=runtime.action if runtime is not None else None,
            )
            yield
        finally:
            # 先撤销新请求准入,再等待已归属的执行和卡片动作,最终关闭提示。
            chat = None
            stop.set()
            try:
                if worker is not None:
                    await worker
            finally:
                try:
                    while chat_tasks:
                        await asyncio.gather(*tuple(chat_tasks), return_exceptions=True)
                finally:
                    wake.close()

    # 关闭自动文档入口, 后台动作集合由当前应用实例持有。
    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None, lifespan=lifespan)
    chat_tasks: set[asyncio.Task[JsonObject]] = set()
    app.state.chat_tasks = chat_tasks

    # 保留卡片动作任务, 客户端断连也不丢失执行及异常观察者。
    def retain_task(task: asyncio.Task[JsonObject]) -> None:
        chat_tasks.add(task)

        # 任务结束后移除引用, 并读取异常, 避免后台失败无人观察。
        def finished(completed: asyncio.Task[JsonObject]) -> None:
            chat_tasks.discard(completed)
            # Detached HTTP requests still have an owner that observes failures.
            if not completed.cancelled():
                completed.exception()

        task.add_done_callback(finished)

    # 统一入口处理参数、身份伪造和 Origin, 再解析外部登录身份。
    @app.middleware("http")
    async def bside_guard(request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path.startswith("/api"):
            internal = request.url.path.startswith("/api/internal/")
            try:
                # 查询白名单先于身份解析执行, 禁止参数绕过固定路由契约。
                if request.query_params and not _query_allowed(request):
                    raise BsideError("QUERY_PARAMETERS_NOT_ALLOWED", 400)
                # 身份只能来自服务端认证, 主动拒绝客户端注入的用户、角色和环境头。
                lowered = {name.lower() for name in request.headers}
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
                # 内部调用走独立凭据验证; 外部写请求必须匹配可信浏览器来源。
                if request.method in _UNSAFE_METHODS and not internal:
                    require_origin(request.headers, allowed_origins)
            except BsideError as error:
                return JSONResponse({"error": {"code": error.code}}, status_code=error.status)
            # 会话查询放在线程池, 解析结果写入本请求 scope 供路由依赖使用。
            if not internal:
                try:
                    request.scope["a2flow.bside.identity"] = await run_in_threadpool(
                        resolve_identity,
                        request.cookies.get(SESSION_COOKIE),
                        sessions=sessions,
                        now=clock,
                    )
                # 认证存储不可用时拒绝请求, 不把存储故障降级成匿名继续。
                except Exception as error:
                    failure = PostgresAccountGuard.unavailable("bside_session", error)
                    return JSONResponse(
                        {"error": {"code": failure.code}},
                        status_code=failure.status,
                        headers=failure.headers(),
                    )
        return await call_next(request)

    # 账号防护错误保留 Retry-After 和定位号, 其他异常不公开内部详情。
    @app.exception_handler(AccountGuardError)
    async def account_guard_failure(request: Request, error: AccountGuardError) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": error.code}},
            status_code=error.status,
            headers=error.headers(),
        )

    # 产品可预期错误只返回稳定错误码和指定 HTTP 状态。
    @app.exception_handler(BsideError)
    async def bside_failure(request: Request, error: BsideError) -> JSONResponse:
        return JSONResponse({"error": {"code": error.code}}, status_code=error.status)

    # 执行服务错误沿用已清洗的协议错误码, 不暴露远端响应原文。
    @app.exception_handler(RemoteRuntimeError)
    async def runtime_failure(request: Request, error: RemoteRuntimeError) -> JSONResponse:
        return JSONResponse({"error": {"code": error.code}}, status_code=error.status)

    # 字段解析错误统一为输入错误, 避免向浏览器回显敏感输入。
    @app.exception_handler(RequestValidationError)
    async def invalid_input(request: Request, error: RequestValidationError) -> JSONResponse:
        return JSONResponse({"error": {"code": "INVALID_INPUT"}}, status_code=400)

    # 未知异常统一投影为内部错误, 不能直接拼接异常文本。
    @app.exception_handler(Exception)
    async def unexpected(request: Request, error: Exception) -> JSONResponse:
        return JSONResponse({"error": {"code": "INTERNAL_ERROR"}}, status_code=500)

    app.include_router(
        # 账号路由获得会话、安全配置和可选记忆接口。
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
        # 会话路由获得消息、卡片动作及持久化准入, 不接管模型循环。
        conversation_routes.create_router(
            conversations=conversations,
            messages=messages,
            run_ownership=run_ownership,
            chat_service=current_chat,
            retain_task=retain_task,
        )
    )
    app.include_router(
        # 动态与处理任务共用可信环境和用户隔离的仓库。
        activity_routes.create_router(
            environment=environment,
            work_activities=work_activities,
            processing_tasks=processing_tasks,
        )
    )
    app.include_router(
        # 运行控制通过显式客户端转发, 归属验证仍保留在产品侧。
        run_routes.create_router(
            environment=environment,
            run_ownership=run_ownership,
            runtime_client=runtime_client,
            workflow_catalog=workflow_catalog,
        )
    )
    app.include_router(
        # 定时规则与调度历史交给独立路由, 统一注入时钟。
        schedule_routes.create_router(
            environment=environment,
            schedules=schedules,
            schedule_history=schedule_history,
            runtime_client=runtime_client,
            clock=clock,
        )
    )
    # 通知只处理用户可见状态, 阅读通知不等于处理业务异常。
    app.include_router(notification_routes.create_router(notifications=notifications))
    return app
