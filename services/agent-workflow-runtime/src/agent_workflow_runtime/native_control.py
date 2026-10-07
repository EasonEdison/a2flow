"""Public synchronous SDK hooks. No scheduler, hidden retries or mutable SDK patch."""

from collections.abc import Callable
from dataclasses import dataclass
from contextvars import ContextVar

from langchain.agents.middleware import AgentMiddleware
from langchain_core.callbacks import BaseCallbackHandler

from .lifecycle import RunStoppedControl
from .models import ActionRejected
from .events import NODE_WAITING, RUN_FAILED


_CURRENT_WORKFLOW_NODE = ContextVar("a2flow_current_workflow_node", default=None)


def current_node_context(fallback):
    """Bound only by the trusted Runtime runner/node wrapper, never model args."""
    context = _CURRENT_WORKFLOW_NODE.get()
    if context is None:
        raise ActionRejected("TRUSTED_NODE_CONTEXT_REQUIRED")
    if (context.trusted_context != fallback.trusted_context
            or context.invocation_scope.kind != "WORKFLOW"
            or context.invocation_scope.run_id != fallback.invocation_scope.run_id):
        raise ActionRejected("RUN_NODE_BINDING_MISMATCH")
    return context


class RunModelCallbacks(BaseCallbackHandler):
    """Inherited by actual main AND summary model calls through RunnableConfig."""

    run_inline = True
    raise_error = True

    def __init__(self, lifecycle, run):
        self.lifecycle, self.run = lifecycle, run

    def _start(self, run_id):
        try:
            context = current_node_context(self.run.context())
            self.lifecycle.admit(self.run.owner, self.run.run_id, context.invocation_scope.node_id,
                                 "MODEL", operation_id=str(run_id))
        except BaseException as error:
            self.lifecycle.observe_fatal(self.run.owner, self.run.run_id, error)
            raise

    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
        self._start(run_id)

    def on_llm_start(self, serialized, prompts, *, run_id, **kwargs):
        self._start(run_id)

    def on_llm_end(self, response, *, run_id, **kwargs):
        self.lifecycle.finish(self.run.owner, self.run.run_id, str(run_id), response)
        self.lifecycle.assert_active(self.run.owner, self.run.run_id)

    def on_llm_error(self, error, *, run_id, **kwargs):
        self.lifecycle.observe_fatal(self.run.owner, self.run.run_id, error)
        # Preserve an already saved response if the SDK emits an error because
        # our on_llm_end raised the stop signal after saving it.
        self.lifecycle.finish(self.run.owner, self.run.run_id, str(run_id),
                              {"errorType": type(error).__name__}, status="UNCONFIRMED")


class BoundNodeMiddleware(AgentMiddleware):
    """Bind callback-visible model/Tool work to one trusted compiled node."""

    def __init__(self, context):
        if context.invocation_scope.kind != "WORKFLOW":
            raise ValueError("WORKFLOW_BINDING_REQUIRED")
        self.context = context

    def _bind(self, request):
        fallback = request.runtime.context
        current_node_context(fallback)
        if (fallback.trusted_context != self.context.trusted_context
                or fallback.invocation_scope.kind != "WORKFLOW"
                or fallback.invocation_scope.run_id
                != self.context.invocation_scope.run_id):
            raise ActionRejected("RUN_NODE_BINDING_MISMATCH")
        return _CURRENT_WORKFLOW_NODE.set(self.context)

    def _invoke(self, handler, request):
        token = self._bind(request)
        try:
            return handler(request)
        finally:
            _CURRENT_WORKFLOW_NODE.reset(token)

    def wrap_model_call(self, request, handler):
        return self._invoke(handler, request)

    def wrap_tool_call(self, request, handler):
        return self._invoke(handler, request)

    async def awrap_model_call(self, request, handler):
        token = self._bind(request)
        try:
            return await handler(request)
        finally:
            _CURRENT_WORKFLOW_NODE.reset(token)

    async def awrap_tool_call(self, request, handler):
        token = self._bind(request)
        try:
            return await handler(request)
        finally:
            _CURRENT_WORKFLOW_NODE.reset(token)


