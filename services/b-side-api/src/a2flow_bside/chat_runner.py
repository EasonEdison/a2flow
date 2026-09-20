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

from typing import Any, AsyncIterator, Protocol


class ChatRunner(Protocol):
    async def iterate(self, *, user_id: int, conversation_id: int,
                      text: str,
                      turn_id: str,
                      ) -> AsyncIterator[dict[str, Any]]: ...
