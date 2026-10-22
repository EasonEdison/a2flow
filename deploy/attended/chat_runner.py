"""Real ChatRunner adapter: b-side SSE protocol over the runtime ChatLoop.

The runtime ChatLoop is transport-free and synchronous per turn; the adapter
runs each turn in a thread and forwards bounded live emitter events through the
b-side ChatRunner protocol (JSON-safe dicts). Composition-root code: it is the
only module that connects the two services.
"""

from __future__ import annotations

import asyncio
import queue
import threading
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, Protocol

from a2flow_asset_store import AssetReader
from a2flow_asset_store.personal_workflows import PersonalWorkflowReader
from a2flow_bside.chat_runner import RuntimeTurnInspection
from agent_workflow_runtime.chat.cards import ChatObservation
from agent_workflow_runtime.chat.persistence import ConversationStore
from agent_workflow_runtime.chat.rpc_assets import RpcChatAssets
from agent_workflow_runtime.model_factory import DeepSeekModelFactory
from agent_workflow_runtime.personal_memory import PersonalMemory
from langchain_core.messages import BaseMessage
from skillweave_contracts import TrustedContext
from skillweave_contracts.chat_result import ChatResultAccumulator

if TYPE_CHECKING:
    from agent_workflow_runtime.chat.processing import ProcessingProvider
    from agent_workflow_runtime.chat.workflow_results import WorkflowRunProvider


class ChatAssetsFactory(Protocol):
    """The two supported calls are ordinary admission and task-bound admission."""

    def __call__(
        self,
        owner: TrustedContext,
        conversation_id: str,
        control_request_id: str = "chat-action",
        *,
        processing_context: Mapping[str, Any] | None = None,
        processing_turn_id: str | None = None,
    ) -> RpcChatAssets: ...


class ChatObservationLoader(Protocol):
    def __call__(
        self,
        owner: TrustedContext,
        conversation_id: str,
        *,
        after_sequence: int,
        limit: int = 100,
    ) -> Sequence[ChatObservation]: ...


HistoryLoader = Callable[[int, int, int], Sequence[BaseMessage]]
SystemPrompt = str | Callable[[TrustedContext], str]


