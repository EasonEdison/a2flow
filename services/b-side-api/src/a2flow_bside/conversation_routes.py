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
    router = APIRouter()
    chat = ChatApplicationService(
        messages=messages,
        environment=environment,
        work_activities=work_activities,
        processing_tasks=processing_tasks,
        chat_action=chat_action,
        durable_chat=durable_chat,
    )

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

    @router.get("/api/conversations/messages", response_model=None)
    async def conversation_messages(
        *,
        conversation_id: Annotated[int, Query(alias="conversationId", gt=0)],
        identity: CurrentIdentity,
    ) -> JsonObject:
        owner = conversations.owner(conversation_id)
        if owner is None or owner != identity.userId:
            raise BsideError("NOT_FOUND", 404)
        rows = messages.list_for(conversation_id)
        cards = []
        if chat_cards is not None:
            try:
                cards = await asyncio.to_thread(
                    chat_cards,
                    identity.userId,
                    str(conversation_id),
                )
                if not isinstance(cards, list):
                    raise TypeError("CHAT_CARDS_RESULT_INVALID")
            except Exception as error:
                raise BsideError("CHAT_HISTORY_CARDS_UNAVAILABLE", 503) from error
        elif has_card_references(rows):
            raise BsideError("CHAT_HISTORY_CARDS_UNAVAILABLE", 503)
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
                for row in hydrated
                # A submission triggers the next model turn server-side. Its internal
                # input record is not a message authored by the user.
                if not (row["role"] == "user" and row["ref_kind"] == "temporary_interaction")
            ],
            "unassignedCards": unassigned_cards,
        }

    @router.post("/api/conversations/messages", response_model=None)
    async def send_message(*, body: MessageSend, identity: CurrentIdentity) -> StreamingResponse:
        conversation_id = body.conversationId
        owner = conversations.owner(conversation_id)
        if owner is None or owner != identity.userId:
            raise BsideError("NOT_FOUND", 404)
        turn = await chat.admit_message(body, identity.userId)
        if durable_chat is None:
            raise BsideError("CHAT_DURABLE_DISPATCH_UNAVAILABLE", 503)
        return StreamingResponse(
            durable_chat.stream(turn),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @router.get("/api/conversations/{conversation_id}/cards", response_model=None)
    async def conversation_cards(*, conversation_id: int, identity: CurrentIdentity) -> JsonObject:
        if conversations.owner(conversation_id) != identity.userId:
            raise BsideError("CONVERSATION_NOT_FOUND", 404)
        if chat_cards is None:
            raise BsideError("CHAT_APPLICATION_UNAVAILABLE", 503)
        return {"cards": await asyncio.to_thread(chat_cards, identity.userId, str(conversation_id))}

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
        task = asyncio.create_task(
            chat.execute_chat_card_action(identity.userId, conversation_id, card_id, body)
        )
        retain_task(task)
        return await asyncio.shield(task)

    @router.post("/api/conversations/{conversation_id}/run-refs", response_model=None)
    async def attach_run(
        *, conversation_id: int, body: RunRefCreate, identity: CurrentIdentity
    ) -> JsonObject:
        owner = conversations.owner(conversation_id)
        if owner is None or owner != identity.userId:
            raise BsideError("NOT_FOUND", 404)
        if not run_ownership.owned_by(identity.userId, body.runId):
            raise BsideError("NOT_FOUND", 404)
        row = messages.append(
            conversation_id=conversation_id,
            role="assistant",
            content={"text": "工作流已启动，等待你的确认。"},  # noqa: RUF001 - existing Chinese wire text
            ref_kind="run",
            ref_id=body.runId,
        )
        return {"id": row["id"]}

    return router
