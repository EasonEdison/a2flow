"""One model/tool round trip for an ordinary conversation turn.

Transport-free: streaming deltas and structured events go to a ChatEmitter;
HTTP/SSE wiring belongs to the assembly layer. The loop never starts a
workflow run and never feeds chat text into a running node.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from langchain.tools import ToolRuntime
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from skillweave_contracts.models import (
    ConversationInvocationScope,
    TrustedInvocationContext,
)

from .events import ChatEmitter, DONE, ERROR, ListEmitter, TEXT_DELTA, TOOL_CALL
from ..service import require_owner
from .tools import _EMITTER, build_chat_tools

_MAX_TOOL_ROUNDS = 8


class ChatLoopError(Exception):
    """A turn failed before a usable reply existed."""


def _close_model(model):
    client = getattr(model, "client", None)
    if callable(getattr(client, "close", None)):
        client.close()
    async_client = getattr(model, "async_client", None)
    close = getattr(async_client, "close", None)
    if callable(close):
        result = close()
        if hasattr(result, "__await__"):
            asyncio.run(result)


class ChatLoop:
    def __init__(
        self,
        *,
        model_factory,
        model_reference: str,
        owner,
        conversation_id: str,
        reader,
        control_request_id: str,
        emitter: ChatEmitter | None = None,
        system_prompt: str | None = None,
        tools: list | None = None,
        history: list | None = None,
    ) -> None:
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
        self._history: list = [
            (HumanMessage(content=str(text))
             if role == "user" else AIMessage(content=str(text)))
            for role, text in (history or [])[-40:]
        ]

    @property
    def history(self) -> list:
        return list(self._history)

    def turn(self, user_text: str) -> str:
        if type(user_text) is not str or not user_text.strip():
            raise ChatLoopError("EMPTY_USER_MESSAGE")
        token = _EMITTER.set(self._emitter)
        try:
            return self._run_turn(user_text.strip())
        finally:
            _EMITTER.reset(token)

    def _tools_ready(self) -> list:
        if self._tools is not None:
            return list(self._tools)
        return list(
            build_chat_tools(
                reader=self._reader,
                trusted_context=self._owner,
                conversation_id=self._conversation_id,
                control_request_id=self._control_request_id,
            )
        )

    def _messages(self):
        base = []
        if self._system_prompt:
            base.append(SystemMessage(content=self._system_prompt))
        return base + self._history

    def _run_turn(self, user_text: str) -> str:
        tools = self._tools_ready()
        human = HumanMessage(content=user_text)
        pending = self._messages() + [human]
        for _ in range(_MAX_TOOL_ROUNDS):
            model = self._model_factory.create(self._model_reference, self._owner)
            try:
                bound = model.bind_tools(tools)
                content_parts, calls = self._stream_once(bound, pending)
            finally:
                _close_model(model)
            if not calls:
                final = "".join(content_parts)
                self._emitter.emit(DONE, {"content": final})
                self._history.append(human)
                self._history.append(AIMessage(content=final))
                return final
            assistant = AIMessage(
                content="".join(content_parts),
                tool_calls=[
                    {"name": call["name"], "args": call["args"], "id": call["id"]}
                    for call in calls
                ],
            )
            self._history.append(human)
            self._history.append(assistant)
            tool_messages = []
            for call in calls:
                self._emitter.emit(TOOL_CALL, {"tool": call["name"]})
                tool_messages.append(self._invoke_tool(call, tools))
            self._history.extend(tool_messages)
            pending = self._messages()
        raise ChatLoopError("TOO_MANY_TOOL_ROUNDS")

    def _stream_once(self, bound, messages):
        content_parts: list[str] = []
        calls: dict[int, dict[str, str]] = {}
        try:
            for chunk in bound.stream(messages):
                for text in self._text_deltas(chunk):
                    content_parts.append(text)
                    self._emitter.emit(TEXT_DELTA, {"text": text})
                for call_chunk in getattr(chunk, "tool_call_chunks", None) or []:
                    if isinstance(call_chunk, dict):
                        index = call_chunk.get("index", 0)
                        entry = calls.setdefault(index, {"id": "", "name": "", "args": ""})
                        if call_chunk.get("id"):
                            entry["id"] = call_chunk["id"]
                        if call_chunk.get("name"):
                            entry["name"] = call_chunk["name"]
                        entry["args"] += call_chunk.get("args") or ""
                    else:
                        index = getattr(call_chunk, "index", 0)
                        entry = calls.setdefault(index, {"id": "", "name": "", "args": ""})
                        if getattr(call_chunk, "id", None):
                            entry["id"] = getattr(call_chunk, "id")
                        if getattr(call_chunk, "name", None):
                            entry["name"] = getattr(call_chunk, "name")
                        entry["args"] += getattr(call_chunk, "args", "") or ""
        except ChatLoopError:
            raise
        except Exception as exc:
            self._emitter.emit(
                ERROR, {"code": "MODEL_STREAM_FAILED", "reason": type(exc).__name__}
            )
            raise ChatLoopError("MODEL_STREAM_FAILED") from exc
        parsed = []
        for entry in calls.values():
            if not entry["name"]:
                self._emitter.emit(ERROR, {"code": "INVALID_TOOL_CALL"})
                raise ChatLoopError("INVALID_TOOL_CALL")
            try:
                args = json.loads(entry["args"]) if entry["args"] else {}
            except ValueError:
                self._emitter.emit(ERROR, {"code": "INVALID_TOOL_ARGUMENTS"})
                raise ChatLoopError("INVALID_TOOL_ARGUMENTS")
            if type(args) is not dict:
                self._emitter.emit(ERROR, {"code": "INVALID_TOOL_ARGUMENTS"})
                raise ChatLoopError("INVALID_TOOL_ARGUMENTS")
            parsed.append({"id": entry["id"], "name": entry["name"], "args": args})
        return content_parts, parsed

    @staticmethod
    def _text_deltas(chunk) -> list[str]:
        content = getattr(chunk, "content", None)
        if isinstance(content, str):
            return [content] if content else []
        if isinstance(content, list):
            result = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str) and text:
                        result.append(text)
                elif isinstance(item, str) and item:
                    result.append(item)
            return result
        return []

    def _invoke_tool(self, call: dict, tools: list) -> ToolMessage:
        tool = next((item for item in tools if item.name == call["name"]), None)
        if tool is None:
            self._emitter.emit(ERROR, {"code": "UNKNOWN_TOOL"})
            raise ChatLoopError("UNKNOWN_TOOL")
        invocation = TrustedInvocationContext(
            trusted_context=self._owner,
            invocation_scope=ConversationInvocationScope(
                conversation_id=self._conversation_id
            ),
            control_request_id=self._control_request_id,
        )
        runtime = ToolRuntime(
            state=None,
            context=invocation,
            config={"configurable": {"thread_id": self._conversation_id}},
            stream_writer=None,
            tool_call_id=call["id"],
            store=None,
        )
        try:
            message = tool.invoke(
                {
                    "name": call["name"],
                    "args": {**call["args"], "runtime": runtime},
                    "id": call["id"],
                    "type": "tool_call",
                }
            )
        except Exception as exc:
            self._emitter.emit(
                ERROR, {"code": "TOOL_EXECUTION_FAILED", "reason": type(exc).__name__}
            )
            raise ChatLoopError("TOOL_EXECUTION_FAILED") from exc
        content = message.content
        artifact = getattr(message, "artifact", None) or {}
        text = content if isinstance(content, str) else json.dumps(
            content, ensure_ascii=False
        )
        return ToolMessage(
            content=text,
            tool_call_id=call["id"],
            name=call["name"],
            artifact=artifact,
        )
