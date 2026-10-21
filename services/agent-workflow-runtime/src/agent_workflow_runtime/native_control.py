"""Public synchronous SDK hooks. No scheduler, hidden retries or mutable SDK patch."""

from collections.abc import Callable
from dataclasses import dataclass
from contextvars import ContextVar
import logging

from langchain.agents.middleware import AgentMiddleware
from langchain_core.callbacks import BaseCallbackHandler

from .lifecycle import RunStoppedControl
from .models import ActionRejected
from .actions import ActionService
from skillweave_contracts import TrustedContext
from typing import Any
from .lifecycle import RunRecord
from .waiting_notifications import publish_waiting_snapshot

LOG = logging.getLogger(__name__)


# 可信节点上下文通过 ContextVar 传播到 SDK 回调，不从模型工具参数推导身份。
_CURRENT_WORKFLOW_NODE = ContextVar("a2flow_current_workflow_node", default=None)


def current_node_context(fallback):
    """Bound only by the trusted Runtime runner/node wrapper, never model args."""
    # 节点必须由受控入口显式绑定；缺失时拒绝，不能用备用对象静默代替。
    context = _CURRENT_WORKFLOW_NODE.get()
    if context is None:
        raise ActionRejected("TRUSTED_NODE_CONTEXT_REQUIRED")
    # 同时比对用户、环境和运行归属，防止并行节点串用其他运行的上下文。
    if (context.trusted_context != fallback.trusted_context
            or context.invocation_scope.kind != "WORKFLOW"
            or context.invocation_scope.run_id != fallback.invocation_scope.run_id):
        raise ActionRejected("RUN_NODE_BINDING_MISMATCH")
    return context


class RunModelCallbacks(BaseCallbackHandler):
    """Inherited by actual main AND summary model calls through RunnableConfig."""

    # 回调同步执行并传播错误，使停止门禁能阻断真实模型调用。
    run_inline = True
    raise_error = True

    def __init__(self, lifecycle, run):
        self.lifecycle, self.run = lifecycle, run

    def _start(self, run_id):
        try:
            # 每次主模型或摘要模型真正开始时都单独准入，覆盖 SDK 内部额外模型调用。
            context = current_node_context(self.run.context())
            self.lifecycle.admit(self.run.owner, self.run.run_id, context.invocation_scope.node_id,
                                 "MODEL", operation_id=str(run_id))
        # 记录非普通致命异常，避免 SDK 并发执行时被另一分支的停止信号掩盖。
        except BaseException as error:
            self.lifecycle.observe_fatal(self.run.owner, self.run.run_id, error)
            raise

    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
        self._start(run_id)

    def on_llm_start(self, serialized, prompts, *, run_id, **kwargs):
        self._start(run_id)

    # 先保存真实响应，再检查运行是否已停止；晚到结果不能被停止状态抹掉。
    def on_llm_end(self, response, *, run_id, **kwargs):
        self.lifecycle.finish(self.run.owner, self.run.run_id, str(run_id), response)
        self.lifecycle.assert_active(self.run.owner, self.run.run_id)

    # 错误回调仅补充未确认事实，已保存的最终响应不会被后来的错误覆盖。
    def on_llm_error(self, error, *, run_id, **kwargs):
        self.lifecycle.observe_fatal(self.run.owner, self.run.run_id, error)
        # Preserve an already saved response if the SDK emits an error because
        # our on_llm_end raised the stop signal after saving it.
        self.lifecycle.finish(self.run.owner, self.run.run_id, str(run_id),
                              {"errorType": type(error).__name__}, status="UNCONFIRMED")


