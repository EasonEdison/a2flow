"""Fail-closed Finalizer admission for the Runtime-owned engine."""

import secrets
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Annotated, Any
from typing_extensions import NotRequired, TypedDict

from langchain.agents.middleware import (
    AgentMiddleware,
    AgentState,
    ToolCallRequest,
)
from langchain.agents.middleware.types import PrivateStateAttr
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command


# 工具成功证据由 Runtime 私有状态保存，不能仅凭模型历史里出现同名工具就算完成。
_RUNTIME_TOOL_EVIDENCE = "_runtime_tool_evidence"
RuntimeToolEvidence = tuple[str, str]


class RuntimeToolEvidenceState(TypedDict):
    """Private provenance collected for one Runtime-owned invocation."""

    invocation_id: str
    facts: list[RuntimeToolEvidence]


def _merge_runtime_tool_evidence(
    current: RuntimeToolEvidenceState | None,
    update: RuntimeToolEvidenceState,
) -> RuntimeToolEvidenceState:
    """Replace stale invocations and merge concurrent facts within one step."""

    # 新调用身份替换旧证据；同一次调用的并行工具结果由 reducer 合并。
    if (
        not isinstance(current, Mapping)
        or current.get("invocation_id") != update["invocation_id"]
    ):
        return {
            "invocation_id": update["invocation_id"],
            "facts": list(update["facts"]),
        }
    # 保留同调用的全部实际证据，不因并行状态更新丢掉其他工具结果。
    return {
        "invocation_id": current["invocation_id"],
        "facts": [*current["facts"], *update["facts"]],
    }


# 私有字段不进入模型输入和图公开输出，但可随原生检查点保存。
class FinalizerState(AgentState):
    """Agent state with Runtime-owned evidence hidden from input and output."""

    _runtime_tool_evidence: NotRequired[
        Annotated[
            RuntimeToolEvidenceState,
            PrivateStateAttr,
            _merge_runtime_tool_evidence,
        ]
    ]


class FinalizationRejected(RuntimeError):
    """Raised when a model final response lacks required successful Tool facts."""


