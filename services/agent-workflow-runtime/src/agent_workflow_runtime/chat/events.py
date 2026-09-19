"""Chat-loop event kinds and the emitter protocol (transport-free)."""

from __future__ import annotations

from typing import Protocol

TEXT_DELTA = "text_delta"
TOOL_CALL = "tool_call"
WORKFLOW_CONFIRM = "workflow_confirm"
DONE = "done"
ERROR = "error"


class ChatEmitter(Protocol):
    def emit(self, kind: str, payload: dict) -> None: ...


class ListEmitter:
    """In-memory emitter for tests and non-streaming callers."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def emit(self, kind: str, payload: dict) -> None:
        self.events.append((kind, payload))