class ChatLoopRunner:
    """ChatRunner over agent_workflow_runtime.chat.ChatLoop."""

    def __init__(
        self,
        *,
        model_factory: DeepSeekModelFactory,
        model_reference: str,
        environment: str,
        reader: AssetReader | PersonalWorkflowReader,
        conversation_store: ConversationStore,
        history_loader: HistoryLoader,
        personal_memory: PersonalMemory | None = None,
        personal_workflows: PersonalWorkflowReader | None = None,
        assets_factory: ChatAssetsFactory | None = None,
        observation_loader: ChatObservationLoader | None = None,
        workflow_run_provider: WorkflowRunProvider | None = None,
        processing_provider: ProcessingProvider | None = None,
        system_prompt: SystemPrompt | None = None,
    ) -> None:
        self._model_factory = model_factory
        self._model_reference = model_reference
        self._environment = environment
        self._reader = reader
        self._conversation_store = conversation_store
        self._history_loader = history_loader
        self._personal_memory = personal_memory
        self._personal_workflows = personal_workflows
        self._assets_factory = assets_factory
        self._observation_loader = observation_loader
        self._workflow_run_provider = workflow_run_provider
        self._processing_provider = processing_provider
        self._system_prompt = system_prompt

    async def inspect_turn(
        self,
        *,
        user_id: int,
        conversation_id: int,
        turn_id: str,
    ) -> RuntimeTurnInspection:
        from skillweave_contracts import TrustedContext

        owner = TrustedContext.from_mapping(
            {
                "userId": user_id,
                "environment": self._environment,
            }
        )
        return await asyncio.to_thread(
            self._conversation_store.inspect_turn,
            owner,
            str(conversation_id),
            turn_id,
        )

    async def iterate(
        self,
        *,
        user_id: int,
        conversation_id: int,
        text: str,
        turn_id: str,
        run_references: Sequence[Mapping[str, Any]] = (),
        processing_context: Mapping[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        from agent_workflow_runtime.chat.events import (
            DONE,
            ERROR,
        )
        from agent_workflow_runtime.chat.loop import ChatLoop
        from agent_workflow_runtime.chat.persistence import ConversationAdmissionError
        from skillweave_contracts import TrustedContext

        if processing_context is not None and (
            self._processing_provider is None or self._assets_factory is None
        ):
            yield {"type": "error", "code": "PROCESSING_ADAPTER_REQUIRED"}
            return
        owner = TrustedContext.from_mapping(
            {
                "userId": user_id,
                "environment": self._environment,
            }
        )
        pending: queue.Queue[tuple[str, Mapping[str, Any]]] = queue.Queue(maxsize=64)
        closed = threading.Event()
        accumulator = ChatResultAccumulator(turn_id=turn_id)
        completion: dict[str, dict[str, Any] | None] = {"payload": None}

        class Emitter:
            def emit(self, kind: str, payload: Mapping[str, Any]) -> None:
                # Capture only the same public application protocol sent to B,
                # never graph state, runnable config or authentication context.
                event = _application_event(kind, payload)
                if event is not None:
                    accumulator.consume(event)
                # A closed transport must not cancel/replay a model/tool turn.
                if kind == DONE:
                    completion["payload"] = dict(payload)
                    accumulator.consume({"type": "done", **payload})
                    return  # Completion is published after the saver session exits.
                while not closed.is_set():
                    try:
                        pending.put((kind, payload), timeout=0.1)
                        return
                    except queue.Full:
                        pass

        emitter = Emitter()

        def run() -> None:
            with self._conversation_store.session(
                owner,
                str(conversation_id),
                turn_id,
                completion_result=accumulator.finish,
            ) as (saver, thread_id):
                prompt = (
                    self._system_prompt(owner)
                    if callable(self._system_prompt)
                    else self._system_prompt
                )
                observation_loader = self._observation_loader
                loop = ChatLoop(
                    model_factory=self._model_factory,
                    model_reference=self._model_reference,
                    owner=owner,
                    conversation_id=str(conversation_id),
                    reader=self._reader,
                    control_request_id=f"chat-{turn_id}",
                    emitter=emitter,
                    system_prompt=prompt,
                    checkpointer=saver,
                    thread_id=thread_id,
                    personal_memory=self._personal_memory,
                    personal_workflows=self._personal_workflows,
                    workflow_run_provider=self._workflow_run_provider,
                    run_references=run_references,
                    processing_context_value=processing_context,
                    chat_assets=(
                        self._assets_factory(
                            owner,
                            str(conversation_id),
                            f"chat-{turn_id}",
                            processing_context=processing_context,
                            processing_turn_id=turn_id,
                        )
                        if processing_context is not None and self._assets_factory is not None
                        else self._assets_factory(owner, str(conversation_id), f"chat-{turn_id}")
                        if self._assets_factory is not None
                        else None
                    ),
                    observation_loader=(
                        (
                            lambda cursor: observation_loader(
                                owner,
                                str(conversation_id),
                                after_sequence=cursor,
                                limit=100,
                            )
                        )
                        if observation_loader is not None
                        else None
                    ),
                    history_loader=lambda: self._history_loader(
                        user_id, conversation_id, int(turn_id)
                    ),
                )
                loop.turn(text)
                if completion["payload"] is None:
                    if not accumulator.waiting:
                        raise ConversationAdmissionError("TURN_COMPLETION_EVIDENCE_MISSING")
                    # 等待交互结束当前 Agent 轮次,完成卡片后是新轮次,绝不重放。
                    accumulator.consume(
                        {"type": "done", "content": "", "finalModelMessageId": None}
                    )

        def worker() -> None:
            try:
                run()
                emitter.emit(
                    "native_completed",
                    completion["payload"]
                    or {
                        "content": "",
                        "finalModelMessageId": None,
                    },
                )
            except ConversationAdmissionError as exc:
                emitter.emit(ERROR, {"code": str(exc)})
            except Exception:
                emitter.emit(ERROR, {"code": "CHAT_UNAVAILABLE"})
            finally:
                emitter.emit("worker_finished", {})

        # The B-side producer owns this iterator independently of its subscriber.
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        failed = False

        def receive() -> tuple[str, Mapping[str, Any]] | None:
            try:
                return pending.get(timeout=0.1)
            except queue.Empty:
                return None

        try:
            while True:
                queued_event = await asyncio.to_thread(receive)
                if queued_event is None:
                    continue
                kind, payload = queued_event
                if kind == "worker_finished":
                    return
                if kind == "native_completed":
                    yield {"type": "done", **payload}
                    continue
                event = _application_event(kind, payload)
                if event is not None:
                    if kind == ERROR:
                        if failed:
                            continue
                        failed = True
                    yield event
        finally:
            closed.set()
            await asyncio.to_thread(thread.join)


def _application_event(kind: str, payload: Mapping[str, Any]) -> dict[str, Any] | None:
    """One conversion for live delivery and durable projection repair."""
    if kind in ("text_delta", "reasoning_delta"):
        return {
            "type": kind,
            "text": payload.get("text", ""),
            "modelMessageId": payload.get("modelMessageId"),
        }
    if kind == "tool_call":
        return {"type": kind, "tool": payload.get("tool", "")}
    if kind in (
        "tool_call_started",
        "tool_call_finished",
        "a2ui_generation_progress",
        "application_rendered",
        "waiting_action",
        "personal_workflow_created",
    ):
        return {"type": kind, **payload}
    if kind == "workflow_confirm":
        return {
            "type": kind,
            "workflowKey": payload.get("workflowKey"),
            "title": payload.get("title"),
        }
    if kind == "error":
        return {"type": kind, "code": payload.get("code", "CHAT_ERROR")}
    return None
