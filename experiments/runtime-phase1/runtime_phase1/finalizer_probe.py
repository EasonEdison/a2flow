"""Fail-closed Finalizer admission for the engine-first probe."""

from collections.abc import Mapping, Sequence
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


class FinalizationRejected(RuntimeError):
    """Raised when a model final response lacks required successful Tool facts."""


class RequiredToolFinalizerAdmission(AgentMiddleware):
    """Gate terminal model responses on successful Runtime-owned Tool evidence."""

    def __init__(self, required_tool_names: Sequence[str]) -> None:
        names = tuple(required_tool_names)
        if not names or any(not isinstance(name, str) or not name for name in names):
            raise ValueError("Finalizer requires non-empty Tool names")
        if len(names) != len(set(names)):
            raise ValueError("Finalizer Tool names must be unique")
        self._required_tool_names = names

    def _check_terminal_response(self, state: Mapping[str, Any]) -> None:
        """Reject only a terminal AI response with missing successful Tool facts."""

        messages = state.get("messages", ())
        if not messages:
            raise FinalizationRejected("Finalizer requires message state")
        last_message = messages[-1]
        if not isinstance(last_message, AIMessage) or last_message.tool_calls:
            return

        turn_start = next(
            (
                index
                for index in range(len(messages) - 1, -1, -1)
                if isinstance(messages[index], HumanMessage)
            ),
            None,
        )
        if turn_start is None:
            raise FinalizationRejected("Finalizer requires a current user boundary")

        authorized_calls: dict[str, str] = {}
        successful_tools: set[str] = set()
        for message in messages[turn_start + 1:]:
            if isinstance(message, AIMessage):
                authorized_calls.update(
                    {
                        call["id"]: call["name"]
                        for call in message.tool_calls
                    }
                )
            elif isinstance(message, ToolMessage):
                expected_name = authorized_calls.pop(message.tool_call_id, None)
                if expected_name == message.name and message.status != "error":
                    successful_tools.add(expected_name)
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
