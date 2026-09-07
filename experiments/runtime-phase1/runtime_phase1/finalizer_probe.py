"""Fail-closed Finalizer admission for the engine-first probe."""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Annotated, Any
from typing_extensions import NotRequired

from langchain.agents.middleware import (
    AgentMiddleware,
    AgentState,
    ToolCallRequest,
)
from langchain.agents.middleware.types import PrivateStateAttr
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command


_RUNTIME_TOOL_EVIDENCE = "_runtime_tool_evidence"
RuntimeToolEvidence = tuple[str, str]


class FinalizerState(AgentState):
    """Agent state with Runtime-owned evidence hidden from input and output."""

    _runtime_tool_evidence: NotRequired[
        Annotated[list[RuntimeToolEvidence], PrivateStateAttr]
    ]


class FinalizationRejected(RuntimeError):
    """Raised when a model final response lacks required successful Tool facts."""


class RequiredToolFinalizerAdmission(AgentMiddleware):
    """Gate terminal responses on facts emitted by the actual Tool handler."""

    state_schema = FinalizerState

    def __init__(self, required_tool_names: Sequence[str]) -> None:
        names = tuple(required_tool_names)
        if not names or any(not isinstance(name, str) or not name for name in names):
            raise ValueError("Finalizer requires non-empty Tool names")
        if len(names) != len(set(names)):
            raise ValueError("Finalizer Tool names must be unique")
        self._required_tool_names = names

    def before_agent(
        self,
        state: Mapping[str, Any],
        runtime: object,
    ) -> dict[str, Any]:
        """Discard any caller-supplied or checkpoint-stale probe evidence."""

        del state, runtime
        return {_RUNTIME_TOOL_EVIDENCE: []}

    async def abefore_agent(
        self,
        state: Mapping[str, Any],
        runtime: object,
    ) -> dict[str, Any]:
        """Apply the same evidence reset for asynchronous execution."""

        return self.before_agent(state, runtime)

    @staticmethod
    def _record_tool_result(
        request: ToolCallRequest,
        result: ToolMessage | Command[Any],
    ) -> ToolMessage | Command[Any]:
        """Record only a successful message returned by the invoked handler."""

        if not isinstance(result, ToolMessage) or result.status == "error":
            return result
        call_id = request.tool_call.get("id")
        call_name = request.tool_call.get("name")
        if (
            not isinstance(call_id, str)
            or not isinstance(call_name, str)
            or result.tool_call_id != call_id
            or result.name != call_name
        ):
            return result
        evidence = list(request.state.get(_RUNTIME_TOOL_EVIDENCE, ()))
        evidence.append((call_id, call_name))
        return Command(
            update={
                "messages": [result],
                _RUNTIME_TOOL_EVIDENCE: evidence,
            }
        )

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        """Record provenance after the synchronous handler returns."""

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

        return self._record_tool_result(request, await handler(request))

    def _check_terminal_response(self, state: Mapping[str, Any]) -> None:
        """Reject terminal AI output without Runtime-owned Tool provenance."""

        messages = state.get("messages", ())
        if not messages:
            raise FinalizationRejected("Finalizer requires message state")
        last_message = messages[-1]
        if not isinstance(last_message, AIMessage) or last_message.tool_calls:
            return

        successful_tools = {
            tool_name
            for _, tool_name in state.get(_RUNTIME_TOOL_EVIDENCE, ())
        }
        missing = [
            name
            for name in self._required_tool_names
            if name not in successful_tools
        ]
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

        del runtime
        self._check_terminal_response(state)

    async def aafter_model(
        self,
        state: Mapping[str, Any],
        runtime: object,
    ) -> None:
        """Apply identical Finalizer admission to asynchronous execution."""

        del runtime
        self._check_terminal_response(state)
