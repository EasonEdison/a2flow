"""Durable display projection of one native agent turn, not model history.

An HTTP subscriber may leave; the producer still consumes the native runner and
saves its outcome. Neither disconnect nor a GET retries model or tool execution.
Process crashes can leave RUNNING: this module deliberately does not guess success.
"""

import asyncio
import copy
import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from typing import Any, Literal, NotRequired, Protocol, TypeAlias, TypedDict, cast

from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from .chat_runner import ChatStream
from .persistence_types import MessageRecord
from .processing_tasks import ProcessingContext


class MessageProjection(Protocol):
    """Both direct messages and generation-fenced writes persist projections."""

    def update_delivery(
        self, *, conversation_id: int, message_id: int, content: dict[str, Any]
    ) -> None: ...


JsonValue: TypeAlias = bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"] | None
JsonObject: TypeAlias = dict[str, JsonValue]


class ModelMessageRecord(TypedDict):
    messageId: str
    sequence: int
    text: str
    reasoning: str
    phase: Literal["process", "final"]


GenerationStage = Literal[
    "preparing", "generating", "validating_loading", "saving", "completed", "failed"
]


class GenerationProgressRecord(TypedDict):
    toolCallId: str
    name: Literal["generate_a2ui", "generate_interaction"]
    stage: GenerationStage
    elapsedMs: int
    errorCode: str


class ToolCallRecord(TypedDict, total=False):
    toolCallId: str
    sequence: int
    name: str
    arguments: JsonObject
    lifecycleStatus: Literal["running", "returned", "raised"]
    toolMessageStatus: Literal["success", "error"] | None
    startedAt: str
    finishedAt: str
    durationMs: int
    result: JsonValue
    businessSuccess: bool | None
    errorCode: str
    generationProgress: list[GenerationProgressRecord]


class ExecutionProjection(TypedDict):
    schemaVersion: Literal["v1"]
    turnId: str
    inputMessageId: str
    assistantMessageId: str
    modelMessages: list[ModelMessageRecord]
    toolCalls: list[ToolCallRecord]


class TextContentPart(TypedDict, total=False):
    type: Literal["text"]
    id: str
    text: str
    modelMessageId: str


class ApplicationContentPart(TypedDict, total=False):
    type: Literal["application"]
    id: str
    cardId: str
    card: JsonObject | None


class PersonalWorkflowContentPart(TypedDict):
    type: Literal["personal_workflow"]
    id: str
    workflow: JsonObject


ContentPart: TypeAlias = TextContentPart | ApplicationContentPart | PersonalWorkflowContentPart


def _identifier(value: object, *, limit: int = 256) -> str | None:
    return value if isinstance(value, str) and 0 < len(value) <= limit else None


class RunnerArguments(TypedDict):
    user_id: int
    conversation_id: int
    text: str
    turn_id: str
    run_references: NotRequired[Sequence[Mapping[str, Any]]]
    processing_context: NotRequired[ProcessingContext]