class RequiredToolFinalizerAdmission(AgentMiddleware):
    """Gate terminal responses on facts emitted by the actual Tool handler."""

    state_schema = FinalizerState

    def __init__(
        self, required_tool_names: Sequence[str],
        terminal_guard: Callable[[Any], None] | None = None, *, lifecycle=None,
        node_context=None,
        tool_alternatives: Mapping[str, Sequence[str]] | None = None,
        allow_empty: bool = False,
    ) -> None:
        # 必需工具配置必须明确且不重复；只有显式纯文本场景允许空集合。
        names = tuple(required_tool_names)
        if (not names and not allow_empty) or any(not isinstance(name, str) or not name for name in names):
            raise ValueError("Finalizer requires non-empty Tool names")
        if len(names) != len(set(names)):
            raise ValueError("Finalizer Tool names must be unique")
        # 结束门禁与工具成功证据分别保存，前者还可检查必需交互是否已完成。
        self._required_tool_names = names
        self._terminal_guard = terminal_guard
        self._lifecycle = lifecycle
        self._node_context = node_context
        # 替代工具由可信配置声明，不能因工具名称相似就自动互相替代。
        self._tool_alternatives = {
            name: frozenset(alternatives)
            for name, alternatives in (tool_alternatives or {}).items()
        }

    def _context(self, fallback):
        # 固定节点存在时核对运行归属，防止最终检查借用其他节点身份。
        if self._node_context is None:
            return fallback
        if (fallback.trusted_context != self._node_context.trusted_context
                or fallback.invocation_scope.kind != "WORKFLOW"
                or fallback.invocation_scope.run_id
                != self._node_context.invocation_scope.run_id):
            from .models import ActionRejected
            raise ActionRejected("RUN_NODE_BINDING_MISMATCH")
        return self._node_context

    def before_agent(
        self,
        state: Mapping[str, Any],
        runtime: object,
    ) -> dict[str, Any]:
        """Start a Runtime-owned evidence scope for this invocation."""

        # 每次 Agent 调用建立新证据域，旧一轮的成功工具不能自动满足当前任务。
        del state
        if self._lifecycle is not None:
            ctx = self._context(runtime.context)
            self._lifecycle.assert_active(ctx.trusted_context, ctx.invocation_scope.run_id)
        # 随机调用 ID 隔离新旧证据；同一调用内的状态恢复仍保留该域。
        return {
            _RUNTIME_TOOL_EVIDENCE: {
                "invocation_id": secrets.token_hex(16),
                "facts": [],
            }
        }

    async def abefore_agent(
        self,
        state: Mapping[str, Any],
        runtime: object,
    ) -> dict[str, Any]:
        """Apply the same evidence reset for asynchronous execution."""

        # 异步调用复用同样的证据初始化规则，避免同步与异步语义分叉。
        return self.before_agent(state, runtime)

    @staticmethod
    def _record_tool_result(
        request: ToolCallRequest,
        result: ToolMessage | Command[Any],
    ) -> ToolMessage | Command[Any]:
        """Record only a successful message returned by the invoked handler."""

        # 从真实调用请求获取 ID 与名称，随后只接纳处理器实际返回的匹配消息。
        call_id = request.tool_call.get("id")
        call_name = request.tool_call.get("name")
        update = {}
        original = result
        # Command 可携带状态更新，先复制更新再定位唯一对应工具回执。
        if isinstance(result, Command):
            if not isinstance(result.update, dict):
                return original
            update = dict(result.update)
            # 多条消息必须按调用 ID 和工具名同时匹配，不接受其他并行调用的成功。
            candidates = [message for message in update.get("messages", ())
                          if isinstance(message, ToolMessage)
                          and message.tool_call_id == call_id and message.name == call_name]
            if len(candidates) != 1:
                return original
            result = candidates[0]
        # 错误消息和身份不符的消息都不写成功证据，保留原返回值给 SDK。
        if not isinstance(result, ToolMessage) or result.status == "error":
            return original
        if (
            not isinstance(call_id, str)
            or not isinstance(call_name, str)
            or result.tool_call_id != call_id
            or result.name != call_name
        ):
            return original
        # 调用必须已有 Runtime 创建的证据域，不能由工具结果随意伪造作用范围。
        evidence_state = request.state.get(_RUNTIME_TOOL_EVIDENCE)
        if not isinstance(evidence_state, Mapping):
            return original
        # 验证调用域完整后，返回带私有证据更新的原生 Command。
        invocation_id = evidence_state.get("invocation_id")
        if not isinstance(invocation_id, str) or not invocation_id:
            return original
        # 保留原业务状态更新与消息，仅追加本次实际工具成功事实。
        return Command(
            update={
                **update,
                "messages": update.get("messages", [result]),
                _RUNTIME_TOOL_EVIDENCE: {
                    "invocation_id": invocation_id,
                    "facts": [(call_id, call_name)],
                },
            }
        )

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        """Record provenance after the synchronous handler returns."""

        # 先真实执行同步工具，再记录成功来源，不根据模型调用意图提前判定完成。
        return self._record_tool_result(request, handler(request))

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[
            [ToolCallRequest],
            Awaitable[ToolMessage | Command[Any]],
        ],
    ) -> ToolMessage | Command[Any]:
        """Record provenance after the asynchronous handler returns."""

        # 异步工具也必须等处理器返回才记录证据，取消不会凭空产生成功事实。
        return self._record_tool_result(request, await handler(request))

    def _check_terminal_response(self, state: Mapping[str, Any]) -> None:
        """Reject terminal AI output without Runtime-owned Tool provenance."""

        # 仅对最终 AI 文本启用工具证据检查，中间工具调用继续交给 SDK 推进。
        messages = state.get("messages", ())
        if not messages:
            raise FinalizationRejected("Finalizer requires message state")
        last_message = messages[-1]
        if not isinstance(last_message, AIMessage) or last_message.tool_calls:
            return

        # 读取 Runtime 私有证据，而不是扫描可被模型或历史伪造的工具描述。
        evidence_state = state.get(_RUNTIME_TOOL_EVIDENCE)
        facts = (
            evidence_state.get("facts", ())
            if isinstance(evidence_state, Mapping)
            else ()
        )
        # 从有效证据结构提取真正成功的工具名，用于后续必需项检查。
        successful_tools = {
            fact[1]
            for fact in facts
            if isinstance(fact, (list, tuple))
            and len(fact) == 2
            and isinstance(fact[1], str)
        }
        # 必需工具可由配置中的合法替代项满足；没有实际成功记录则阻止结束。
        missing = [
            name
            for name in self._required_tool_names
            if name not in successful_tools
            and not self._tool_alternatives.get(name, frozenset()).intersection(successful_tools)
        ]
        # 缺少证据直接拒绝最终回复，不通过补一段模型文本伪装业务完成。
        if missing:
            raise FinalizationRejected(
                "Finalizer rejected missing successful Tool evidence: "
                + ",".join(missing)
            )

    def after_model(
        self,
        state: Mapping[str, Any],
        runtime: object,
    ) -> None:
        """Apply Finalizer admission to synchronous model execution."""

        messages = state.get("messages", ())
        # 模型不再调用工具才是候选最终回复，此时仍需检查交互和生命周期门禁。
        terminal = messages and isinstance(messages[-1], AIMessage) and not messages[-1].tool_calls

        context = self._context(runtime.context)

        # 先检查必需卡片完成情况，再核对工具事实，二者同时通过才允许结束。
        def check():
            if terminal and self._terminal_guard is not None:
                self._terminal_guard(context)
            self._check_terminal_response(state)

        # 工作流最终检查也单独准入，停止后不能因模型已返回而继续宣告成功。
        if terminal and self._lifecycle is not None:
            self._lifecycle.execute(context, "FINALIZER", check)
        else:
            check()

    async def aafter_model(
        self,
        state: Mapping[str, Any],
        runtime: object,
    ) -> None:
        """Apply identical Finalizer admission to asynchronous execution."""

        # 异步模型返回沿用相同结束检查，保持证据与停止规则一致。
        self.after_model(state, runtime)
