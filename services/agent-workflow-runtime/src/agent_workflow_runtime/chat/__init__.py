"""Conversation chat execution engine: model loop, chat tools, chat events.

The engine never starts a workflow run by itself: running a workflow always
requires an explicit user confirmation after the workflow_confirm event.
"""

from .events import (
    ChatEmitter,
    DONE,
    ERROR,
    ListEmitter,
    TEXT_DELTA,
    TOOL_CALL,
    WORKFLOW_CONFIRM,
)
from .loop import ChatLoop, ChatLoopError
from .tools import build_chat_tools

__all__ = [
    "ChatEmitter",
    "ChatLoop",
    "ChatLoopError",
    "DONE",
    "ERROR",
    "ListEmitter",
    "TEXT_DELTA",
    "TOOL_CALL",
    "WORKFLOW_CONFIRM",
    "build_chat_tools",
]
