"""Conversation adapter over the shared Deep Agents SDK factory.

ChatLoop is a compatibility name, not a handwritten ReAct loop.
Durable conversation migration is a separate assembly concern.
"""

import asyncio
from uuid import uuid4

from langchain.agents.middleware import AgentMiddleware, hook_config
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from skillweave_contracts.models import (
    ConversationInvocationScope, TrustedInvocationContext,
)

from ..assembly import build_agent
from ..service import require_owner
from .events import DONE, ERROR, ListEmitter, TEXT_DELTA, TOOL_CALL
from .tools import (
    _EMITTER,
    AbilityModelArgs,
    ProposeModelArgs,
    RenderModelArgs,
    UseSkillModelArgs,
    build_chat_tools,
)


class ChatLoopError(Exception):
    """The SDK did not complete the turn."""


class _InteractiveCardStop(AgentMiddleware):
    """Use the SDK's public jump hook after an interactive card is saved."""

    def __init__(self, chat_assets):
        self._chat_assets = chat_assets

    @staticmethod
    def _batch_rejection(request):
        messages = request.state.get("messages", ())
        calls = getattr(messages[-1], "tool_calls", ()) if messages else ()
        renders = [call for call in calls if call.get("name") == "render_application"]
        if not renders:
            return None
        first_render_id = renders[0].get("id")
        if (
            len(calls) == 1
            and request.tool_call.get("id") == first_render_id
        ):
            return None
        if request.tool_call.get("id") == first_render_id:
            return None
        return ToolMessage(
            content="Application rendering must be the only operation in its tool batch",
            name=request.tool_call["name"],
            tool_call_id=request.tool_call["id"],
            status="error",
        )

    def wrap_tool_call(self, request, handler):
        rejection = self._batch_rejection(request)
        if rejection is not None:
            return rejection
        return handler(request)

    async def awrap_tool_call(self, request, handler):
        rejection = self._batch_rejection(request)
        if rejection is not None:
            return rejection
        return await handler(request)

    @hook_config(can_jump_to=["end"])
    def before_model(self, state, runtime):
        del state, runtime
        if self._chat_assets.waiting_action() is not None:
            return {"jump_to": "end"}
        return None


def _close_model(model):
    client = getattr(model, "client", None)
    if callable(getattr(client, "close", None)):
        client.close()
    close = getattr(getattr(model, "async_client", None), "close", None)
    if callable(close):
        result = close()
        if hasattr(result, "__await__"):
            asyncio.run(result)


