"""Pre-injection admission for closed model-visible Tool arguments."""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ToolCallRequest
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool
from langgraph.prebuilt import ToolNode
from langgraph.types import Command


ModelArgsValidator = Callable[[object], object]
ToolCallHandler = Callable[[ToolCallRequest], ToolMessage | Command[Any]]
AsyncToolCallHandler = Callable[
    [ToolCallRequest], Awaitable[ToolMessage | Command[Any]]
]
REJECTION_MESSAGE = "Tool arguments do not match the closed model contract"


class ClosedModelArgsAdmission(AgentMiddleware):
    """Validate original model args before ToolRuntime injection can strip keys."""

    def __init__(self, validators: Mapping[str, ModelArgsValidator]) -> None:
        # 复制宿主配置的工具参数验证器，执行时不依赖模型自行声明合同。
        self._validators = dict(validators)

    def _validate_or_reject(
        self,
        request: ToolCallRequest,
    ) -> ToolMessage | None:
        """Return a generic rejection when original model args are not closed."""

        # 在 SDK 注入或剔除隐藏字段之前校验原始参数，禁止越权字段被悄悄忽略。
        validator = self._validators.get(request.tool_call["name"])
        try:
            # 未声明验证器的工具直接拒绝，不能把未知工具视为无需校验。
            if validator is None:
                raise ValueError("Tool has no model-argument validator")
            validator(request.tool_call["args"])
        # 验证失败仅返回固定工具错误，不把包含输入内容的详细异常发给模型。
        except ValueError:
            return ToolMessage(
                content=REJECTION_MESSAGE,
                name=request.tool_call["name"],
                tool_call_id=request.tool_call["id"],
                status="error",
            )
        return None

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: ToolCallHandler,
    ) -> ToolMessage | Command[Any]:
        """Reject undeclared original fields without exposing validation details."""

        # 同步路径先校验再调用处理器，拒绝时不会执行业务副作用。
        rejection = self._validate_or_reject(request)
        if rejection is not None:
            return rejection
        return handler(request)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: AsyncToolCallHandler,
    ) -> ToolMessage | Command[Any]:
        """Apply identical closed-argument admission to async execution."""

        rejection = self._validate_or_reject(request)
        if rejection is not None:
            return rejection
        # 异步路径同样在验证通过后才调用真实处理器。
        return await handler(request)


def build_closed_tool_node(
    tools: Sequence[BaseTool],
    validators: Mapping[str, ModelArgsValidator],
) -> ToolNode:
    """Build a ToolNode that admits original args before injected-field stripping."""

    # 独立 ToolNode 也复用同一准入中间件，避免出现另一套参数安全规则。
    admission = ClosedModelArgsAdmission(validators)
    return ToolNode(tools, wrap_tool_call=admission.wrap_tool_call)
