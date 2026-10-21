"""Conversation routes HTTP routes with explicit typed dependencies."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from .chat_application import ChatApplicationService
from .chat_history import has_card_references, hydrate_history
from .durable_chat import DurableChat
from .errors import BsideError
from .processing_tasks import ProcessingTasksRepository
from .repositories import (
    ConversationsRepository,
    MessagesRepository,
    RunOwnershipRepository,
)
from .route_dependencies import (
    ChatAction,
    ChatCards,
    JsonObject,
)
from .route_identity import CurrentIdentity
from .route_models import (
    ChatCardAction,
    ConversationCreate,
    MessageSend,
    RunRefCreate,
)
from .route_support import _iso
from .work_activities import WorkActivitiesRepository


def create_router(
    *,
    conversations: ConversationsRepository,
    messages: MessagesRepository,
    run_ownership: RunOwnershipRepository,
    environment: str,
    work_activities: WorkActivitiesRepository | None,
    processing_tasks: ProcessingTasksRepository | None,
    chat_cards: ChatCards | None,
    chat_action: ChatAction | None,
    durable_chat: DurableChat | None,
    retain_task: Callable[[asyncio.Task[JsonObject]], None],
) -> APIRouter:
    # 会话路由注入应用服务, HTTP 层负责身份和响应, 执行准入由服务负责。
    router = APIRouter()
    chat = ChatApplicationService(
        messages=messages,
        environment=environment,
        work_activities=work_activities,
        processing_tasks=processing_tasks,
        chat_action=chat_action,
        durable_chat=durable_chat,
    )

    # 列表仅查询当前登录用户的会话, 时间统一转为线协议格式。
    @router.get("/api/conversations", response_model=None)
    async def list_conversations(*, identity: CurrentIdentity) -> JsonObject:
        return {
            "conversations": [
                {
                    "id": row["id"],
                    "title": row["title"],
                    "createdAt": _iso(row["created_at"]),
                }
                for row in conversations.list_for(identity.userId)
            ]
        }

    # 会话所有者取自认证结果, 客户端不能通过请求体指定用户。
    @router.post("/api/conversations", response_model=None)
    async def create_conversation(
        *, body: ConversationCreate, identity: CurrentIdentity
    ) -> JsonObject:
        row = conversations.create(user_id=identity.userId, title=body.title)
        return {
            "id": row["id"],
            "title": row["title"],
            "createdAt": _iso(row["created_at"]),
        }

    # 历史查询使用 conversationId 参数, 读取前仍检查会话所有者。
    @router.get("/api/conversations/messages", response_model=None)
    async def conversation_messages(
        *,
        conversation_id: Annotated[int, Query(alias="conversationId", gt=0)],
        identity: CurrentIdentity,
    ) -> JsonObject:
        owner = conversations.owner(conversation_id)
        if owner is None or owner != identity.userId:
            raise BsideError("NOT_FOUND", 404)
        # 历史由保存的消息和最新权威卡片状态共同恢复。
        rows = messages.list_for(conversation_id)
        cards = []
        if chat_cards is not None:
            try:
                cards = await asyncio.to_thread(
                    chat_cards,
                    identity.userId,
                    str(conversation_id),
                )
                # 卡片读取失败明确返回不可用, 不能把卡片丢失伪装成正常历史。
                if not isinstance(cards, list):
                    raise TypeError("CHAT_CARDS_RESULT_INVALID")
            except Exception as error:
                raise BsideError("CHAT_HISTORY_CARDS_UNAVAILABLE", 503) from error
        elif has_card_references(rows):
            raise BsideError("CHAT_HISTORY_CARDS_UNAVAILABLE", 503)
        # 按稳定引用关联卡片, 无归属卡片单独返回以避免静默遗漏。
        hydrated, unassigned_cards = hydrate_history(rows, cards)
        return {
            "messages": [
                {
                    "id": str(row["id"]),
                    "role": row["role"],
                    "content": row["content"],
                    "refKind": row["ref_kind"],
                    "refId": row["ref_id"],
                    "createdAt": _iso(row["created_at"]),
                }
                # 内部恢复输入不是用户亲自发送的消息, 历史展示时过滤该记录。
                for row in hydrated
                # A submission triggers the next model turn server-side. Its internal
                # input record is not a message authored by the user.
                if not (row["role"] == "user" and row["ref_kind"] == "temporary_interaction")
            ],
            "unassignedCards": unassigned_cards,
        }

    # 消息先完成持久化准入, 再订阅输出; 刷新重连不会重新启动模型。
    @router.post("/api/conversations/messages", response_model=None)
    async def send_message(*, body: MessageSend, identity: CurrentIdentity) -> StreamingResponse:
        conversation_id = body.conversationId
        owner = conversations.owner(conversation_id)
        if owner is None or owner != identity.userId:
            raise BsideError("NOT_FOUND", 404)
        # 应用服务校验幂等键、引用及处理任务, 并返回同一轮次事实。
        turn = await chat.admit_message(body, identity.userId)
        if durable_chat is None:
            raise BsideError("CHAT_DURABLE_DISPATCH_UNAVAILABLE", 503)
        # SSE 只订阅保存的事件, 禁止缓存及代理缓冲。
        return StreamingResponse(
            durable_chat.stream(turn),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    # 卡片列表沿用会话归属检查, 不因知道卡片 ID 就开放读取。
    @router.get("/api/conversations/{conversation_id}/cards", response_model=None)
    async def conversation_cards(*, conversation_id: int, identity: CurrentIdentity) -> JsonObject:
        if conversations.owner(conversation_id) != identity.userId:
            raise BsideError("CONVERSATION_NOT_FOUND", 404)
        if chat_cards is None:
            raise BsideError("CHAT_APPLICATION_UNAVAILABLE", 503)
        return {"cards": await asyncio.to_thread(chat_cards, identity.userId, str(conversation_id))}

    # 卡片动作只接受所属会话, 实际提交与自动续聊由应用服务衔接。
    @router.post(
        "/api/conversations/{conversation_id}/cards/{card_id}/actions",
        response_model=None,
    )
    async def conversation_card_action(
        *,
        conversation_id: int,
        card_id: str,
        body: ChatCardAction,
        identity: CurrentIdentity,
    ) -> JsonObject:
        if conversations.owner(conversation_id) != identity.userId:
            raise BsideError("CONVERSATION_NOT_FOUND", 404)
        if chat_action is None:
            raise BsideError("CHAT_APPLICATION_UNAVAILABLE", 503)
        # 动作任务归应用生命周期所有, shield 避免浏览器断连取消真实执行。
        task = asyncio.create_task(
            chat.execute_chat_card_action(identity.userId, conversation_id, card_id, body)
        )
        retain_task(task)
        return await asyncio.shield(task)

    # 关联运行时同时验证会话与运行归属, 不能跨账号引用结果。
    @router.post("/api/conversations/{conversation_id}/run-refs", response_model=None)
    async def attach_run(
        *, conversation_id: int, body: RunRefCreate, identity: CurrentIdentity
    ) -> JsonObject:
        owner = conversations.owner(conversation_id)
        if owner is None or owner != identity.userId:
            raise BsideError("NOT_FOUND", 404)
        if not run_ownership.owned_by(identity.userId, body.runId):
            raise BsideError("NOT_FOUND", 404)
        # 这里只保存运行引用消息, 不能由这条展示消息推断工作流已完成。
        row = messages.append(
            conversation_id=conversation_id,
            role="assistant",
            content={"text": "工作流已启动，等待你的确认。"},  # noqa: RUF001 - existing Chinese wire text
            ref_kind="run",
            ref_id=body.runId,
        )
        return {"id": row["id"]}

    return router
