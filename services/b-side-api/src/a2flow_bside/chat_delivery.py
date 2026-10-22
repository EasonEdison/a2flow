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
from contextlib import suppress
from typing import Any, NotRequired, Protocol, TypedDict

# 公开结果归并属于中立契约,产品层仅绑定页面消息身份和保存展示。
from skillweave_contracts.chat_result import (
    ChatResultAccumulator,
    ChatTurnResult,
    validate_result,
)
from skillweave_contracts.chat_state import FINAL_DELIVERIES
from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from .chat_runner import ChatStream
from .persistence_types import MessageRecord
from .processing_tasks import ProcessingContext


# 展示投影只要求更新消息, 普通仓库与带执行代际隔离的写入器都实现此接口。
class MessageProjection(Protocol):
    """Both direct messages and generation-fenced writes persist projections."""

    def update_delivery(
        self, *, conversation_id: int, message_id: int, content: dict[str, Any]
    ) -> None: ...


def _bind_content(content: dict[str, Any], *, input_id: int, assistant_id: int) -> dict[str, Any]:
    copied = copy.deepcopy(content)
    execution = copied["execution"]
    execution.update(
        turnId=str(input_id), inputMessageId=str(input_id), assistantMessageId=str(assistant_id)
    )
    # 原生结果使用中立片段序号;产品绑定沿用历史 text:助手消息:序号 协议。
    part_ids: dict[str, str] = {}
    for part in copied["parts"]:
        if part.get("type") == "text":
            current = part["id"]
            suffix = current.removeprefix("text:")
            if suffix.isdigit():
                part_ids[current] = f"text:{assistant_id}:{suffix}"
                part["id"] = part_ids[current]
    for event in copied["events"]:
        event.update(
            turnId=str(input_id), inputMessageId=str(input_id), assistantMessageId=str(assistant_id)
        )
        if "partId" in event:
            event["partId"] = part_ids.get(event["partId"], event["partId"])
        if event.get("type") == "personal_workflow_created":
            event["messageId"] = str(assistant_id)
    return copied


def restore_content(
    result: ChatTurnResult,
    *,
    input_message: MessageRecord,
    assistant_message: MessageRecord,
) -> dict[str, Any]:
    """Repair display from a complete snapshot, without event/model/tool replay."""
    checked = validate_result(result)
    if checked["turnId"] != str(input_message["id"]):
        raise ValueError("CHAT_RESULT_TURN_ID_MISMATCH")
    content = _bind_content(
        checked["content"], input_id=input_message["id"], assistant_id=assistant_message["id"]
    )
    previous = assistant_message.get("content", {})
    # 这些是产品关系,不进入原生结果或变成第二份模型历史。
    for field in ("continuation", "processingTaskId"):
        if field in previous:
            content[field] = copy.deepcopy(previous[field])
    return content


# 运行参数固定绑定用户、会话及轮次, 引用和处理上下文仅按需传入。
class RunnerArguments(TypedDict):
    user_id: int
    conversation_id: int
    text: str
    turn_id: str
    run_references: NotRequired[Sequence[Mapping[str, Any]]]
    processing_context: NotRequired[ProcessingContext]