class RunAdmissionMiddleware(AgentMiddleware):
    def __init__(self, lifecycle, node_context=None):
        self.lifecycle, self.node_context = lifecycle, node_context

    def _check(self, context):
        scope = context.invocation_scope
        if scope.kind != "WORKFLOW":
            raise ActionRejected("WORKFLOW_BINDING_REQUIRED")
        self.lifecycle.assert_active(context.trusted_context, scope.run_id)

    def _node(self, fallback):
        if self.node_context is None:
            return current_node_context(fallback)
        current_node_context(self.node_context)
        if (fallback.trusted_context != self.node_context.trusted_context
                or fallback.invocation_scope.run_id
                != self.node_context.invocation_scope.run_id):
            raise ActionRejected("RUN_NODE_BINDING_MISMATCH")
        return self.node_context

    def before_agent(self, state, runtime):
        self._check(runtime.context)

    def before_model(self, state, runtime):
        self._check(runtime.context)

    def after_model(self, state, runtime):
        self._check(runtime.context)

    def after_agent(self, state, runtime):
        self._check(runtime.context)

    def wrap_model_call(self, request, handler):
        self._check(request.runtime.context)
        result = handler(request)
        self._check(request.runtime.context)
        return result

    def wrap_tool_call(self, request, handler):
        context = self._node(request.runtime.context)
        return self.lifecycle.execute(context, "TOOL", lambda: handler(request))


def guarded_node(lifecycle, context, handler):
    """Wrap each owned business node, not an entire Skill as one reusable permit."""
    def invoke(state):
        token = _CURRENT_WORKFLOW_NODE.set(context)
        try:
            return lifecycle.execute(context, "NODE", lambda: handler(state))
        finally:
            _CURRENT_WORKFLOW_NODE.reset(token)
    return invoke


def guarded_router(lifecycle, context, route):
    def invoke(state):
        return lifecycle.execute(context, "ROUTER", lambda: route(state))
    return invoke


@dataclass(frozen=True)
class RunGraphBinding:
    """Explicit trusted assembly binding; raw/uncontrolled graphs are not AF04 entries.

    Factories must use guarded business nodes/routes and RunAdmissionMiddleware
    for Deep Agents. This binds the lifecycle to the compiled graph; it is not
    a generic safety proof for arbitrary user-supplied Python graphs.
    """

    graph: object
    lifecycle: object
    progress: object = None
    failure_observer: Callable[[BaseException], None] | None = None

    def get_state(self, *args, **kwargs):
        return self.graph.get_state(*args, **kwargs)

    def invoke(self, *args, **kwargs):
        return self.graph.invoke(*args, **kwargs)


