"""Real ChatRunner adapter: b-side SSE protocol over the runtime ChatLoop.

The runtime ChatLoop is transport-free and synchronous per turn; the adapter
runs each turn in a thread and replays the buffered emitter events through the
b-side ChatRunner protocol (JSON-safe dicts). Composition-root code: it is the
only module that connects the two services.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator


class ChatLoopRunner:
    """ChatRunner over agent_workflow_runtime.chat.ChatLoop."""

    def __init__(
        self,
        *,
        model_factory,
        model_reference: str,
        environment: str,
        reader,
        conversation_store,
        history_loader,
        personal_memory=None,
        system_prompt: str | None = None,
    ) -> None:
        self._model_factory = model_factory
        self._model_reference = model_reference
        self._environment = environment
        self._reader = reader
        self._conversation_store = conversation_store
        self._history_loader = history_loader
        self._personal_memory = personal_memory
        self._system_prompt = system_prompt

    async def iterate(
        self, *, user_id: str, conversation_id: int, text: str,
        turn_id: str,
    ) -> AsyncIterator[dict[str, Any]]:
        from skillweave_contracts import TrustedContext

        from agent_workflow_runtime.chat.events import (
            DONE, ERROR, TEXT_DELTA, TOOL_CALL, WORKFLOW_CONFIRM,
            ListEmitter,
        )
        from agent_workflow_runtime.chat.loop import ChatLoop
        from agent_workflow_runtime.chat.persistence import ConversationAdmissionError

        owner = TrustedContext.from_mapping({
            "userId": user_id, "environment": self._environment,
        })
        emitter = ListEmitter()
        def run():
            with self._conversation_store.session(
                owner, str(conversation_id), turn_id,
            ) as (saver, thread_id):
                prompt = (self._system_prompt(owner)
                          if callable(self._system_prompt) else self._system_prompt)
                loop = ChatLoop(
                    model_factory=self._model_factory,
                    model_reference=self._model_reference, owner=owner,
                    conversation_id=str(conversation_id), reader=self._reader,
                    control_request_id=f"chat-{turn_id}",
                    emitter=emitter, system_prompt=prompt,
                    checkpointer=saver, thread_id=thread_id,
                    personal_memory=self._personal_memory,
                    history_loader=lambda: self._history_loader(
                        user_id, conversation_id, int(turn_id)),
                )
                loop.turn(text)
        try:
            await asyncio.to_thread(run)
        except ConversationAdmissionError as exc:
            yield {"type": "error", "code": str(exc)}
            return
        except Exception as exc:  # noqa: BLE001
            yield {"type": "error", "code": type(exc).__name__}
            return
        for kind, payload in emitter.events:
            if kind == TEXT_DELTA:
                yield {"type": "text_delta", "text": payload.get("text", "")}
            elif kind == TOOL_CALL:
                # Tool activity is not surfaced to the user; whitelist holds.
                continue
            elif kind == WORKFLOW_CONFIRM:
                yield {
                    "type": "workflow_confirm",
                    "workflowKey": payload.get("workflowKey"),
                    "title": payload.get("title"),
                }
            elif kind == ERROR:
                yield {"type": "error", "code": payload.get("code", "CHAT_ERROR")}
            elif kind == DONE:
                break
        yield {"type": "done"}