# 此类消费执行事件并保存展示, 不拥有模型工具循环, 也不决定业务重试。
class ChatDelivery(ChatResultAccumulator):
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
        super().__init__(
            turn_id=str(input_message["id"]), text_part_prefix=f"text:{assistant_message['id']}"
        )
        self.messages, self.runner = messages, runner
        self.user_id, self.conversation_id, self.text = user_id, conversation_id, text
        self.input_id, self.assistant_id = input_message["id"], assistant_message["id"]
        self.run_references = copy.deepcopy(list(run_references))
        self.processing_context = copy.deepcopy(processing_context)
        self.turn_id = str(self.input_id)
        # 卡片续聊和异常任务归产品管理,不作为原生执行事实。
        if isinstance(assistant_message.get("content", {}).get("continuation"), dict):
            self.content["continuation"] = copy.deepcopy(
                assistant_message["content"]["continuation"]
            )
        if self.processing_context is not None:
            self.content["processingTaskId"] = self.processing_context["taskId"]
        # 限制实时订阅队列长度; 持久化调度可以替换为事件日志接收器。
        self.pending: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(
            maxsize=64,
        )
        self.detached = False
        self.output_sequence = 0
        # Native delivery and durable journaling supply the same explicit event sink.
        self.emit: Callable[[dict[str, Any]], Awaitable[None]] = self._emit

    # 实时事件附上单调序号和产品消息身份, 断开订阅后停止入队。
    async def _emit(self, event: dict[str, Any]) -> None:
        self.output_sequence += 1
        if not self.detached:
            await self.pending.put(
                {
                    **event,
                    "sequence": self.output_sequence,
                    "messageId": str(self.assistant_id),
                    "inputMessageId": str(self.input_id),
                }
            )

    # 保存展示副本; 底层写入器可额外验证当前执行代际。
    async def save(self) -> None:
        await asyncio.to_thread(
            self.messages.update_delivery,
            conversation_id=self.conversation_id,
            message_id=self.assistant_id,
            content=_bind_content(
                self.content, input_id=self.input_id, assistant_id=self.assistant_id
            ),
        )

    async def produce(self) -> None:
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
            # 原始输入消息 ID 用作稳定轮次 ID, 重复投影不生成新执行身份。
            arguments: RunnerArguments = {
                "user_id": self.user_id,
                "conversation_id": self.conversation_id,
                "text": self.text,
                "turn_id": str(self.input_id),
            }
            # 仅传入已保存的引用和处理上下文, 不重新从客户端补取内容。
            if self.run_references:
                arguments["run_references"] = self.run_references
            if self.processing_context is not None:
                arguments["processing_context"] = self.processing_context
            # 正常流和恢复快照共用同一纯归并器;本层只负责 IO 和产品身份。
            iterator = self.runner.iterate(**arguments)
            async for incoming in iterator:
                event = self.consume(incoming)
                if event is None:
                    continue
                if event.get("type") in {
                    "waiting_action",
                    "application_rendered",
                    "personal_workflow_created",
                    "workflow_confirm",
                    "interaction_required",
                }:
                    event.update(
                        turnId=self.turn_id,
                        inputMessageId=str(self.input_id),
                        assistantMessageId=str(self.assistant_id),
                    )
                if event.get("type") == "personal_workflow_created":
                    event["messageId"] = str(self.assistant_id)
                    await self.save()
                    last_save = time.monotonic()
                await self.emit(event)
                if time.monotonic() - last_save >= 1:
                    await self.save()
                    last_save = time.monotonic()
            if not self.completed or self.failed:
                self.content["delivery"] = "failed"
                self.content.setdefault("errorCode", "CHAT_INCOMPLETE")
            else:
                # 迭代器退出证明原生事务已落库,之后才能提交产品终态。
                result = self.finish()
                self.content.update(result["content"])
            # 先保存终态投影, 再通知订阅者结束, 避免刷新后缺少最终回答。
            await self.save()
            await self.emit(
                {
                    "type": "done"
                    if self.content["delivery"] in FINAL_DELIVERIES
                    else "error",
                    "code": self.content.get("errorCode"),
                    "finalModelMessageId": self.final_model_message_id,
                    "content": _bind_content(
                        self._public_content(),
                        input_id=self.input_id,
                        assistant_id=self.assistant_id,
                    ),
                }
            )
        # 异常或取消只标记结果未确认, 不能自动重新运行可能发生过的工具。
        except (Exception, asyncio.CancelledError):
            self.content["delivery"] = "unconfirmed"
            self.content["errorCode"] = "CHAT_UNCONFIRMED"
            # 投影保存失败时保留原持久化运行状态, 不伪造成功。
            with suppress(Exception):
                await self.save()
            await self.emit({"type": "error", "code": "CHAT_UNCONFIRMED"})
        finally:
            try:
                # 无论正常、异常或取消都关闭原生迭代器, 释放执行会话资源。
                close = getattr(iterator, "aclose", None)
                if close is not None:
                    await close()
            finally:
                # 仍有订阅者时发送队列结束标记, 断连时不再等待队列消费。
                if not self.detached:
                    await self.pending.put(None)

    # 实时 SSE 消费与生产任务分离, 订阅结束只解除展示连接。
    async def stream(self) -> AsyncIterator[str]:
        try:
            while True:
                event = await self.pending.get()
                if event is None:
                    return
                yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
        finally:
            self.detach()

    # 清空待发事件并标记断连, 使后台生产者可继续保存真实结果。
    def detach(self) -> None:
        self.detached = True
        # Also safe before the async generator starts (disconnect during headers).
        while not self.pending.empty():
            self.pending.get_nowait()


# 响应对象负责可靠解除订阅, 不承担业务执行的取消或重试。
class ChatStreamingResponse(StreamingResponse):
    def __init__(self, delivery: ChatDelivery) -> None:
        self.delivery = delivery
        super().__init__(
            delivery.stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    # 即便连接在响应头阶段退出, 也执行 detach 清理订阅状态。
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.delivery.detach()
