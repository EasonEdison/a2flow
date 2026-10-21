"""Chat admission and saved-card continuation application operations.

The product owns durable admission; the runtime still owns the agent loop.
"""

from __future__ import annotations

import asyncio

from .durable_chat import DurableChat
from .errors import BsideError
from .persistence_types import DatabaseConnection, MessageRecord
from .processing_tasks import ProcessingContext, ProcessingTasksRepository
from .repositories import MessagesRepository
from .route_dependencies import ChatAction, JsonObject
from .route_models import ChatCardAction, MessageSend
from .route_support import _bounded_run_reference
from .work_activities import WorkActivitiesRepository


class ChatApplicationService:
    def __init__(
        self,
        *,
        messages: MessagesRepository,
        environment: str,
        work_activities: WorkActivitiesRepository | None,
        processing_tasks: ProcessingTasksRepository | None,
        chat_action: ChatAction | None,
        durable_chat: DurableChat | None,
    ) -> None:
        self.messages = messages
        self.environment = environment
        self.work_activities = work_activities
        self.processing_tasks = processing_tasks
        self.chat_action = chat_action
        self.durable_chat = durable_chat

    async def execute_chat_card_action(
        self, user_id: int, conversation_id: int, card_id: str, body: ChatCardAction
    ) -> JsonObject:
        chat_action = self.chat_action
        if chat_action is None:
            raise BsideError("CHAT_APPLICATION_UNAVAILABLE", 503)
        processing_context = None
        if self.processing_tasks is not None:
            processing_context = await asyncio.to_thread(
                self.processing_tasks.context_for_card,
                user_id=user_id,
                environment=self.environment,
                conversation_id=str(conversation_id),
                card_id=card_id,
            )
        response = await asyncio.to_thread(
            chat_action,
            user_id,
            str(conversation_id),
            card_id,
            {
                "requestId": body.requestId,
                "actionName": body.actionName,
                "inputs": body.inputs,
            },
        )
        marker = response.get("continuation")
        if marker is None:
            return response
        card = response.get("card", {})
        display = card.get("display", {})
        result = card.get("result", {})
        # This marker comes only from the trusted action service after it saved
        # the real write result. User inputs cannot opt into this continuation.
        submitted = (
            isinstance(result, dict)
            and result.get("status") == "SUBMITTED"
            and isinstance(result.get("values"), dict)
        )
        write_completed = (
            isinstance(marker, dict)
            and marker.get("kind") == "WRITE_APPROVAL"
            and "result" in card
        )
        temporary = (
            display.get("protocolProfile") == "a2flow.temporary.v1"
            and display.get("definitionSource") == "TEMPORARY"
        )
        confirmed_java = (
            write_completed and display.get("protocolProfile") == "a2flow.java-rpc.v1"
        )
        if (
            not isinstance(marker, dict)
            or marker.get("cardId") != card_id
            or not isinstance(marker.get("requestId"), str)
            or not marker["requestId"]
            or card.get("cardId") != card_id
            or card.get("conversationId") != str(conversation_id)
            or card.get("status") != "COMPLETED"
            or not (submitted or write_completed)
            or not (temporary or confirmed_java)
        ):
            raise BsideError("CHAT_CONTINUATION_UNCONFIRMED", 409)
        if self.durable_chat is None:
            raise BsideError("CHAT_DURABLE_DISPATCH_UNAVAILABLE", 503)
        await asyncio.to_thread(
            self.durable_chat.materialize, self.messages, self.processing_tasks
        )
        _, input_message, assistant_message = await asyncio.to_thread(
            self.messages.claim_interaction_continuation,
            user_id=user_id,
            conversation_id=conversation_id,
            card_id=card_id,
            request_id=marker["requestId"],
            write_completed=write_completed,
        )
        state = assistant_message["content"].get("delivery")
        statuses: dict[object, str] = {
            "queued": "RUNNING",
            "running": "RUNNING",
            "completed": "COMPLETED",
            "waiting_action": "COMPLETED",
            "unconfirmed": "NEEDS_REVIEW",
            "failed": "FAILED",
        }
        status = statuses.get(state, "UNKNOWN")
        return {
            **response,
            "continuation": {
                "cardId": card_id,
                "requestId": marker["requestId"],
                "status": status,
                "inputMessageId": str(input_message["id"]),
                "assistantMessageId": str(assistant_message["id"]),
            },
        }

    async def admit_message(self, body: MessageSend, user_id: int) -> JsonObject:
        conversation_id = body.conversationId
        durable_chat = self.durable_chat
        if durable_chat is None:
            raise BsideError("CHAT_DURABLE_DISPATCH_UNAVAILABLE", 503)

        prior = await asyncio.to_thread(
            durable_chat.request,
            user_id=user_id,
            conversation_id=conversation_id,
            request_id=body.clientRequestId,
            payload=body.model_dump(),
        )

        if prior is not None:
            return prior

        processing_context = None

        processing_activity = None

        if body.processingTarget is not None or body.processingTaskId is not None:
            if self.processing_tasks is None:
                raise BsideError("PROCESSING_UNAVAILABLE", 503)
            if body.processingTaskId is not None:
                processing_context = await asyncio.to_thread(
                    self.processing_tasks.get_context,
                    user_id=user_id,
                    environment=self.environment,
                    conversation_id=str(conversation_id),
                    task_id=body.processingTaskId,
                )
                processing_activity = processing_context["activityId"]
            elif body.processingTarget is not None:
                processing_activity = body.processingTarget.activityId

        references = []

        seen = set()

        activity_ids = [r.activityId for r in body.runReferences]

        if processing_activity is not None and processing_activity not in activity_ids:
            activity_ids.append(processing_activity)

        if len(activity_ids) > 3:
            raise BsideError("TOO_MANY_RUN_REFERENCES", 400)

        for activity_id in activity_ids:
            if activity_id in seen:
                raise BsideError("DUPLICATE_RUN_REFERENCE", 400)
            seen.add(activity_id)
            if self.work_activities is None:
                raise BsideError("WORK_ACTIVITIES_UNAVAILABLE", 503)
            snapshot = await asyncio.to_thread(
                self.work_activities.get_result,
                user_id=user_id,
                environment=self.environment,
                activity_id=activity_id,
                limit=8000,
            )
            references.append(_bounded_run_reference(snapshot))

        if processing_activity is not None:
            processing_tasks = self.processing_tasks
            processing_request_id = body.processingRequestId
            # MessageSend validates this pairing before admission. Capture the
            # validated request and concrete repository for the transaction callback.
            assert processing_tasks is not None and processing_request_id is not None

            def observe_turn(
                connection: DatabaseConnection,
                context: ProcessingContext,
                input_message: MessageRecord,
                assistant_message: MessageRecord,
                *,
                new: bool,
            ) -> None:
                if new:
                    durable_chat.insert_turn(
                        connection,
                        user_id=user_id,
                        conversation_id=conversation_id,
                        request_id="processing:" + processing_request_id,
                        digest=processing_request_id,
                        input_message=input_message,
                        assistant_message=assistant_message,
                        references=references,
                        processing_context=context,
                    )
                durable_chat.record_request(
                    connection,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    request_id=body.clientRequestId,
                    payload=body.model_dump(),
                    input_message=input_message,
                    assistant_message=assistant_message,
                )

            (
                created,
                processing_context,
                input_message,
                assistant_message,
            ) = await asyncio.to_thread(
                processing_tasks.begin_turn,
                user_id=user_id,
                environment=self.environment,
                conversation_id=str(conversation_id),
                request_id=processing_request_id,
                text=body.text,
                references=references,
                target=body.processingTarget.model_dump()
                if body.processingTarget
                else None,
                task_id=body.processingTaskId,
                turn_observer=observe_turn,
            )
            turn = await asyncio.to_thread(
                durable_chat.request,
                user_id=user_id,
                conversation_id=conversation_id,
                request_id=body.clientRequestId,
                payload=body.model_dump(),
            )
        else:
            turn = await asyncio.to_thread(
                durable_chat.receive,
                user_id=user_id,
                conversation_id=conversation_id,
                request_id=body.clientRequestId,
                payload=body.model_dump(),
                references=references,
            )

        assert turn is not None
        return turn
