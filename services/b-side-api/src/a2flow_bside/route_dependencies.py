"""Typed callback contracts at the explicit HTTP composition boundary.

JSON objects remain open because remote asset/card schemas are extensible; the
service dependency itself is never an untyped container or global registry.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypedDict

JsonObject = dict[str, Any]


class MemoryEntryData(TypedDict):
    id: str
    text: str


class MemoryState(TypedDict):
    revision: int
    enabled: bool
    entries: list[MemoryEntryData]


class CardActionPayload(TypedDict):
    requestId: str
    actionName: str
    inputs: JsonObject


WorkflowCatalog = Callable[[int], list[JsonObject]]
MemoryView = Callable[[int], MemoryState]
MemoryReplace = Callable[[int, MemoryState], MemoryState]
ChatCards = Callable[[int, str], list[JsonObject]]
ChatAction = Callable[[int, str, str, CardActionPayload], JsonObject]
