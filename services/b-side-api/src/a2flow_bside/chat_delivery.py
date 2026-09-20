"""Durable display projection of one native agent turn, not model history.

An HTTP subscriber may leave; the producer still consumes the native runner and
saves its outcome. Neither disconnect nor a GET retries model or tool execution.
Process crashes can leave RUNNING: this module deliberately does not guess success.
"""

import asyncio
import copy
import json
import time
from starlette.responses import StreamingResponse


class ChatDelivery:
    def __init__(self, *, messages, runner, user_id, conversation_id, text,
                 input_message, assistant_message):
        self.messages, self.runner = messages, runner
        self.user_id, self.conversation_id, self.text = user_id, conversation_id, text
        self.input_id, self.assistant_id = input_message['id'], assistant_message['id']
        self.content = {"text": "", "reasoning": "", "tools": [],
                        "events": [], "delivery": "running"}
        self.pending = asyncio.Queue(maxsize=64)
        self.detached = False
        self.sequence = 0

    async def emit(self, event):
        self.sequence += 1
        if not self.detached:
            await self.pending.put({**event, "sequence": self.sequence,
                                    "messageId": str(self.assistant_id),
                                    "inputMessageId": str(self.input_id)})

    async def save(self):
        await asyncio.to_thread(
            self.messages.update_delivery, conversation_id=self.conversation_id,
            message_id=self.assistant_id, content=copy.deepcopy(self.content))

    async def produce(self):
        completed, failed = False, False
        last_save = time.monotonic()
        iterator = None
        try:
            await self.emit({"type": "turn_started"})
            iterator = self.runner.iterate(
                user_id=self.user_id, conversation_id=self.conversation_id,
                text=self.text, turn_id=str(self.input_id),
            )
            async for event in iterator:
                kind = event.get("type")
                if kind == "done":
                    completed = True
                    continue  # Native iterator/session must exit before success.
                if kind == "error":
                    failed = True
                    self.content["errorCode"] = event.get("code", "CHAT_UNAVAILABLE")
                    continue
                if kind in ("text_delta", "reasoning_delta"):
                    key = "text" if kind == "text_delta" else "reasoning"
                    self.content[key] += str(event.get("text", ""))
                elif kind == "tool_call":
                    self.content["tools"].append(str(event.get("tool", "")))
                elif kind in ("workflow_confirm", "interaction_required"):
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
                self.content["delivery"] = "completed"
            await self.save()
            await self.emit({"type": "done" if self.content["delivery"] == "completed" else "error",
                             "code": self.content.get("errorCode"),
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

    async def stream(self):
        try:
            while True:
                event = await self.pending.get()
                if event is None:
                    return
                yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
        finally:
            self.detach()

    def detach(self):
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
