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
        self._validators = dict(validators)

    def _validate_or_reject(
        self,
        request: ToolCallRequest,
    ) -> ToolMessage | None:
        """Return a generic rejection when original model args are not closed."""

        validator = self._validators.get(request.tool_call["name"])
        try:
            if validator is None:
                raise ValueError("Tool has no model-argument validator")
            validator(request.tool_call["args"])
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
        return await handler(request)


def build_closed_tool_node(
    tools: Sequence[BaseTool],
    validators: Mapping[str, ModelArgsValidator],
) -> ToolNode:
    """Build a ToolNode that admits original args before injected-field stripping."""

    admission = ClosedModelArgsAdmission(validators)
    return ToolNode(tools, wrap_tool_call=admission.wrap_tool_call)
