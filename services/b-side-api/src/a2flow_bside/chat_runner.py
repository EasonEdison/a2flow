"""Chat runner protocol: the SSE bridge depends only on this interface.

The real engine (Deep Agents chat loop with use_skill and workflow-confirm
cards) is wired by the assembly in a later slice; offline tests inject a
scripted fake. Events are plain JSON-safe dicts:

- {"type": "text_delta", "text": "..."}      streamed assistant text
- {"type": "reasoning_delta", "text": "..."} provider-returned visible reasoning
- {"type": "tool_call", "tool": "..."}      name only, never arguments/results
- {"type": "workflow_confirm", "workflowKey": "...", "title": "..."}
- {"type": "interaction_required", "runId": "..."}
- {"type": "error", "code": "..."}           runner-level failure
- {"type": "done"}                           terminal marker
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, AsyncIterator, Literal, Protocol, TypedDict

if TYPE_CHECKING:
    from .processing_tasks import ProcessingContext


# 执行层检查返回权威轮次状态; 已完成时同时提供可重建的公开事件。
class RuntimeTurnInspection(TypedDict):
    status: Literal["NOT_STARTED", "BUSY", "COMPLETED", "NEEDS_REVIEW"]
    events: list[dict[str, Any]]


# 真实执行与已完成事件回放共用迭代接口, 产品层无需识别底层图对象。
class ChatStream(Protocol):
    """Live runner and completed-event replay both provide this stream."""

    # 普通方法返回异步迭代器; 这里声明输出契约, 不另建模型循环。
    def iterate(
        self,
        *,
        user_id: int,
        conversation_id: int,
        text: str,
        turn_id: str,
        run_references: Sequence[Mapping[str, Any]] = (),
        processing_context: ProcessingContext | None = None,
    ) -> AsyncIterator[dict[str, Any]]: ...


# 只有原生执行器负责判断可否执行, 产品租约过期不能证明尚未运行。
class ChatRunner(ChatStream, Protocol):
    """Native runner additionally provides authoritative execution facts."""

    # 检查与执行共享同一准入边界, 未知结果必须保留待核对状态。
    async def inspect_turn(
        self, *, user_id: int, conversation_id: int, turn_id: str
    ) -> RuntimeTurnInspection:
        """Return NOT_STARTED, BUSY, COMPLETED (with events), or NEEDS_REVIEW.

        Inspection shares native execution admission. An expired product lease
        alone is never evidence that a model or business operation may replay.
        """
        ...