class BoundNodeMiddleware(AgentMiddleware):
    """Bind callback-visible model/Tool work to one trusted compiled node."""

    def __init__(self, context):
        # 只有工作流节点可以启用此绑定，中间件不是通用用户身份入口。
        if context.invocation_scope.kind != "WORKFLOW":
            raise ValueError("WORKFLOW_BINDING_REQUIRED")
        self.context = context

    def _bind(self, request):
        # 先确认上层运行上下文可信，再把模型和工具调用收窄到当前编译节点。
        fallback = request.runtime.context
        current_node_context(fallback)
        if (fallback.trusted_context != self.context.trusted_context
                or fallback.invocation_scope.kind != "WORKFLOW"
                or fallback.invocation_scope.run_id
                != self.context.invocation_scope.run_id):
            raise ActionRejected("RUN_NODE_BINDING_MISMATCH")
        return _CURRENT_WORKFLOW_NODE.set(self.context)

    def _invoke(self, handler, request):
        # 绑定仅覆盖本次处理器调用；finally 恢复原值，避免线程复用造成身份泄漏。
        token = self._bind(request)
        try:
            return handler(request)
        finally:
            _CURRENT_WORKFLOW_NODE.reset(token)

    def wrap_model_call(self, request, handler):
        return self._invoke(handler, request)

    def wrap_tool_call(self, request, handler):
        return self._invoke(handler, request)

    # 异步模型处理也保持相同绑定作用域，取消或异常都必须恢复 ContextVar。
    async def awrap_model_call(self, request, handler):
        token = self._bind(request)
        try:
            return await handler(request)
        finally:
            _CURRENT_WORKFLOW_NODE.reset(token)

    # 异步工具调用与同步路径沿用同一可信节点身份。
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
        # 每个 SDK 推进边界都读取运行状态，停止后禁止新的模型或工具准入。
        scope = context.invocation_scope
        if scope.kind != "WORKFLOW":
            raise ActionRejected("WORKFLOW_BINDING_REQUIRED")
        self.lifecycle.assert_active(context.trusted_context, scope.run_id)

    def _node(self, fallback):
        # 未固定节点时读取当前受控绑定；固定节点时还需核对请求的运行归属。
        if self.node_context is None:
            return current_node_context(fallback)
        current_node_context(self.node_context)
        if (fallback.trusted_context != self.node_context.trusted_context
                or fallback.invocation_scope.run_id
                != self.node_context.invocation_scope.run_id):
            raise ActionRejected("RUN_NODE_BINDING_MISMATCH")
        return self.node_context

    # Agent 起止和模型前后均检查活动状态，覆盖等待期间发生的停止。
    def before_agent(self, state, runtime):
        self._check(runtime.context)

    def before_model(self, state, runtime):
        self._check(runtime.context)

    def after_model(self, state, runtime):
        self._check(runtime.context)

    def after_agent(self, state, runtime):
        self._check(runtime.context)

    # 处理器前后检查停止状态，真实模型开始准入另由回调覆盖。
    def wrap_model_call(self, request, handler):
        self._check(request.runtime.context)
        result = handler(request)
        self._check(request.runtime.context)
        return result

    def wrap_tool_call(self, request, handler):
        # 工具执行走生命周期账本，先准入、再调用、最后保存实际返回事实。
        context = self._node(request.runtime.context)
        return self.lifecycle.execute(context, "TOOL", lambda: handler(request))


# 每个业务节点单独获得准入，不能用一次 Skill 准入覆盖其后所有业务步骤。
def guarded_node(lifecycle, context, handler):
    """Wrap each owned business node, not an entire Skill as one reusable permit."""
    def invoke(state):
        token = _CURRENT_WORKFLOW_NODE.set(context)
        try:
            return lifecycle.execute(context, "NODE", lambda: handler(state))
        finally:
            _CURRENT_WORKFLOW_NODE.reset(token)
    return invoke


# 路由决定也经过停止门禁，避免停止后继续调度下游节点。
def guarded_router(lifecycle, context, route):
    def invoke(state):
        return lifecycle.execute(context, "ROUTER", lambda: route(state))
    return invoke


