"""Deterministic chat model used only by the Runtime feasibility probe."""

from typing import Any, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field


class ScriptedToolModel(BaseChatModel):
    """Replay complete AI messages while recording the real agent input."""

    responses: list[AIMessage]
    observedMessages: list[list[BaseMessage]] = Field(default_factory=list)
    boundTools: list[Any] = Field(default_factory=list)
    responseIndex: int = 0

    @property
    def _llm_type(self) -> str:
        return "skillweave-scripted-tool-model"

    def bind_tools(
        self,
        tools: Sequence[Any],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> BaseChatModel:
        """Record the actual tool objects that Deep Agents binds."""

        del tool_choice, kwargs
        self.boundTools = list(tools)
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Return the next scripted response and preserve input messages."""

        del stop, run_manager, kwargs
        self.observedMessages.append(list(messages))
        response = self.responses[self.responseIndex]
        self.responseIndex += 1
        return ChatResult(generations=[ChatGeneration(message=response)])