class ChatDelivery:
    def __init__(
        self,
        *,
        messages: MessageProjection,
        runner: ChatStream,
        user_id: int,
        conversation_id: int,
        text: str,
        input_message: MessageRecord,
        assistant_message: MessageRecord,
        run_references: tuple[dict[str, Any], ...] = (),
        processing_context: ProcessingContext | None = None,
    ) -> None:
        self.messages, self.runner = messages, runner
        self.user_id, self.conversation_id, self.text = user_id, conversation_id, text
        self.input_id, self.assistant_id = input_message["id"], assistant_message["id"]
        self.run_references = copy.deepcopy(list(run_references))
        self.processing_context = copy.deepcopy(processing_context)
        self.turn_id = str(self.input_id)
        self.execution: ExecutionProjection = {
            "schemaVersion": "v1",
            "turnId": self.turn_id,
            "inputMessageId": str(self.input_id),
            "assistantMessageId": str(self.assistant_id),
            "modelMessages": [],
            "toolCalls": [],
        }
        self.content: dict[str, Any] = {
            "text": "",
            "reasoning": "",
            "tools": [],
            "events": [],
            "delivery": "running",
            "execution": self.execution,
            "parts": [],
        }
        if isinstance(assistant_message.get("content", {}).get("continuation"), dict):
            self.content["continuation"] = copy.deepcopy(
                assistant_message["content"]["continuation"]
            )
        if self.processing_context is not None:
            self.content["processingTaskId"] = self.processing_context["taskId"]
        self.parts: list[ContentPart] = self.content["parts"]
        self._live_cards: dict[str, JsonObject] = {}
        self._text_part_count = 0
        self._model_messages: dict[str, ModelMessageRecord] = {}
        self._tool_calls: dict[str, ToolCallRecord] = {}
        self.final_model_message_id: str | None = None
        self.pending: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(
            maxsize=64,
        )
        self.detached = False
        self.sequence = 0
        # Native delivery and durable journaling supply the same explicit event sink.
        self.emit: Callable[[dict[str, Any]], Awaitable[None]] = self._emit

    def _model_delta(
        self,
        event: dict[str, Any],
        key: Literal["text", "reasoning"],
        sequence: int,
    ) -> str | None:
        message_id = _identifier(event.get("modelMessageId"))
        value = event.get("text")
        if not isinstance(value, str):
            return None
        if message_id is not None:
            record = self._model_messages.get(message_id)
            if record is None:
                record = {
                    "messageId": message_id,
                    "sequence": sequence,
                    "text": "",
                    "reasoning": "",
                    "phase": "process",
                }
                self._model_messages[message_id] = record
                self.execution["modelMessages"].append(record)
            if key == "text":
                record["text"] += value
            else:
                record["reasoning"] += value
        if key != "text":
            return None
        current = self.parts[-1] if self.parts else None
        current_model_id = (
            current.get("modelMessageId")
            if isinstance(current, dict) and current.get("type") == "text"
            else None
        )
        if (
            isinstance(current, dict)
            and current.get("type") == "text"
            and current_model_id == message_id
        ):
            text_part = cast(TextContentPart, current)
            text_part["text"] = text_part["text"] + value
            return text_part["id"]
        return self._append_text_part(value, message_id)

    def _append_text_part(self, value: str, message_id: str | None) -> str:
        self._text_part_count += 1
        part: TextContentPart = {
            "type": "text",
            "id": f"text:{self.assistant_id}:{self._text_part_count}",
            "text": value,
        }
        if message_id is not None:
            part["modelMessageId"] = message_id
        self.parts.append(part)
        return part["id"]

    def _application(self, event: dict[str, Any]) -> tuple[str, JsonObject] | None:
        card = event.get("card")
        if not isinstance(card, dict):
            return None
        card_id = _identifier(card.get("cardId"), limit=128)
        if card_id is None:
            return None
        copied = cast(JsonObject, copy.deepcopy(card))
        self._live_cards[card_id] = copied
        part_id = "application:" + card_id
        if not any(part.get("id") == part_id for part in self.parts):
            self.parts.append(
                {
                    "type": "application",
                    "id": part_id,
                    "cardId": card_id,
                }
            )
        return part_id, copied

    def _personal_workflow(self, event: dict[str, Any]) -> tuple[str, JsonObject]:
        workflow = event.get("workflow")
        if not isinstance(workflow, dict):
            raise ValueError("INVALID_PERSONAL_WORKFLOW_EVENT")
        key = _identifier(workflow.get("definitionKey"))
        if (
            key is None
            or not key.startswith("personal-wf-")
            or workflow.get("source") != "PERSONAL"
        ):
            raise ValueError("INVALID_PERSONAL_WORKFLOW_EVENT")
        if (
            not isinstance(workflow.get("name"), str)
            or not workflow["name"].strip()
            or len(workflow["name"]) > 200
            or not isinstance(workflow.get("defaultRequirement"), str)
            or len(workflow["defaultRequirement"]) > 2000
        ):
            raise ValueError("INVALID_PERSONAL_WORKFLOW_EVENT")
        nodes = workflow.get("nodes")
        if not isinstance(nodes, list) or not 1 <= len(nodes) <= 8:
            raise ValueError("INVALID_PERSONAL_WORKFLOW_EVENT")
        public_nodes: list[JsonValue] = []
        for node in nodes:
            if not isinstance(node, dict) or node.get("type") not in {
                "SKILL",
                "BUSINESS_CAPABILITY",
            }:
                raise ValueError("INVALID_PERSONAL_WORKFLOW_EVENT")
            reference = "skillKey" if node["type"] == "SKILL" else "abilityKey"
            if _identifier(node.get("nodeId")) is None or _identifier(node.get(reference)) is None:
                raise ValueError("INVALID_PERSONAL_WORKFLOW_EVENT")
            public_node = {field: node[field] for field in ("nodeId", "type", reference)}
            if isinstance(node.get("displayName"), str):
                public_node["displayName"] = node["displayName"]
            public_nodes.append(public_node)
        copied: JsonObject = {
            "definitionKey": key,
            "source": "PERSONAL",
            "name": workflow["name"],
            "defaultRequirement": workflow["defaultRequirement"],
            "nodes": public_nodes,
        }
        if isinstance(workflow.get("inputSchema"), dict):
            copied["inputSchema"] = copy.deepcopy(workflow["inputSchema"])
        part_id = "personal-workflow:" + key
        existing = next((part for part in self.parts if part.get("id") == part_id), None)
        if existing is not None:
            if existing.get("workflow") != copied:
                raise ValueError("PERSONAL_WORKFLOW_EVENT_CONFLICT")
        else:
            self.parts.append({"type": "personal_workflow", "id": part_id, "workflow": copied})
        return part_id, copied

    def _public_content(self) -> dict[str, Any]:
        content = copy.deepcopy(self.content)
        for part in content["parts"]:
            if part.get("type") == "application":
                part["card"] = copy.deepcopy(self._live_cards.get(part["cardId"]))
        return content

    def _tool_started(self, event: dict[str, Any], sequence: int) -> None:
        tool_call_id = _identifier(event.get("toolCallId"))
        name = _identifier(event.get("name"), limit=128)
        started_at = _identifier(event.get("startedAt"), limit=64)
        arguments = event.get("arguments")
        if (
            tool_call_id is None
            or name is None
            or started_at is None
            or not isinstance(arguments, dict)
        ):
            return
        record: ToolCallRecord = {
            "toolCallId": tool_call_id,
            "sequence": sequence,
            "name": name,
            "arguments": cast(JsonObject, copy.deepcopy(arguments)),
            "lifecycleStatus": "running",
            "toolMessageStatus": None,
            "startedAt": started_at,
        }
        self._tool_calls[tool_call_id] = record
        self.execution["toolCalls"].append(record)

    def _tool_finished(self, event: dict[str, Any], sequence: int) -> None:
        tool_call_id = _identifier(event.get("toolCallId"))
        name = _identifier(event.get("name"), limit=128)
        started_at = _identifier(event.get("startedAt"), limit=64)
        finished_at = _identifier(event.get("finishedAt"), limit=64)
        duration_ms = event.get("durationMs")
        lifecycle = event.get("lifecycleStatus")
        tool_status = event.get("toolMessageStatus")
        if (
            tool_call_id is None
            or name is None
            or started_at is None
            or finished_at is None
            or type(duration_ms) is not int
            or duration_ms < 0
            or lifecycle not in {"returned", "raised"}
            or tool_status not in {None, "success", "error"}
        ):
            return
        record = self._tool_calls.get(tool_call_id)
        if record is None:
            record = {
                "toolCallId": tool_call_id,
                "sequence": sequence,
                "name": name,
                "arguments": {},
                "lifecycleStatus": "running",
                "toolMessageStatus": None,
                "startedAt": started_at,
            }
            self._tool_calls[tool_call_id] = record
            self.execution["toolCalls"].append(record)
        record.update(
            {
                "lifecycleStatus": lifecycle,
                "toolMessageStatus": tool_status,
                "finishedAt": finished_at,
                "durationMs": duration_ms,
            }
        )
        if "result" in event:
            record["result"] = cast(JsonValue, copy.deepcopy(event["result"]))
        business_success = event.get("businessSuccess")
        if type(business_success) is bool or business_success is None:
            if "businessSuccess" in event:
                record["businessSuccess"] = business_success
        error_code = _identifier(event.get("errorCode"), limit=128)
        if error_code is not None:
            record["errorCode"] = error_code

    def _generation_progress(self, event: dict[str, Any]) -> GenerationProgressRecord | None:
        tool_call_id = _identifier(event.get("toolCallId"))
        record = self._tool_calls.get(tool_call_id or "")
        stage = event.get("stage")
        elapsed = event.get("elapsedMs")
        code = event.get("errorCode", "")
        if (
            record is None
            or record["name"] not in {"generate_a2ui", "generate_interaction"}
            or event.get("name") != record["name"]
            or not isinstance(stage, str)
            or stage
            not in {
                "preparing",
                "generating",
                "validating_loading",
                "saving",
                "completed",
                "failed",
            }
            or type(elapsed) is not int
            or elapsed < 0
            or not isinstance(code, str)
            or len(code) > 128
            or (code and not all(char in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for char in code))
        ):
            return None
        progress = record.setdefault("generationProgress", [])
        order = {
            "preparing": 0,
            "generating": 1,
            "validating_loading": 2,
            "saving": 3,
            "completed": 4,
            "failed": 4,
        }
        if len(progress) >= 5 or (
            progress
            and (
                order[stage] <= order[progress[-1]["stage"]] or elapsed < progress[-1]["elapsedMs"]
            )
        ):
            return None
        value: GenerationProgressRecord = {
            "toolCallId": record["toolCallId"],
            "name": cast(Literal["generate_a2ui", "generate_interaction"], record["name"]),
            "stage": cast(GenerationStage, stage),
            "elapsedMs": elapsed,
            "errorCode": code,
        }
        if not progress or progress[-1] != value:
            progress.append(value)
        return value

    def _finalize_model_messages(self, event: dict[str, Any]) -> None:
        final_id = _identifier(event.get("finalModelMessageId"))
        self.final_model_message_id = final_id
        final_content = event.get("content")
        if final_id is not None:
            record = self._model_messages.get(final_id)
            if record is None:
                record = {
                    "messageId": final_id,
                    "sequence": self.sequence + 1,
                    "text": "",
                    "reasoning": "",
                    "phase": "final",
                }
                self._model_messages[final_id] = record
                self.execution["modelMessages"].append(record)
            record["phase"] = "final"
            if not record["text"] and isinstance(final_content, str):
                record["text"] = final_content
            self.content["text"] = record["text"]
            self.content["reasoning"] = record["reasoning"]
        elif isinstance(final_content, str):
            # A provider without native ids still gets an accurate final answer,
            # but no synthetic model message identity is invented.
            self.content["text"] = final_content
        matching_text = "".join(
            str(part.get("text", ""))
            for part in self.parts
            if part.get("type") == "text"
            and (
                part.get("modelMessageId") == final_id
                if final_id is not None
                else "modelMessageId" not in part
            )
        )
        has_streamed_final = (
            bool(matching_text)
            if final_id is not None
            else isinstance(final_content, str) and matching_text == final_content
        )
        if isinstance(final_content, str) and final_content and not has_streamed_final:
            # Some providers only expose the final text on their terminal
            # message. Add that real text once; streamed text remains
            # authoritative whenever a matching part already exists.
            self._append_text_part(final_content, final_id)

    async def _emit(self, event: dict[str, Any]) -> None:
        self.sequence += 1
        if not self.detached:
            await self.pending.put(
                {
                    **event,
                    "sequence": self.sequence,
                    "messageId": str(self.assistant_id),
                    "inputMessageId": str(self.input_id),
                }
            )

    async def save(self) -> None:
        await asyncio.to_thread(
            self.messages.update_delivery,
            conversation_id=self.conversation_id,
            message_id=self.assistant_id,
            content=copy.deepcopy(self.content),
        )

    async def produce(self) -> None:
        completed, failed, waiting = False, False, False
        last_save = time.monotonic()
        iterator = None
        try:
            await self.emit(
                {
                    "type": "turn_started",
                    "turnId": self.turn_id,
                    **(
                        {"processingTaskId": self.processing_context["taskId"]}
                        if self.processing_context is not None
                        else {}
                    ),
                }
            )
            arguments: RunnerArguments = dict(
                user_id=self.user_id,
                conversation_id=self.conversation_id,
                text=self.text,
                turn_id=str(self.input_id),
            )
            if self.run_references:
                arguments["run_references"] = self.run_references
            if self.processing_context is not None:
                arguments["processing_context"] = self.processing_context
            iterator = self.runner.iterate(**arguments)
            async for event in iterator:
                kind = event.get("type")
                if kind == "done":
                    self._finalize_model_messages(event)
                    completed = True
                    continue  # Native iterator/session must exit before success.
                if kind == "error":
                    failed = True
                    self.content["errorCode"] = event.get("code", "CHAT_UNAVAILABLE")
                    continue
                if kind == "waiting_action":
                    waiting = True
                    event = {
                        **event,
                        "turnId": self.turn_id,
                        "inputMessageId": str(self.input_id),
                        "assistantMessageId": str(self.assistant_id),
                    }
                    card_id = _identifier(event.get("cardId"), limit=128)
                    if card_id is not None:
                        event["partId"] = "application:" + card_id
                    self.content["events"].append(event)
                elif kind in ("text_delta", "reasoning_delta"):
                    key: Literal["text", "reasoning"] = (
                        "text" if kind == "text_delta" else "reasoning"
                    )
                    part_id = self._model_delta(event, key, self.sequence + 1)
                    if part_id is not None:
                        event = {**event, "partId": part_id}
                elif kind == "tool_call":
                    self.content["tools"].append(str(event.get("tool", "")))
                elif kind == "tool_call_started":
                    self._tool_started(event, self.sequence + 1)
                elif kind == "tool_call_finished":
                    self._tool_finished(event, self.sequence + 1)
                elif kind == "a2ui_generation_progress":
                    progress = self._generation_progress(event)
                    if progress is None:
                        continue
                    event = {"type": kind, **progress}
                elif kind == "application_rendered":
                    event = {
                        **event,
                        "turnId": self.turn_id,
                        "inputMessageId": str(self.input_id),
                        "assistantMessageId": str(self.assistant_id),
                    }
                    application = self._application(event)
                    if application is None:
                        continue
                    part_id, card = application
                    event = {**event, "partId": part_id, "card": card}
                    self.content["events"].append(
                        {
                            "type": "application_rendered",
                            "turnId": self.turn_id,
                            "inputMessageId": str(self.input_id),
                            "assistantMessageId": str(self.assistant_id),
                            "partId": part_id,
                            "cardId": card["cardId"],
                        }
                    )
                elif kind == "personal_workflow_created":
                    part_id, workflow = self._personal_workflow(event)
                    event = {
                        "type": kind,
                        "workflow": workflow,
                        "partId": part_id,
                        "turnId": self.turn_id,
                        "sequence": self.sequence + 1,
                        "messageId": str(self.assistant_id),
                        "inputMessageId": str(self.input_id),
                        "assistantMessageId": str(self.assistant_id),
                    }
                    if not any(
                        item.get("type") == kind and item.get("partId") == part_id
                        for item in self.content["events"]
                    ):
                        self.content["events"].append(copy.deepcopy(event))
                    # A displayed registration result must survive a refresh even
                    # if the model's later turn fails or the subscriber disconnects.
                    await self.save()
                    last_save = time.monotonic()
                elif kind in ("workflow_confirm", "interaction_required"):
                    event = {
                        **event,
                        "turnId": self.turn_id,
                        "inputMessageId": str(self.input_id),
                        "assistantMessageId": str(self.assistant_id),
                    }
                    self.content["events"].append(event)
                else:
                    continue
                await self.emit(event)
                if time.monotonic() - last_save >= 1:
                    await self.save()
                    last_save = time.monotonic()
            if not completed or failed:
                self.content["delivery"] = "failed"
                self.content.setdefault("errorCode", "CHAT_INCOMPLETE")
            else:
                self.content["delivery"] = "waiting_action" if waiting else "completed"
            await self.save()
            await self.emit(
                {
                    "type": "done"
                    if self.content["delivery"] in {"completed", "waiting_action"}
                    else "error",
                    "code": self.content.get("errorCode"),
                    "finalModelMessageId": self.final_model_message_id,
                    "content": self._public_content(),
                }
            )
        except (Exception, asyncio.CancelledError):
            self.content["delivery"] = "unconfirmed"
            self.content["errorCode"] = "CHAT_UNCONFIRMED"
            try:
                await self.save()
            except Exception:
                pass  # Persisted RUNNING remains unconfirmed, never fake success.
            await self.emit({"type": "error", "code": "CHAT_UNCONFIRMED"})
        finally:
            try:
                close = getattr(iterator, "aclose", None)
                if close is not None:
                    await close()
            finally:
                if not self.detached:
                    await self.pending.put(None)

    async def stream(self) -> AsyncIterator[str]:
        try:
            while True:
                event = await self.pending.get()
                if event is None:
                    return
                yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
        finally:
            self.detach()

    def detach(self) -> None:
        self.detached = True
        # Also safe before the async generator starts (disconnect during headers).
        while not self.pending.empty():
            self.pending.get_nowait()


class ChatStreamingResponse(StreamingResponse):
    def __init__(self, delivery: ChatDelivery) -> None:
        self.delivery = delivery
        super().__init__(
            delivery.stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.delivery.detach()
