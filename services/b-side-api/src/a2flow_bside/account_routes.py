"""Account routes HTTP routes with explicit typed dependencies."""

from __future__ import annotations

import asyncio
import datetime as dt
import re
from collections.abc import Callable
from typing import ParamSpec, TypeVar

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from skillweave_contracts.user_id import user_id_to_wire

from . import auth
from .account_guard import AccountGuardError, PostgresAccountGuard
from .errors import BsideError
from .identity import SESSION_COOKIE, parse_session_token
from .repositories import (
    SessionsRepository,
    UsersRepository,
)
from .route_dependencies import (
    JsonObject,
    MemoryReplace,
    MemoryState,
    MemoryView,
)
from .route_identity import CurrentIdentity
from .route_models import (
    LoginRequest,
    MemorySettings,
    RegisterRequest,
)

P = ParamSpec("P")
R = TypeVar("R")


def create_router(
    *,
    users: UsersRepository,
    sessions: SessionsRepository,
    pepper: str,
    browser_origin: str,
    session_seconds: int,
    clock: Callable[[], dt.datetime],
    account_guard: PostgresAccountGuard | None,
    memory_view: MemoryView | None,
    memory_replace: MemoryReplace | None,
) -> APIRouter:
    # 账号路由只接收装配好的依赖, 不在请求处理中重新创建存储连接配置。
    router = APIRouter()
    _USERNAME = re.compile(r"^[A-Za-z0-9_-]{3,32}$")
    # 预先生成占位摘要, 使不存在的账号也执行密码派生, 减少时序差异。
    dummy_hash = auth.hash_password("dummy-timing-password", pepper=pepper)

    # Cookie 禁止脚本读取并限制同站发送; HTTPS 站点同时启用 Secure。
    def set_session(response: JSONResponse, token: str) -> None:
        response.set_cookie(
            SESSION_COOKIE,
            token,
            max_age=session_seconds,
            httponly=True,
            samesite="strict",
            secure=browser_origin.startswith("https://"),
            path="/",
        )

    # 清除 Cookie 时复用相同作用域, 确保浏览器删除的是实际会话凭据。
    def clear_session(response: JSONResponse) -> None:
        response.delete_cookie(
            SESSION_COOKIE,
            httponly=True,
            samesite="strict",
            secure=browser_origin.startswith("https://"),
            path="/",
        )

    # 个人记忆依赖可信登录身份, 未装配记忆服务时明确返回不可用。
    @router.get("/api/memory", response_model=None)
    async def read_memory(*, identity: CurrentIdentity) -> MemoryState:
        if memory_view is None:
            raise BsideError("MEMORY_UNAVAILABLE", 503)
        return await asyncio.to_thread(memory_view, identity.userId)

    # 更新携带原 revision 交给存储侧检查, 避免并发覆盖个人设置。
    @router.put("/api/memory", response_model=None)
    async def update_memory(*, body: MemorySettings, identity: CurrentIdentity) -> MemoryState:
        if memory_replace is None:
            raise BsideError("MEMORY_UNAVAILABLE", 503)
        # 同步记忆写入在线程中执行, 不阻塞异步 HTTP 事件循环。
        return await asyncio.to_thread(
            memory_replace,
            identity.userId,
            MemoryState(
                revision=body.revision,
                enabled=body.enabled,
                entries=[{"id": entry.id, "text": entry.text} for entry in body.entries],
            ),
        )

    # 先保存令牌摘要及过期时间, 再向浏览器签发原始令牌。
    def _issue_session(response: JSONResponse, user_id: int) -> str:
        token = auth.new_session_token()
        account_storage(
            "bside_session_create",
            sessions.create,
            token_sha256=auth.hash_session_token(token),
            user_id=user_id,
            expires_at=clock() + dt.timedelta(seconds=session_seconds),
        )
        # 会话落库成功后才设置 Cookie, 避免发出没有服务端记录的凭据。
        set_session(response, token)
        return token

    # 保留已知业务错误, 其他存储异常转换为不泄露内部详情的认证故障。
    def account_storage(
        operation: str, function: Callable[P, R], *args: P.args, **kwargs: P.kwargs
    ) -> R:
        try:
            return function(*args, **kwargs)
        except (BsideError, AccountGuardError):
            raise
        except Exception as error:
            raise PostgresAccountGuard.unavailable(operation, error) from None

    # 未装配防护组件时关闭认证入口, 不能跳过限流继续登录或注册。
    def admit_account(action: str, username: str, request: Request) -> None:
        if account_guard is None:
            raise AccountGuardError("AUTH_GUARD_UNAVAILABLE", 503)
        account_guard.admit(action, username, dict(request.scope))

    # 注册先做字段校验与准入, 再计算密码摘要和建立账号。
    @router.post("/api/auth/register", response_model=None)
    def register(*, request: Request, body: RegisterRequest) -> JSONResponse:
        if not _USERNAME.fullmatch(body.username):
            raise BsideError("INVALID_USERNAME", 400)
        if len(body.password) < 8:
            raise BsideError("INVALID_PASSWORD", 400)
        admit_account("register", body.username, request)
        # 角色由服务端创建规则决定, 注册请求不能自行申请管理员身份。
        user_id = account_storage(
            "bside_register",
            users.create,
            username=body.username,
            password_hash=auth.hash_password(body.password, pepper=pepper),
        )
        # 响应返回可展示的账号信息, 不包含密码摘要。
        response = JSONResponse(
            {
                "userId": user_id_to_wire(user_id),
                "username": body.username,
                "role": "USER",
            }
        )
        _issue_session(response, user_id)
        return response

    # 登录尝试先计入共享预算, 成功与失败都不能绕过防护。
    @router.post("/api/auth/login", response_model=None)
    def login(*, request: Request, body: LoginRequest) -> JSONResponse:
        admit_account("login", body.username, request)
        record = account_storage("bside_login", users.find_by_username, body.username)
        # 账号不存在时仍执行一次占位验证, 并返回相同的凭据错误。
        if record is None:
            auth.verify_password(body.password, dummy_hash, pepper=pepper)
            raise BsideError("INVALID_CREDENTIALS", 401)
        # 真实密码验证通过后才创建新会话, 角色取自数据库记录。
        if not auth.verify_password(body.password, record["password_hash"], pepper=pepper):
            raise BsideError("INVALID_CREDENTIALS", 401)
        response = JSONResponse(
            {
                "userId": user_id_to_wire(record["user_id"]),
                "username": record["username"],
                "role": record["role"],
            }
        )
        _issue_session(response, record["user_id"])
        return response

    # 退出先删除服务端会话记录, 再清理浏览器 Cookie。
    @router.post("/api/auth/logout", response_model=None)
    def logout(*, request: Request) -> JSONResponse:
        token = parse_session_token(request.cookies.get(SESSION_COOKIE))
        if token is not None:
            account_storage("bside_logout", sessions.delete, auth.hash_session_token(token))
        response = JSONResponse({"ok": True})
        clear_session(response)
        return response

    # 会话查询仅投影统一认证依赖已经解析的身份。
    @router.get("/api/auth/session", response_model=None)
    async def session(*, identity: CurrentIdentity) -> JsonObject:
        return {
            "userId": user_id_to_wire(identity.userId),
            "username": identity.username,
            "role": identity.role,
        }

    return router