class ChatLoop:
    def __init__(
        self, *, model_factory, model_reference, owner, conversation_id,
        reader, control_request_id, emitter=None, system_prompt=None,
        tools=None, history=None, checkpointer=None, thread_id=None,
        history_loader=None, personal_memory=None,
        chat_assets=None,
    ):
        require_owner(owner)
        if type(conversation_id) is not str or not conversation_id:
            raise ChatLoopError("CONVERSATION_ID_REQUIRED")
        if type(control_request_id) is not str or not control_request_id:
            raise ChatLoopError("CONTROL_REQUEST_ID_REQUIRED")
        self._model_factory = model_factory
        self._model_reference = model_reference
        self._owner = owner
        self._conversation_id = conversation_id
        self._reader = reader
        self._control_request_id = control_request_id
        self._emitter = emitter if emitter is not None else ListEmitter()
        self._system_prompt = system_prompt
        self._tools = tools
        if (checkpointer is None) != (thread_id is None):
            raise ValueError("CHECKPOINT_AND_THREAD_REQUIRED_TOGETHER")
        self._checkpointer = checkpointer
        self._thread_id = thread_id
        self._history_loader = history_loader
        self._personal_memory = personal_memory
        self._chat_assets = chat_assets
        self._history = [
            HumanMessage(content=str(text)) if role == "user"
            else AIMessage(content=str(text)) for role, text in (history or [])
        ]

    @property
    def history(self):
        return list(self._history)

    def turn(self, user_text):
        if type(user_text) is not str or not user_text.strip():
            raise ChatLoopError("EMPTY_USER_MESSAGE")
        token = _EMITTER.set(self._emitter)
        model = None
        try:
            if self._chat_assets is not None:
                self._chat_assets.begin_turn()
            model = self._model_factory.create(self._model_reference, self._owner)
            tools = self._tools if self._tools is not None else build_chat_tools(
                reader=self._reader, trusted_context=self._owner,
                conversation_id=self._conversation_id,
                control_request_id=self._control_request_id,
                chat_assets=self._chat_assets,
            )
            from ..personal_memory import PersonalMemoryMiddleware
            middleware = ([PersonalMemoryMiddleware(self._personal_memory, self._owner)]
                          if self._personal_memory is not None else [])
            if self._chat_assets is not None:
                middleware.append(_InteractiveCardStop(self._chat_assets))
            validators = {
                "use_skill": UseSkillModelArgs.model_validate,
                "propose_workflow_run": ProposeModelArgs.model_validate,
            }
            if self._chat_assets is not None:
                validators.update({
                    "execute_ability": AbilityModelArgs.model_validate,
                    "render_application": RenderModelArgs.model_validate,
                })
            graph = build_agent(
                model, tools,
                validators,
                harness_profile_key=model.configuration.harness_profile_key,
                context_schema=TrustedInvocationContext,
                system_prompt=self._system_prompt,
                checkpointer=self._checkpointer,
                middleware=middleware,
            )
            context = TrustedInvocationContext(
                trusted_context=self._owner,
                invocation_scope=ConversationInvocationScope(
                    conversation_id=self._conversation_id,
                ),
                control_request_id=self._control_request_id,
            )
            config = {"recursion_limit": 64, "configurable": {
                "thread_id": self._thread_id or str(uuid4()),
            }}
            previous = self._history
            if self._checkpointer is not None:
                snapshot = graph.get_state(config)
                if snapshot.next:
                    raise ChatLoopError("INCOMPLETE_PREVIOUS_TURN")
                if snapshot.values:
                    previous = snapshot.values.get("messages", [])
                    initial = []
                else:
                    previous = (self._history_loader() if self._history_loader
                                else self._history)
                    initial = previous
            else:
                initial = previous
            messages = initial + [HumanMessage(content=user_text.strip())]
            seen_calls = {
                call["id"] for message in previous
                for call in getattr(message, "tool_calls", ())
            }
            for mode, event in graph.stream(
                {"messages": messages}, context=context,
                config=config,
                stream_mode=["messages", "values"],
            ):
                if mode == "messages":
                    message, metadata = event
                    if metadata.get("langgraph_node") != "model":
                        continue
                    for text in self._text_deltas(message):
                        self._emitter.emit(TEXT_DELTA, {"text": text})
                    reasoning = [block["reasoning"] for block in message.content_blocks
                                 if block.get("type") == "reasoning"
                                 and isinstance(block.get("reasoning"), str)]
                    # The existing DeepSeek adapter preserves this native field.
                    # Prefer SDK blocks if present; never emit it twice.
                    native_reasoning = message.additional_kwargs.get("reasoning_content")
                    if not reasoning and isinstance(native_reasoning, str):
                        reasoning = [native_reasoning]
                    for text in reasoning:
                        if text:
                            self._emitter.emit("reasoning_delta", {"text": text})
                else:
                    messages = event.get("messages", messages)
                    for message in messages:
                        for call in getattr(message, "tool_calls", ()):
                            if call["id"] not in seen_calls:
                                seen_calls.add(call["id"])
                                self._emitter.emit(TOOL_CALL, {"tool": call["name"]})
            waiting = (
                None
                if self._chat_assets is None
                else self._chat_assets.waiting_action()
            )
            if waiting is not None:
                self._history = list(messages)
                self._emitter.emit(
                    "waiting_action", {"cardId": waiting["cardId"]},
                )
                return None
            last = messages[-1]
            if not isinstance(last, AIMessage) or last.tool_calls:
                raise ChatLoopError("INCOMPLETE_AGENT_TURN")
            self._history = list(messages)
            final = "".join(self._text_deltas(last))
            self._emitter.emit(DONE, {"content": final})
            return final
        except Exception as exc:
            self._emitter.emit(ERROR, {"code": "MODEL_STREAM_FAILED",
                                       "reason": type(exc).__name__})
            raise ChatLoopError("MODEL_STREAM_FAILED") from exc
        finally:
            _EMITTER.reset(token)
            if model is not None:
                _close_model(model)

    @staticmethod
    def _text_deltas(message):
        content = message.content
        if isinstance(content, str):
            return [content] if content else []
        return [item["text"] for item in content
                if isinstance(item, dict) and item.get("type") == "text"
                and isinstance(item.get("text"), str) and item["text"]]
