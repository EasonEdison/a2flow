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

from collections.abc import AsyncIterator, Mapping, Sequence
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from .processing_tasks import ProcessingContext


# 原生检查结果由共享契约定义,不让 Runtime 反向依赖产品协议。
from skillweave_contracts.chat_result import RuntimeTurnInspection as RuntimeTurnInspection


# 真实执行通过迭代接口交付增量,已完成恢复直接读取最终结果, 产品层无需识别底层图对象。
class ChatStream(Protocol):
    """Live native runner provides this stream; recovery consumes a final result."""

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
        """Return NOT_STARTED, BUSY, COMPLETED (with result), or NEEDS_REVIEW.

        Inspection shares native execution admission. An expired product lease
        alone is never evidence that a model or business operation may replay.
        """
        ...
