"""Anthropic model adapter that keeps Runtime Tool schemas fail closed."""

from collections.abc import Sequence
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.runnables import Runnable


class StrictToolChatAnthropic(ChatAnthropic):
    """Force strict provider schemas when Deep Agents binds Runtime tools."""

    def bind_tools(
        self,
        tools: Sequence[Any],
        **kwargs: Any,
    ) -> Runnable:
        """Bind tools with closed input objects on the Anthropic wire."""

        kwargs["strict"] = True
        return super().bind_tools(tools, **kwargs)
