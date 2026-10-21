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

from typing import Any, AsyncIterator, Literal, Protocol, TypedDict, TYPE_CHECKING


if TYPE_CHECKING:
    from .processing_tasks import ProcessingContext


class RuntimeTurnInspection(TypedDict):
    status: Literal["NOT_STARTED", "BUSY", "COMPLETED", "NEEDS_REVIEW"]
    events: list[dict[str, Any]]


class ChatStream(Protocol):
    """Live runner and completed-event replay both provide this stream."""
    def iterate(self, *, user_id: int, conversation_id: int,
                      text: str,
                      turn_id: str,
                      run_references: tuple[dict[str, Any], ...] = (),
                      processing_context: ProcessingContext | None = None,
                      ) -> AsyncIterator[dict[str, Any]]: ...

class ChatRunner(ChatStream, Protocol):
    """Native runner additionally provides authoritative execution facts."""

    async def inspect_turn(self, *, user_id: int, conversation_id: int,
                           turn_id: str) -> RuntimeTurnInspection:
        """Return NOT_STARTED, BUSY, COMPLETED (with events), or NEEDS_REVIEW.

        Inspection shares native execution admission. An expired product lease
        alone is never evidence that a model or business operation may replay.
        """
        ...
