"""Concrete Chat dependencies constructed together during application startup."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .chat_runner import ChatRunner
from .chat_wake import ChatWake
from .durable_chat import DurableChat
from .route_dependencies import ChatAction, ChatCards


@dataclass(frozen=True)
class ChatRuntime:
    """Fixed composition result, not a mutable service registry or executor."""

    durable_chat: DurableChat
    runner: ChatRunner
    cards: ChatCards | None = None
    action: ChatAction | None = None


ChatRuntimeFactory = Callable[[ChatWake], ChatRuntime]