class ControlledRunRunner:
    """Only this synchronous boundary recognizes our signal after durable STOPPED."""

    def __init__(self, lifecycle, graph_factory, resolve_versions):
        self.lifecycle = lifecycle
        self.graph_factory = graph_factory
        self.resolve_versions = resolve_versions

    def start(self, owner, control_id, definition_key, inputs, entry_node_id, *, stopped_run_id=None):
        run, fresh = self.lifecycle.allocate(
            owner, control_id, definition_key, inputs, entry_node_id, self.resolve_versions,
            stopped_run_id=stopped_run_id,
        )
        if not fresh:
            return self.lifecycle.snapshot(owner, run.run_id)
        invoked = False
        try:
            self.lifecycle.assert_active(owner, run.run_id)
            graph, initial_state = self.graph_factory(run, self.lifecycle)
            invoked = True
            self.invoke(run, graph, initial_state)
        except RunStoppedControl as signal:
            self.lifecycle.raise_observed_fatal(owner, run.run_id)
            saved = self.lifecycle.read(owner, run.run_id)
            if signal.run_id != run.run_id or saved.status != "STOPPED":
                raise
            self.lifecycle.control_status(owner, control_id, "RETURNED")
            return self.lifecycle.snapshot(owner, run.run_id)
        except BaseException as error:
            # invoke handles both first execution and Action continuation. Only
            # setup failures occur before that shared boundary.
            if not invoked:
                self._record_failure(run, None, error)
            try:
                self.lifecycle.control_status(owner, control_id, "UNCONFIRMED")
            except Exception:
                error.add_note("RUN_CONTROL_RECEIPT_SAVE_UNCONFIRMED")
            raise
        self.lifecycle.control_status(owner, control_id, "RETURNED")
        return self.lifecycle.snapshot(owner, run.run_id)

    def invoke(self, run, graph, value):
        if isinstance(graph, RunGraphBinding) and graph.progress is not None:
            with graph.progress.capture(run.context()):
                return self._invoke_controlled(run, graph, value)
        return self._invoke_controlled(run, graph, value)

    def _invoke_controlled(self, run, graph, value):
        """Fresh state or an authorized native reference; STOPPED always rejects."""
        token = _CURRENT_WORKFLOW_NODE.set(run.context())
        try:
            self.lifecycle.assert_active(run.owner, run.run_id)
            if not isinstance(graph, RunGraphBinding) or graph.lifecycle is not self.lifecycle:
                raise ActionRejected("CONTROLLED_GRAPH_BINDING_REQUIRED")
            callbacks = [RunModelCallbacks(self.lifecycle, run)]
            if graph.progress is not None:
                from .progress_observer import ProgressCallbacks
                callbacks.append(ProgressCallbacks())
            result = graph.invoke(
                value, {"configurable": {"thread_id": run.thread_id},
                        "callbacks": callbacks},
                context=run.context(),
            )
            # interrupt means waiting, not a successful completed run.
            self.lifecycle.raise_observed_fatal(run.owner, run.run_id)
            self.lifecycle.assert_active(run.owner, run.run_id)
            pending = tuple(graph.get_state(
                {"configurable": {"thread_id": run.thread_id}}
            ).next or ())
            if not result.get("__interrupt__") and not pending:
                self.lifecycle.succeed(run.owner, run.run_id)
            else:
                for node_id in pending:
                    if isinstance(node_id, str):
                        self.lifecycle.publish_event(
                            NODE_WAITING, run, payload={"nodeId": node_id},
                        )
            return result
        except RunStoppedControl as signal:
            self.lifecycle.raise_observed_fatal(run.owner, run.run_id)
            saved = self.lifecycle.read(run.owner, run.run_id)
            if signal.run_id != run.run_id or saved.status != "STOPPED":
                raise
            return self.lifecycle.snapshot(run.owner, run.run_id)
        except BaseException as error:
            from langgraph.errors import GraphInterrupt
            if not isinstance(error, GraphInterrupt):
                self._record_failure(run, graph, error)
            self.lifecycle.raise_observed_fatal(run.owner, run.run_id)
            raise
        finally:
            _CURRENT_WORKFLOW_NODE.reset(token)

    def _record_failure(self, run, graph, error: BaseException) -> None:
        """Publish failure facts without replaying or undoing completed Actions."""
        if isinstance(graph, RunGraphBinding):
            try:
                failed = self.lifecycle.fail(run.owner, run.run_id)
                if failed is None:
                    return  # Never replace STOPPED, SUCCEEDED or prior FAILED.
                run = failed
            except Exception:
                error.add_note("RUN_FAILURE_STATE_SAVE_UNCONFIRMED")
        if isinstance(graph, RunGraphBinding) and graph.failure_observer is not None:
            try:
                graph.failure_observer(error)
            except Exception:
                error.add_note("NODE_FAILURE_OBSERVATION_UNCONFIRMED")
        try:
            self.lifecycle.publish_event(
                RUN_FAILED, run, payload={"reason": type(error).__name__})
        except Exception:
            error.add_note("RUN_FAILURE_EVENT_PUBLISH_UNCONFIRMED")

    def action(self, run, service, payload):
        """AF04 Action entry cannot silently select the legacy AF03 test path."""
        if service.lifecycle is not self.lifecycle:
            raise ActionRejected("CONTROLLED_ACTION_BINDING_REQUIRED")
        from .langgraph_adapter import LangGraphContinuation
        continuation = service.continuation
        if (not isinstance(continuation, LangGraphContinuation)
                or continuation.lifecycle is not self.lifecycle
                or not isinstance(continuation.graph, RunGraphBinding)
                or continuation.graph.lifecycle is not self.lifecycle):
            raise ActionRejected("CONTROLLED_CONTINUATION_BINDING_REQUIRED")
        from .models import ActionRequest
        if ActionRequest.from_mapping(payload).run_id != run.run_id:
            raise ActionRejected("RUN_BINDING_MISMATCH")
        try:
            self.lifecycle.assert_active(run.owner, run.run_id)
            return service.submit(payload, run.owner)
        except RunStoppedControl as signal:
            self.lifecycle.raise_observed_fatal(run.owner, run.run_id)
            saved = self.lifecycle.read(run.owner, run.run_id)
            if signal.run_id != run.run_id or saved.status != "STOPPED":
                raise
            return self.lifecycle.snapshot(run.owner, run.run_id)