@dataclass(frozen=True)
# 显式绑定只表达装配责任；任意 Python 图不会因为包一层对象就自动变安全。
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

    def start(self, owner: TrustedContext, control_id: str, definition_key: str, inputs: dict[str, Any], entry_node_id: str, *, stopped_run_id: str | None = None) -> dict[str, Any]:
        # 先分配并保存运行及控制请求，同请求重复到达只返回已有运行。
        run, fresh = self.lifecycle.allocate(
            owner, control_id, definition_key, inputs, entry_node_id, self.resolve_versions,
            stopped_run_id=stopped_run_id,
        )
        # 控制请求去重不触发图工厂，避免刷新或网络重发重新启动同一运行。
        if not fresh:
            return self.lifecycle.snapshot(owner, run.run_id)
        # 区分图构建前失败与图执行内失败，确保各阶段都能关闭运行事实。
        invoked = False
        try:
            self.lifecycle.assert_active(owner, run.run_id)
            # 图工厂由可信后端提供，初始输入与生命周期绑定后再进入执行。
            graph, initial_state = self.graph_factory(run, self.lifecycle)
            invoked = True
            self.invoke(run, graph, initial_state)
        # 只有本运行已持久化 STOPPED 的私有信号可以解释为正常停止。
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
            # 尚未进入公共执行边界的构建错误，也要记录为真实运行失败。
            if not invoked:
                self._record_failure(run, None, error)
            try:
                # 启动回执不确定时保留 UNCONFIRMED，不能把异常当作未开始并重试。
                self.lifecycle.control_status(owner, control_id, "UNCONFIRMED")
            except Exception:
                error.add_note("RUN_CONTROL_RECEIPT_SAVE_UNCONFIRMED")
            raise
        self.lifecycle.control_status(owner, control_id, "RETURNED")
        return self.lifecycle.snapshot(owner, run.run_id)

    # 首次启动与交互恢复复用同一个受控调用边界，进度采集仅作观察。
    def invoke(self, run, graph, value):
        if isinstance(graph, RunGraphBinding) and graph.progress is not None:
            with graph.progress.capture(run.context()):
                return self._invoke_controlled(run, graph, value)
        return self._invoke_controlled(run, graph, value)

    def _invoke_controlled(self, run, graph, value):
        """Fresh state or an authorized native reference; STOPPED always rejects."""
        # 运行入口建立可信上下文，下层节点可在同运行内进一步绑定具体 node_id。
        token = _CURRENT_WORKFLOW_NODE.set(run.context())
        try:
            self.lifecycle.assert_active(run.owner, run.run_id)
            # 执行前验证图和生命周期来自同一装配，拒绝未经门禁的裸图。
            if not isinstance(graph, RunGraphBinding) or graph.lifecycle is not self.lifecycle:
                raise ActionRejected("CONTROLLED_GRAPH_BINDING_REQUIRED")
            # 回调通过 SDK 配置继承到主模型及内部摘要模型，不另建调度层。
            callbacks = [RunModelCallbacks(self.lifecycle, run)]
            if graph.progress is not None:
                from .progress_observer import ProgressCallbacks
                callbacks.append(ProgressCallbacks())
            # 线程 ID 来自保存的运行记录，不能由恢复请求指定任意检查点。
            result = graph.invoke(
                value, {"configurable": {"thread_id": run.thread_id},
                        "callbacks": callbacks},
                context=run.context(),
            )
            # interrupt means waiting, not a successful completed run.
            self.lifecycle.raise_observed_fatal(run.owner, run.run_id)
            self.lifecycle.assert_active(run.owner, run.run_id)
            # 读取原生图是否仍有待执行节点；invoke 返回本身不表示整个流程已完成。
            snapshot = graph.get_state(
                {"configurable": {"thread_id": run.thread_id}}, subgraphs=True,
            )
            pending = tuple(snapshot.next or ())
            # 没有中断且没有待执行节点才落成功；原生等待应发布等待快照。
            if not result.get("__interrupt__") and not pending:
                self.lifecycle.succeed(run.owner, run.run_id)
            else:
                try:
                    # 等待通知失败只记录通知问题，不能把已保存的检查点等待改写成图失败。
                    publish_waiting_snapshot(self.lifecycle, run, snapshot)
                except Exception as error:
                    # Checkpoint is already waiting. Recovery can restore its notice;
                    # notification failure must not fabricate a graph failure.
                    LOG.warning("Waiting notification enqueue failed run_id=%s error_type=%s",
                                run.run_id, type(error).__name__)
            return result
        except RunStoppedControl as signal:
            self.lifecycle.raise_observed_fatal(run.owner, run.run_id)
            saved = self.lifecycle.read(run.owner, run.run_id)
            if signal.run_id != run.run_id or saved.status != "STOPPED":
                raise
            return self.lifecycle.snapshot(run.owner, run.run_id)
        # GraphInterrupt 属于原生等待控制流，其余真实异常才记录失败。
        except BaseException as error:
            from langgraph.errors import GraphInterrupt
            # 先保存失败事实，再重新抛出观察到的致命异常，避免被普通错误替代。
            if not isinstance(error, GraphInterrupt):
                self._record_failure(run, graph, error)
            self.lifecycle.raise_observed_fatal(run.owner, run.run_id)
            raise
        finally:
            _CURRENT_WORKFLOW_NODE.reset(token)

    def _record_failure(self, run, graph, error: BaseException) -> None:
        """Publish failure facts without replaying or undoing completed Actions."""
        # Allocation precedes graph construction. Setup failures must also
        # terminate the run, even when no graph binding exists yet.
        try:
            # 失败仅能关闭仍在运行的记录，不覆盖 STOPPED、SUCCEEDED 或已有 FAILED。
            failed = self.lifecycle.fail(run.owner, run.run_id, reason=type(error).__name__)
            if failed is None:
                return  # Never replace STOPPED, SUCCEEDED or prior FAILED.
            run = failed
        except Exception:
            error.add_note("RUN_FAILURE_STATE_SAVE_UNCONFIRMED")
            return  # No independently committed notification may contradict run state.
        # 运行失败落库后才通知节点观察器，避免节点展示与运行事实矛盾。
        if isinstance(graph, RunGraphBinding) and graph.failure_observer is not None:
            try:
                graph.failure_observer(error)
            except Exception:
                error.add_note("NODE_FAILURE_OBSERVATION_UNCONFIRMED")

    def action(self, run: RunRecord, service: ActionService, payload: dict[str, Any]) -> object:
        """AF04 Action entry cannot silently select the legacy AF03 test path."""
        # 动作服务、恢复适配器和图必须共享同一生命周期，禁止绕过受控执行入口。
        if service.lifecycle is not self.lifecycle:
            raise ActionRejected("CONTROLLED_ACTION_BINDING_REQUIRED")
        from .langgraph_adapter import LangGraphContinuation
        continuation = service.continuation
        # 恢复链条逐层核对绑定，不只验证外层 ActionService 对象。
        if (not isinstance(continuation, LangGraphContinuation)
                or continuation.lifecycle is not self.lifecycle
                or not isinstance(continuation.graph, RunGraphBinding)
                or continuation.graph.lifecycle is not self.lifecycle):
            raise ActionRejected("CONTROLLED_CONTINUATION_BINDING_REQUIRED")
        from .models import ActionRequest
        # 请求中的运行身份也必须匹配当前运行，随后才允许提交真实动作。
        if ActionRequest.from_mapping(payload).run_id != run.run_id:
            raise ActionRejected("RUN_BINDING_MISMATCH")
        try:
            self.lifecycle.assert_active(run.owner, run.run_id)
            # 动作服务独立负责业务事实与恢复回执；此处不重写其幂等规则。
            return service.submit(payload, run.owner)
        except RunStoppedControl as signal:
            self.lifecycle.raise_observed_fatal(run.owner, run.run_id)
            saved = self.lifecycle.read(run.owner, run.run_id)
            if signal.run_id != run.run_id or saved.status != "STOPPED":
                raise
            return self.lifecycle.snapshot(run.owner, run.run_id)
