"""Durable display projection of one native agent turn, not model history.

An HTTP subscriber may leave; the producer still consumes the native runner and
saves its outcome. Neither disconnect nor a GET retries model or tool execution.
Process crashes can leave RUNNING: this module deliberately does not guess success.
"""

import asyncio
import copy
import json
import time
from collections.abc import AsyncIterator
from typing import Any, Literal, TypeAlias, TypedDict, cast

from starlette.responses import StreamingResponse

JsonValue: TypeAlias = (
    bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"] | None
)
JsonObject: TypeAlias = dict[str, JsonValue]


class ModelMessageRecord(TypedDict):
    messageId: str
    sequence: int
    text: str
    reasoning: str
    phase: Literal["process", "final"]


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


class ExecutionProjection(TypedDict):
    schemaVersion: Literal["v1"]
    turnId: str
    inputMessageId: str
    assistantMessageId: str
    modelMessages: list[ModelMessageRecord]
    toolCalls: list[ToolCallRecord]


def _identifier(value: object, *, limit: int = 256) -> str | None:
    return value if isinstance(value, str) and 0 < len(value) <= limit else None


class ChatDelivery:
    def __init__(self, *, messages, runner, user_id, conversation_id, text,
                 input_message, assistant_message):
        self.messages, self.runner = messages, runner
        self.user_id, self.conversation_id, self.text = user_id, conversation_id, text
        self.input_id, self.assistant_id = input_message['id'], assistant_message['id']
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
            "text": "", "reasoning": "", "tools": [], "events": [],
            "delivery": "running", "execution": self.execution,
        }
        self._model_messages: dict[str, ModelMessageRecord] = {}
        self._tool_calls: dict[str, ToolCallRecord] = {}
        self.final_model_message_id: str | None = None
        self.pending: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(
            maxsize=64,
        )
        self.detached = False
        self.sequence = 0

    def _model_delta(
        self, event: dict[str, Any], key: Literal["text", "reasoning"],
        sequence: int,
    ) -> None:
        message_id = _identifier(event.get("modelMessageId"))
        value = event.get("text")
        if message_id is None or not isinstance(value, str):
            return
        record = self._model_messages.get(message_id)
        if record is None:
            record = {"messageId": message_id, "sequence": sequence,
                      "text": "", "reasoning": "", "phase": "process"}
            self._model_messages[message_id] = record
            self.execution["modelMessages"].append(record)
        if key == "text":
            record["text"] += value
        else:
            record["reasoning"] += value

    def _tool_started(self, event: dict[str, Any], sequence: int) -> None:
        tool_call_id = _identifier(event.get("toolCallId"))
        name = _identifier(event.get("name"), limit=128)
        started_at = _identifier(event.get("startedAt"), limit=64)
        arguments = event.get("arguments")
        if (tool_call_id is None or name is None or started_at is None
                or not isinstance(arguments, dict)):
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
            tool_call_id is None or name is None or started_at is None
            or finished_at is None or type(duration_ms) is not int
            or duration_ms < 0 or lifecycle not in {"returned", "raised"}
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
        record.update({
            "lifecycleStatus": lifecycle,
            "toolMessageStatus": tool_status,
            "finishedAt": finished_at,
            "durationMs": duration_ms,
        })
        if "result" in event:
            record["result"] = cast(JsonValue, copy.deepcopy(event["result"]))
        business_success = event.get("businessSuccess")
        if type(business_success) is bool or business_success is None:
            if "businessSuccess" in event:
                record["businessSuccess"] = business_success
        error_code = _identifier(event.get("errorCode"), limit=128)
        if error_code is not None:
            record["errorCode"] = error_code

    def _finalize_model_messages(self, event: dict[str, Any]) -> None:
        final_id = _identifier(event.get("finalModelMessageId"))
        self.final_model_message_id = final_id
        final_content = event.get("content")
        if final_id is not None:
            record = self._model_messages.get(final_id)
            if record is None:
                record = {"messageId": final_id, "sequence": self.sequence + 1,
                          "text": "", "reasoning": "", "phase": "final"}
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

    async def emit(self, event: dict[str, Any]) -> None:
        self.sequence += 1
        if not self.detached:
            await self.pending.put({**event, "sequence": self.sequence,
                                    "messageId": str(self.assistant_id),
                                    "inputMessageId": str(self.input_id)})

    async def save(self) -> None:
        await asyncio.to_thread(
            self.messages.update_delivery, conversation_id=self.conversation_id,
            message_id=self.assistant_id, content=copy.deepcopy(self.content))

    async def produce(self) -> None:
        completed, failed, waiting = False, False, False
        last_save = time.monotonic()
        iterator = None
        try:
            await self.emit({"type": "turn_started", "turnId": self.turn_id})
            iterator = self.runner.iterate(
                user_id=self.user_id, conversation_id=self.conversation_id,
                text=self.text, turn_id=str(self.input_id),
            )
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
                    event = {**event, "turnId": self.turn_id,
                             "inputMessageId": str(self.input_id),
                             "assistantMessageId": str(self.assistant_id)}
                    self.content["events"].append(event)
                elif kind in ("text_delta", "reasoning_delta"):
                    key = "text" if kind == "text_delta" else "reasoning"
                    self._model_delta(event, key, self.sequence + 1)
                elif kind == "tool_call":
                    self.content["tools"].append(str(event.get("tool", "")))
                elif kind == "tool_call_started":
                    self._tool_started(event, self.sequence + 1)
                elif kind == "tool_call_finished":
                    self._tool_finished(event, self.sequence + 1)
                elif kind in ("workflow_confirm", "interaction_required",
                              "application_rendered"):
                    event = {**event, "turnId": self.turn_id,
                             "inputMessageId": str(self.input_id),
                             "assistantMessageId": str(self.assistant_id)}
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
            await self.emit({"type": "done" if self.content["delivery"] in {"completed", "waiting_action"} else "error",
                             "code": self.content.get("errorCode"),
                             "finalModelMessageId": self.final_model_message_id,
                             "content": copy.deepcopy(self.content)})
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
    def __init__(self, delivery):
        self.delivery = delivery
        super().__init__(delivery.stream(), media_type="text/event-stream",
                         headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.delivery.detach()
