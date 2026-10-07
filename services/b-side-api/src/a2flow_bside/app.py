"""B-side FastAPI application: accounts, chat, workflows, runs, schedules,
notifications. All dependencies are injected; create_app performs no I/O."""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import hmac
import queue
import re
import threading
import uuid
from contextlib import asynccontextmanager
from typing import Callable, Literal

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, ConfigDict, field_validator
from skillweave_contracts.user_id import user_id_from_wire, user_id_to_wire

from . import auth
from .chat_runner import ChatRunner
from .chat_delivery import ChatDelivery, ChatStreamingResponse
from .chat_history import has_card_references, hydrate_history
from .errors import BsideError, RemoteRuntimeError
from .identity import (
    SESSION_COOKIE,
    RequestIdentity,
    parse_session_token,
    require_origin,
    resolve_identity,
)
from .runtime_client import RuntimeClient
from .scheduling import ScheduleRuleError, next_run_after, parse_rule

_USERNAME = re.compile(r"^[A-Za-z0-9_-]{3,32}$")
_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class MemoryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    text: str = Field(min_length=1, max_length=1000)


class MemorySettings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    revision: int = Field(ge=0)
    enabled: bool
    entries: list[MemoryEntry] = Field(max_length=20)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class MessageSend(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class RunStart(BaseModel):
    workflowKey: str = Field(min_length=1, max_length=256)
    input: dict[str, object] | str


class RunRefCreate(BaseModel):
    runId: str = Field(min_length=1, max_length=256)


class InternalRunStart(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    requestId: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    environment: str = Field(pattern=r"^(PRT|ONLINE)$")
    userId: int
    workflowKey: str = Field(min_length=1, max_length=256)
    input: dict[str, object] | str

    @field_validator("userId", mode="before")
    @classmethod
    def parse_user_id(cls, value: object) -> int:
        return user_id_from_wire(value)


class RunAction(BaseModel):
    nodeId: str = Field(min_length=1, max_length=256)
    interactionId: str = Field(min_length=1, max_length=256)
    actionName: str = Field(min_length=1, max_length=256)
    inputs: dict[str, object] = Field(default_factory=dict)


class ChatCardAction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    requestId: str = Field(min_length=1, max_length=128)
    actionName: str = Field(min_length=1, max_length=128)
    inputs: dict[str, object]


class WorkflowCardAction(ChatCardAction):
    nodeId: str = Field(min_length=1, max_length=256)
    interactionId: str = Field(min_length=1, max_length=256)


class InternalResume(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    userId: int
    environment: Literal["PRT", "ONLINE"]
    requestId: str = Field(min_length=1, max_length=128)
    actionRequestId: str = Field(min_length=1, max_length=128)
    nodeId: str = Field(min_length=1, max_length=256)
    interactionId: str = Field(min_length=1, max_length=256)

    @field_validator("userId", mode="before")
    @classmethod
    def parse_user_id(cls, value: object) -> int:
        return user_id_from_wire(value)


class CronRuleInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expression: str = Field(min_length=1, max_length=128)


class ScheduleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    workflowKey: str = Field(min_length=1, max_length=256)
    ruleType: Literal["cron"]
    ruleJson: CronRuleInput
    timezone: str | None = Field(default=None, max_length=64)
    inputText: str = Field(min_length=1, max_length=4000)


class ScheduleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    enabled: bool | None = None
    ruleType: Literal["cron"] | None = None
    ruleJson: CronRuleInput | None = None
    timezone: str | None = Field(default=None, max_length=64)
    inputText: str | None = Field(default=None, min_length=1, max_length=4000)


def _iterate_thread(sync_iter):
    """Pump a blocking generator into an async stream from a worker thread."""
    pending = queue.Queue()

    def produce():
        try:
            for chunk in sync_iter:
                pending.put(("chunk", chunk))
            pending.put(("done", None))
        except Exception as exc:  # noqa: BLE001
            pending.put(("error", exc))

    threading.Thread(target=produce, daemon=True).start()

    async def consume():
        while True:
            kind, payload = await asyncio.to_thread(pending.get)
            if kind == "chunk":
                yield payload
            elif kind == "error":
                raise payload
            else:
                return

    return consume()


def _iso(value):
    if isinstance(value, dt.datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _iso(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_iso(item) for item in value]
    return value


def _schedule_json(row: dict) -> dict:
    return {
        "id": row["id"],
        "workflowKey": row["workflow_key"],
        "environment": row["environment"],
        "ruleType": row["rule_type"],
        "ruleJson": row["rule_json"],
        "timezone": row["timezone"],
        "inputText": row["input_text"],
        "enabled": row["enabled"],
        "nextRunAt": _iso(row["next_run_at"]),
        "lastRunAt": _iso(row["last_run_at"]),
        "createdAt": _iso(row["created_at"]),
    }


def create_app(
    *,
    users,
    sessions,
    conversations,
    messages,
    schedules,
    notifications,
    run_ownership,
    runtime_client: RuntimeClient,
    chat_runner: ChatRunner,
    workflow_catalog: Callable[[int], list[dict]],
    pepper: str,
    browser_origin: str,
    environment: str,
    session_seconds: int,
    now: Callable[[], dt.datetime] | None = None,
    memory_view=None,
    memory_replace=None,
    chat_cards=None,
    chat_action=None,
    browser_origins: tuple[str, ...] = (),
):
    from .config import browser_origin as validate_origin
    allowed_origins = tuple(validate_origin(value) for value in (browser_origins or (browser_origin,)))
    if (validate_origin(browser_origin) not in allowed_origins or
            len({value.split(":", 1)[0] for value in allowed_origins}) != 1):
        raise RuntimeError("INVALID_BSIDE_BROWSER_ORIGINS")
    clock = now or (lambda: dt.datetime.now(dt.timezone.utc))
    dummy_hash = auth.hash_password("dummy-timing-password", pepper=pepper)
    @asynccontextmanager
    async def lifespan(app):
        yield
        # Graceful shutdown waits for owned turns, not HTTP subscribers.
        if app.state.chat_tasks:
            await asyncio.gather(*app.state.chat_tasks, return_exceptions=True)

    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.chat_tasks = set()

    def identity(request: Request) -> RequestIdentity:
        value = request.scope.get("a2flow.bside.identity")
        if not isinstance(value, RequestIdentity):
            raise BsideError("AUTHENTICATION_REQUIRED", 401)
        return value

    def set_session(response: JSONResponse, token: str) -> None:
        response.set_cookie(
            SESSION_COOKIE, token, max_age=session_seconds, httponly=True,
            samesite="strict", secure=browser_origin.startswith("https://"),
            path="/")

    def clear_session(response: JSONResponse) -> None:
        response.delete_cookie(SESSION_COOKIE, httponly=True,
                               samesite="strict",
                               secure=browser_origin.startswith("https://"),
                               path="/")

    @app.get("/api/memory")
    async def read_memory(identity: RequestIdentity = Depends(identity)):
        if memory_view is None:
            raise BsideError("MEMORY_UNAVAILABLE", 503)
        return await asyncio.to_thread(memory_view, identity.userId)

    @app.put("/api/memory")
    async def update_memory(body: MemorySettings,
                            identity: RequestIdentity = Depends(identity)):
        if memory_replace is None:
            raise BsideError("MEMORY_UNAVAILABLE", 503)
        return await asyncio.to_thread(memory_replace, identity.userId, body.model_dump())

    @app.middleware("http")
    async def bside_guard(request: Request, call_next):
        if request.url.path.startswith("/api"):
            internal = request.url.path.startswith("/api/internal/")
            try:
                if request.query_params:
                    raise BsideError("QUERY_PARAMETERS_NOT_ALLOWED", 400)
                lowered = {name.lower() for name in request.headers.keys()}
                if lowered & {
                        "x-a2flow-environment", "x-a2flow-role",
                        "x-a2flow-roles", "x-a2flow-user-id", "x-environment",
                        "x-role", "x-roles", "x-user-id"}:
                    raise BsideError("IDENTITY_FIELDS_NOT_ALLOWED", 400)
                if request.method in _UNSAFE_METHODS and not internal:
                    require_origin(request.headers, allowed_origins)
            except BsideError as error:
                return JSONResponse({"error": {"code": error.code}},
                                    status_code=error.status)
            if not internal:
                request.scope["a2flow.bside.identity"] = resolve_identity(
                    request.cookies.get(SESSION_COOKIE), sessions=sessions,
                    now=clock)
        return await call_next(request)

    @app.exception_handler(BsideError)
    async def bside_failure(request: Request, error: BsideError):
        return JSONResponse({"error": {"code": error.code}},
                            status_code=error.status)

    @app.exception_handler(RemoteRuntimeError)
    async def runtime_failure(request: Request, error: RemoteRuntimeError):
        return JSONResponse({"error": {"code": error.code}},
                            status_code=error.status)

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request: Request, error):
        return JSONResponse({"error": {"code": "INVALID_INPUT"}},
                            status_code=400)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, error):
        return JSONResponse({"error": {"code": "INTERNAL_ERROR"}},
                            status_code=500)

    def _issue_session(response: JSONResponse, user_id: int) -> str:
        token = auth.new_session_token()
        sessions.create(
            token_sha256=auth.hash_session_token(token),
            user_id=user_id,
            expires_at=clock() + dt.timedelta(seconds=session_seconds))
        set_session(response, token)
        return token

    # ---- auth ----

    @app.post("/api/auth/register")
    async def register(request: Request, body: RegisterRequest):
        if not _USERNAME.fullmatch(body.username):
            raise BsideError("INVALID_USERNAME", 400)
        if len(body.password) < 8:
            raise BsideError("INVALID_PASSWORD", 400)
        user_id = users.create(
            username=body.username,
            password_hash=auth.hash_password(body.password, pepper=pepper))
        response = JSONResponse(
            {"userId": user_id_to_wire(user_id), "username": body.username, "role": "USER"})
        _issue_session(response, user_id)
        return response

    @app.post("/api/auth/login")
    async def login(request: Request, body: LoginRequest):
        record = users.find_by_username(body.username)
        if record is None:
            auth.verify_password(body.password, dummy_hash, pepper=pepper)
            raise BsideError("INVALID_CREDENTIALS", 401)
        if not auth.verify_password(
                body.password, record["password_hash"], pepper=pepper):
            raise BsideError("INVALID_CREDENTIALS", 401)
        response = JSONResponse({
            "userId": user_id_to_wire(record["user_id"]),
            "username": record["username"],
            "role": record["role"],
        })
        _issue_session(response, record["user_id"])
        return response

    @app.post("/api/auth/logout")
    async def logout(request: Request):
        token = parse_session_token(request.cookies.get(SESSION_COOKIE))
        if token is not None:
            sessions.delete(auth.hash_session_token(token))
        response = JSONResponse({"ok": True})
        clear_session(response)
        return response

    @app.get("/api/auth/session")
    async def session(identity: RequestIdentity = Depends(identity)):
        return {"userId": user_id_to_wire(identity.userId), "username": identity.username,
                "role": identity.role}

    # ---- conversations ----

    @app.get("/api/conversations")
    async def list_conversations(
            identity: RequestIdentity = Depends(identity)):
        return {"conversations": [
            {"id": row["id"], "title": row["title"],
             "createdAt": _iso(row["created_at"])}
            for row in conversations.list_for(identity.userId)]}

    @app.post("/api/conversations")
    async def create_conversation(
            body: ConversationCreate,
            identity: RequestIdentity = Depends(identity)):
        row = conversations.create(user_id=identity.userId, title=body.title)
        return {"id": row["id"], "title": row["title"],
                "createdAt": _iso(row["created_at"])}

    @app.get("/api/conversations/{conversation_id}/messages")
    async def conversation_messages(
            conversation_id: int,
            identity: RequestIdentity = Depends(identity)):
        owner = conversations.owner(conversation_id)
        if owner is None or owner != identity.userId:
            raise BsideError("NOT_FOUND", 404)
        rows = messages.list_for(conversation_id)
        cards = []
        if chat_cards is not None:
            try:
                cards = await asyncio.to_thread(
                    chat_cards, identity.userId, str(conversation_id),
                )
                if not isinstance(cards, list):
                    raise TypeError("CHAT_CARDS_RESULT_INVALID")
            except Exception as error:
                raise BsideError("CHAT_HISTORY_CARDS_UNAVAILABLE", 503) from error
        elif has_card_references(rows):
            raise BsideError("CHAT_HISTORY_CARDS_UNAVAILABLE", 503)
        hydrated, unassigned_cards = hydrate_history(rows, cards)
        return {"messages": [
            {"id": str(row["id"]), "role": row["role"],
             "content": row["content"], "refKind": row["ref_kind"],
             "refId": row["ref_id"], "createdAt": _iso(row["created_at"])}
            for row in hydrated], "unassignedCards": unassigned_cards}

    @app.post("/api/conversations/{conversation_id}/messages")
    async def send_message(
            conversation_id: int, body: MessageSend,
            identity: RequestIdentity = Depends(identity)):
        owner = conversations.owner(conversation_id)
        if owner is None or owner != identity.userId:
            raise BsideError("NOT_FOUND", 404)
        input_message = messages.append(
            conversation_id=conversation_id, role="user",
            content={"text": body.text, "delivery": "submitted"})

        assistant_message = messages.append(
            conversation_id=conversation_id, role="assistant",
            content={"text": "", "delivery": "running", "parts": []})
        delivery = ChatDelivery(
            messages=messages, runner=chat_runner, user_id=identity.userId,
            conversation_id=conversation_id, text=body.text,
            input_message=input_message, assistant_message=assistant_message)
        task = asyncio.create_task(delivery.produce())
        app.state.chat_tasks.add(task)
        task.add_done_callback(app.state.chat_tasks.discard)
        return ChatStreamingResponse(delivery)

    @app.get("/api/conversations/{conversation_id}/cards")
    async def conversation_cards(conversation_id: int,
                                 identity: RequestIdentity = Depends(identity)):
        if conversations.owner(conversation_id) != identity.userId:
            raise BsideError("CONVERSATION_NOT_FOUND", 404)
        if chat_cards is None:
            raise BsideError("CHAT_APPLICATION_UNAVAILABLE", 503)
        return {"cards": await asyncio.to_thread(
            chat_cards, identity.userId, str(conversation_id))}

    @app.post("/api/conversations/{conversation_id}/cards/{card_id}/actions")
    async def conversation_card_action(conversation_id: int, card_id: str,
                                       body: ChatCardAction,
                                       identity: RequestIdentity = Depends(identity)):
        if conversations.owner(conversation_id) != identity.userId:
            raise BsideError("CONVERSATION_NOT_FOUND", 404)
        if chat_action is None:
            raise BsideError("CHAT_APPLICATION_UNAVAILABLE", 503)
        return await asyncio.to_thread(chat_action, identity.userId,
            str(conversation_id), card_id, body.model_dump())

    @app.post("/api/conversations/{conversation_id}/run-refs")
    async def attach_run(
            conversation_id: int, body: RunRefCreate,
            identity: RequestIdentity = Depends(identity)):
        owner = conversations.owner(conversation_id)
        if owner is None or owner != identity.userId:
            raise BsideError("NOT_FOUND", 404)
        if not run_ownership.owned_by(identity.userId, body.runId):
            raise BsideError("NOT_FOUND", 404)
        row = messages.append(
            conversation_id=conversation_id, role="assistant",
            content={"text": "工作流已启动，等待你的确认。"},
            ref_kind="run", ref_id=body.runId)
        return {"id": row["id"]}

    # ---- workflows catalog ----

    @app.get("/api/workflows")
    async def workflows(identity: RequestIdentity = Depends(identity)):
        return {"workflows": list(workflow_catalog(identity.userId))}

    # ---- runs (proxied runtime control; ownership recorded per control id) ----

    def _require_run_owner(control_id: str, owner_user: int) -> None:
        recorded = run_ownership.owner(control_id)
        if recorded is None:
            raise BsideError("NOT_FOUND", 404)
        if recorded != owner_user:
            raise BsideError("NOT_FOUND", 404)

    def _runtime(user_id: int):
        return runtime_client.for_user(user_id, environment)

    def _resolve_run_id(control_id: str, user_id: int) -> str:
        view = _runtime(user_id).control(control_id)
        run_id = view.get("runId") or view.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            raise BsideError("RUN_NOT_RESOLVED", 409)
        run_ownership.bind_run_id(control_id, run_id)
        return run_id

    def _resolve_inputs(workflow_key: str, user_id: int, raw_input):
        if not isinstance(raw_input, str):
            return raw_input
        # Scheduled runs carry a plain prompt; wrap it into the workflow's
        # single required string property when it has one.
        entry = next(
            (item for item in workflow_catalog(user_id)
             if item.get("definitionKey") == workflow_key),
            None,
        )
        if entry is None:
            raise BsideError("WORKFLOW_NOT_FOUND", 404)
        schema = entry.get("inputSchema") or {}
        required = schema.get("required") or []
        properties = schema.get("properties") or {}
        if (len(required) == 1
                and properties.get(required[0], {}).get("type") == "string"):
            return {required[0]: raw_input}
        raise BsideError("INVALID_INPUT", 400)

    def _start_for(user_id: int, workflow_key: str, raw_input) -> dict:
        control_id = uuid.uuid4().hex
        inputs = _resolve_inputs(workflow_key, user_id, raw_input)
        _runtime(user_id).start(control_id, workflow_key, inputs)
        run_ownership.create(
            control_id=control_id, user_id=user_id,
            workflow_key=workflow_key)
        return {"controlRequestId": control_id, "status": "SUBMITTED"}

    @app.post("/api/runs")
    async def start_run(body: RunStart,
                        identity: RequestIdentity = Depends(identity)):
        return _start_for(identity.userId, body.workflowKey, body.input)

    def _require_internal(request: Request) -> None:
        token = os.environ.get("A2FLOW_BSIDE_INTERNAL_TOKEN")
        if not token:
            raise BsideError("INTERNAL_API_DISABLED", 503)
        provided = request.headers.get("x-a2flow-internal-token") or ""
        if not hmac.compare_digest(provided, token):
            raise BsideError("INTERNAL_TOKEN_REQUIRED", 401)

    @app.post("/api/internal/runs")
    async def internal_start(request: Request, body: InternalRunStart):
        _require_internal(request)
        if body.environment != environment:
            raise BsideError("ENVIRONMENT_MISMATCH", 400)
        inputs = _resolve_inputs(body.workflowKey, body.userId, body.input)
        # Commit ownership before calling Runtime. A timeout must not cause a
        # new control ID; Runtime's durable allocation deduplicates this ID.
        await asyncio.to_thread(
            run_ownership.reserve, control_id=body.requestId,
            user_id=body.userId, workflow_key=body.workflowKey,
        )
        await asyncio.to_thread(
            _runtime(body.userId).start, body.requestId, body.workflowKey, inputs,
        )
        return {"controlRequestId": body.requestId, "status": "SUBMITTED"}

    @app.get("/api/internal/runs/{request_id}")
    async def internal_run_status(request: Request, request_id: str):
        _require_internal(request)
        owner = run_ownership.owner(request_id)
        if owner is None:
            raise BsideError("NOT_FOUND", 404)
        view = await asyncio.to_thread(_runtime(owner).control, request_id)
        return {"controlRequestId": request_id, "status": "SUBMITTED", "view": view}

    @app.get("/api/runs/{control_id}/cards")
    async def workflow_cards(
        control_id: str, identity: RequestIdentity = Depends(identity),
    ):
        _require_run_owner(control_id, identity.userId)
        try:
            run_id = await asyncio.to_thread(_resolve_run_id, control_id, identity.userId)
        except BsideError as error:
            if error.code == "RUN_NOT_RESOLVED":
                return {"cards": []}
            raise
        except RemoteRuntimeError as error:
            if error.code == "CONTROL_NOT_FOUND":
                return {"cards": []}
            raise
        return await asyncio.to_thread(_runtime(identity.userId).cards, run_id)

    @app.post("/api/internal/runs/{run_id}/cards/{card_id}/resume")
    async def internal_resume(
        request: Request, run_id: str, card_id: str, body: InternalResume,
    ):
        _require_internal(request)
        if body.environment != environment:
            raise BsideError("ENVIRONMENT_MISMATCH", 400)
        if run_ownership.owner_by_run(run_id) != body.userId:
            raise BsideError("NOT_FOUND", 404)
        return await asyncio.to_thread(
            _runtime(body.userId).resume_card, run_id, card_id,
            body.model_dump(exclude={"userId", "environment"}),
        )

    @app.get("/api/internal/run-controls/{request_id}")
    async def internal_control_status(
        request: Request, request_id: str, userId: str, environment: str,
    ):
        _require_internal(request)
        owner = user_id_from_wire(userId)
        if environment not in {"PRT", "ONLINE"}:
            raise BsideError("ENVIRONMENT_MISMATCH", 400)
        view = await asyncio.to_thread(
            runtime_client.for_user(owner, environment).control, request_id,
        )
        return {"controlRequestId": request_id, "status": "SUBMITTED", "view": view}

    @app.post("/api/runs/{control_id}/cards/{card_id}/actions")
    async def workflow_card_action(
        control_id: str, card_id: str, body: WorkflowCardAction,
        identity: RequestIdentity = Depends(identity),
    ):
        _require_run_owner(control_id, identity.userId)
        run_id = await asyncio.to_thread(_resolve_run_id, control_id, identity.userId)
        return await asyncio.to_thread(
            _runtime(identity.userId).card_action, run_id, card_id, body.model_dump(),
        )

    @app.get("/api/runs")
    async def list_runs(identity: RequestIdentity = Depends(identity)):
        items = []
        for row in run_ownership.list_for(identity.userId):
            item = {
                "controlRequestId": row["control_id"],
                "workflowKey": row["workflow_key"],
                "createdAt": _iso(row["created_at"]),
            }
            try:
                item["view"] = _runtime(identity.userId).control(row["control_id"])
            except RemoteRuntimeError:
                item["view"] = None
            if item["view"] and item["view"].get("runId"):
                run_ownership.bind_run_id(
                    row["control_id"], item["view"]["runId"])
            items.append(item)
        return {"runs": items}

    @app.get("/api/runs/{run_id}")
    async def run_detail(run_id: str,
                         identity: RequestIdentity = Depends(identity)):
        _require_run_owner(run_id, identity.userId)
        receipt = _runtime(identity.userId).control(run_id)
        runtime_run_id = receipt.get("runId") if isinstance(receipt, dict) \
            else None
        if runtime_run_id:
            try:
                return _runtime(identity.userId).view(runtime_run_id)
            except RemoteRuntimeError:
                pass
        return receipt

    @app.post("/api/runs/{run_id}/stop")
    async def stop_run(run_id: str,
                       identity: RequestIdentity = Depends(identity)):
        _require_run_owner(run_id, identity.userId)
        runtime_run_id = _resolve_run_id(run_id, identity.userId)
        return _runtime(identity.userId).stop(
            runtime_run_id, uuid.uuid4().hex)

    @app.post("/api/runs/{run_id}/actions")
    async def run_action(run_id: str, body: RunAction,
                         identity: RequestIdentity = Depends(identity)):
        _require_run_owner(run_id, identity.userId)
        runtime_run_id = _resolve_run_id(run_id, identity.userId)
        return StreamingResponse(
            _iterate_thread(_runtime(identity.userId).action_stream(
                runtime_run_id, body.nodeId, {
                    "controlRequestId": uuid.uuid4().hex,
                    "inputs": body.inputs,
                    "interactionId": body.interactionId,
                    "actionName": body.actionName,
                })),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"})

    @app.get("/api/runs/{run_id}/surface")
    async def run_surface(run_id: str,
                          identity: RequestIdentity = Depends(identity)):
        _require_run_owner(run_id, identity.userId)
        runtime_run_id = _resolve_run_id(run_id, identity.userId)
        return StreamingResponse(
            _iterate_thread(_runtime(identity.userId).surface_stream(runtime_run_id)),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"})

    # ---- schedules ----

    def _computed_next(rule_type: str, rule_json: dict,
                       timezone: str) -> dt.datetime:
        try:
            rule = parse_rule(rule_type, rule_json, timezone, clock())
        except ScheduleRuleError as error:
            raise BsideError("INVALID_SCHEDULE", 400) from None
        next_at = next_run_after(rule, clock())
        if next_at is None:
            raise BsideError("INVALID_SCHEDULE", 400)
        return next_at

    @app.post("/api/schedules")
    async def create_schedule(
            body: ScheduleCreate,
            identity: RequestIdentity = Depends(identity)):
        timezone = body.timezone or "Asia/Shanghai"
        next_at = _computed_next(body.ruleType, body.ruleJson.model_dump(), timezone)
        row = schedules.create(
            user_id=identity.userId, workflow_key=body.workflowKey,
            environment=environment, rule_type=body.ruleType,
            rule_json=body.ruleJson.model_dump(), timezone=timezone,
            input_text=body.inputText, next_run_at=next_at)
        return _schedule_json(row)

    @app.get("/api/schedules")
    async def list_schedules(
            identity: RequestIdentity = Depends(identity)):
        return {"schedules": [
            _schedule_json(row)
            for row in schedules.list_for(identity.userId)]}

    @app.patch("/api/schedules/{schedule_id}")
    async def update_schedule(
            schedule_id: int, body: ScheduleUpdate,
            identity: RequestIdentity = Depends(identity)):
        row = schedules.get(schedule_id)
        if row is None or row["user_id"] != identity.userId:
            raise BsideError("NOT_FOUND", 404)
        fields = {}
        if body.enabled is not None:
            fields["enabled"] = body.enabled
        if body.inputText is not None:
            fields["input_text"] = body.inputText
        rule_changed = (body.ruleType is not None
                        or body.ruleJson is not None
                        or body.timezone is not None)
        reenabled = body.enabled is True and not row["enabled"]
        if rule_changed or reenabled:
            rule_type = body.ruleType or row["rule_type"]
            rule_json = body.ruleJson.model_dump() if body.ruleJson is not None \
                else row["rule_json"]
            timezone = body.timezone or row["timezone"]
            fields["rule_type"] = rule_type
            fields["rule_json"] = rule_json
            fields["timezone"] = timezone
            fields["next_run_at"] = _computed_next(
                rule_type, rule_json, timezone)
        updated = schedules.update(
            schedule_id, identity.userId, **fields)
        if updated is None:
            raise BsideError("NOT_FOUND", 404)
        return _schedule_json(updated)

    @app.delete("/api/schedules/{schedule_id}")
    async def delete_schedule(
            schedule_id: int,
            identity: RequestIdentity = Depends(identity)):
        if not schedules.delete(schedule_id, identity.userId):
            raise BsideError("NOT_FOUND", 404)
        return {"ok": True}

    # ---- notifications ----

    @app.get("/api/notifications")
    async def list_notifications(
            identity: RequestIdentity = Depends(identity)):
        return {"notifications": [
            {"id": row["id"], "kind": row["kind"], "title": row["title"],
             "body": row["body"], "refType": row["ref_type"],
             "refId": row["ref_id"], "read": row["read"],
             "createdAt": _iso(row["created_at"])}
            for row in notifications.list_for(identity.userId)]}

    @app.post("/api/notifications/{notification_id}/read")
    async def mark_notification_read(
            notification_id: int,
            identity: RequestIdentity = Depends(identity)):
        if not notifications.mark_read(notification_id, identity.userId):
            raise BsideError("NOT_FOUND", 404)
        return {"ok": True}

    return app
