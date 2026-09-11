"""Public SDK observation hooks; no persistence/control decisions in callbacks."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from uuid import uuid4

from langchain.agents.middleware import AgentMiddleware
from langchain_core.callbacks import BaseCallbackHandler

from .deepseek_model import DeepSeekChat
from .models import ActionRejected
from .service import require_owner


_SCOPE = ContextVar("a2flow_progress_segment", default=None)
_VISIBLE_MODEL = ContextVar("a2flow_visible_model", default=False)


@dataclass
class ProgressScope:
    context: object
    execution_id: str
    sink: object
    unavailable: bool = False

    def emit(self, kind, payload):
        if self.unavailable:
            return
        try:
            self.sink.offer(self, kind, payload)
        except Exception:
            # Capture health is distinct from business/model/Finalizer outcomes.
            self.unavailable = True


@contextmanager
def bind_progress(context, execution_id, sink):
    require_owner(context.trusted_context)
    if context.invocation_scope.kind != "WORKFLOW":
        raise ActionRejected("PROGRESS_WORKFLOW_CONTEXT_REQUIRED")
    scope = ProgressScope(context, execution_id, sink)
    token = _SCOPE.set(scope)
    try:
        yield scope
    finally:
        _SCOPE.reset(token)


def current_progress():
    return _SCOPE.get()


class ProgressCallbacks(BaseCallbackHandler):
    """Only explicitly visible model invocations emit text. Inputs never emitted."""

    run_inline = True
    raise_error = False

    def _emit(self, kind, payload):
        scope = _SCOPE.get()
        if scope is not None and _VISIBLE_MODEL.get():
            scope.emit(kind, payload)

    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
        self._emit("MODEL_STARTED", {"modelCallId": str(run_id)})

    def on_llm_new_token(self, token, *, chunk=None, run_id, **kwargs):
        message = getattr(chunk, "message", None)
        if message is None:
            return
        # Deliberately do not serialize a message, content view, Tool args or raw
        # provider payload. Only these two provider-returned text channels.
        reasoning = message.additional_kwargs.get("reasoning_content")
        if isinstance(reasoning, str) and reasoning:
            self._emit("REASONING_DELTA", {"modelCallId": str(run_id), "text": reasoning})
        if isinstance(message.content, str) and message.content:
            self._emit("TEXT_DELTA", {"modelCallId": str(run_id), "text": message.content})

    def on_llm_end(self, response, *, run_id, **kwargs):
        self._emit("MODEL_RETURNED", {"modelCallId": str(run_id)})

    def on_llm_error(self, error, *, run_id, **kwargs):
        self._emit("MODEL_UNCONFIRMED", {"modelCallId": str(run_id), "code": "MODEL_CALL_ERROR"})


class ProgressMiddleware(AgentMiddleware):
    """Keep the original handler and final native response; observe permitted calls."""

    def wrap_model_call(self, request, handler):
        if _SCOPE.get() is None:
            return handler(request)
        if not isinstance(request.model, DeepSeekChat):
            _SCOPE.get().unavailable = True
            return handler(request)
        token = _VISIBLE_MODEL.set(True)
        try:
            settings = {**request.model_settings, "stream": True}
            return handler(request.override(model_settings=settings))
        finally:
            _VISIBLE_MODEL.reset(token)

    async def awrap_model_call(self, request, handler):
        if _SCOPE.get() is None:
            return await handler(request)
        if not isinstance(request.model, DeepSeekChat):
            _SCOPE.get().unavailable = True
            return await handler(request)
        token = _VISIBLE_MODEL.set(True)
        try:
            return await handler(request.override(
                model_settings={**request.model_settings, "stream": True}))
        finally:
            _VISIBLE_MODEL.reset(token)

    def wrap_tool_call(self, request, handler):
        scope = _SCOPE.get()
        if scope is None:
            return handler(request)
        operation = uuid4().hex
        payload = {"toolOperationId": operation, "toolName": request.tool_call["name"]}
        scope.emit("TOOL_STARTED", payload)
        try:
            result = handler(request)
        except BaseException as error:
            from langgraph.errors import GraphInterrupt
            scope.emit("TOOL_INTERRUPTED" if isinstance(error, GraphInterrupt)
                       else "TOOL_UNCONFIRMED", payload)
            raise
        scope.emit("TOOL_RETURNED", payload)
        return result


@contextmanager
def observe_node(context, operation_id):
    parent = current_progress()
    if parent is None:
        yield
        return
    with parent.sink.capture(context, operation_id) as scope:
        payload = {"nodeOperationId": operation_id}
        scope.emit("NODE_STARTED", payload)
        try:
            yield
        except BaseException as error:
            from langgraph.errors import GraphInterrupt
            scope.emit("NODE_INTERRUPTED" if isinstance(error, GraphInterrupt)
                       else "NODE_UNCONFIRMED", payload)
            raise
        scope.emit("NODE_RETURNED", payload)
