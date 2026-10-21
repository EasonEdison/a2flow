"""Account routes HTTP routes with explicit typed dependencies."""

from __future__ import annotations

import asyncio
import datetime as dt
import re
from collections.abc import Callable
from typing import ParamSpec, TypeVar

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from skillweave_contracts.user_id import user_id_to_wire

from . import auth
from .account_guard import AccountGuardError, PostgresAccountGuard
from .errors import BsideError
from .identity import SESSION_COOKIE, RequestIdentity, parse_session_token
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
from .route_identity import identity
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
    router = APIRouter()
    _USERNAME = re.compile(r"^[A-Za-z0-9_-]{3,32}$")
    dummy_hash = auth.hash_password("dummy-timing-password", pepper=pepper)

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

    def clear_session(response: JSONResponse) -> None:
        response.delete_cookie(
            SESSION_COOKIE,
            httponly=True,
            samesite="strict",
            secure=browser_origin.startswith("https://"),
            path="/",
        )

    @router.get("/api/memory", response_model=None)
    async def read_memory(identity: RequestIdentity = Depends(identity)) -> MemoryState:
        if memory_view is None:
            raise BsideError("MEMORY_UNAVAILABLE", 503)
        return await asyncio.to_thread(memory_view, identity.userId)

    @router.put("/api/memory", response_model=None)
    async def update_memory(
        body: MemorySettings, identity: RequestIdentity = Depends(identity)
    ) -> MemoryState:
        if memory_replace is None:
            raise BsideError("MEMORY_UNAVAILABLE", 503)
        return await asyncio.to_thread(
            memory_replace,
            identity.userId,
            MemoryState(
                revision=body.revision,
                enabled=body.enabled,
                entries=[
                    {"id": entry.id, "text": entry.text} for entry in body.entries
                ],
            ),
        )

    def _issue_session(response: JSONResponse, user_id: int) -> str:
        token = auth.new_session_token()
        account_storage(
            "bside_session_create",
            sessions.create,
            token_sha256=auth.hash_session_token(token),
            user_id=user_id,
            expires_at=clock() + dt.timedelta(seconds=session_seconds),
        )
        set_session(response, token)
        return token

    def account_storage(
        operation: str, function: Callable[P, R], *args: P.args, **kwargs: P.kwargs
    ) -> R:
        try:
            return function(*args, **kwargs)
        except (BsideError, AccountGuardError):
            raise
        except Exception as error:
            raise PostgresAccountGuard.unavailable(operation, error) from None

    def admit_account(action: str, username: str, request: Request) -> None:
        if account_guard is None:
            raise AccountGuardError("AUTH_GUARD_UNAVAILABLE", 503)
        account_guard.admit(action, username, dict(request.scope))

    @router.post("/api/auth/register", response_model=None)
    def register(request: Request, body: RegisterRequest) -> JSONResponse:
        if not _USERNAME.fullmatch(body.username):
            raise BsideError("INVALID_USERNAME", 400)
        if len(body.password) < 8:
            raise BsideError("INVALID_PASSWORD", 400)
        admit_account("register", body.username, request)
        user_id = account_storage(
            "bside_register",
            users.create,
            username=body.username,
            password_hash=auth.hash_password(body.password, pepper=pepper),
        )
        response = JSONResponse(
            {
                "userId": user_id_to_wire(user_id),
                "username": body.username,
                "role": "USER",
            }
        )
        _issue_session(response, user_id)
        return response

    @router.post("/api/auth/login", response_model=None)
    def login(request: Request, body: LoginRequest) -> JSONResponse:
        admit_account("login", body.username, request)
        record = account_storage("bside_login", users.find_by_username, body.username)
        if record is None:
            auth.verify_password(body.password, dummy_hash, pepper=pepper)
            raise BsideError("INVALID_CREDENTIALS", 401)
        if not auth.verify_password(
            body.password, record["password_hash"], pepper=pepper
        ):
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

    @router.post("/api/auth/logout", response_model=None)
    def logout(request: Request) -> JSONResponse:
        token = parse_session_token(request.cookies.get(SESSION_COOKIE))
        if token is not None:
            account_storage(
                "bside_logout", sessions.delete, auth.hash_session_token(token)
            )
        response = JSONResponse({"ok": True})
        clear_session(response)
        return response

    @router.get("/api/auth/session", response_model=None)
    async def session(identity: RequestIdentity = Depends(identity)) -> JsonObject:
        return {
            "userId": user_id_to_wire(identity.userId),
            "username": identity.username,
            "role": identity.role,
        }

    return router
