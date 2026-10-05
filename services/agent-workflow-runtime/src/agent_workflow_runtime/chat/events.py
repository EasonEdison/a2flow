"""Typed, transport-free events emitted by the native Chat loop."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from typing import Literal, Protocol, TypeAlias, TypedDict, cast

TEXT_DELTA = "text_delta"
TOOL_CALL = "tool_call"
TOOL_CALL_STARTED = "tool_call_started"
TOOL_CALL_FINISHED = "tool_call_finished"
WORKFLOW_CONFIRM = "workflow_confirm"
DONE = "done"
ERROR = "error"

JsonValue: TypeAlias = (
    bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"] | None
)
JsonObject: TypeAlias = dict[str, JsonValue]

_MAX_DEPTH = 4
_MAX_ITEMS = 20
_MAX_STRING = 512
_MAX_EVENT_BYTES = 4096
_PRIVATE_KEY_PARTS = (
    "authorization", "cookie", "credential", "password", "passwd",
    "secret", "token", "api_key", "apikey",
)


class ModelDeltaPayload(TypedDict):
    text: str
    modelMessageId: str | None


class ToolCallStartedPayload(TypedDict):
    toolCallId: str
    name: str
    arguments: JsonObject
    startedAt: str


class ToolCallFinishedPayload(TypedDict, total=False):
    toolCallId: str
    name: str
    lifecycleStatus: Literal["returned", "raised"]
    toolMessageStatus: Literal["success", "error"] | None
    startedAt: str
    finishedAt: str
    durationMs: int
    result: JsonValue
    businessSuccess: bool | None
    errorCode: str


class DonePayload(TypedDict):
    content: str
    finalModelMessageId: str | None


def _private_key(key: str) -> bool:
    normalized = key.casefold().replace("-", "_")
    return any(part in normalized for part in _PRIVATE_KEY_PARTS)


def _bounded_value(value: object, *, depth: int) -> JsonValue:
    if value is None or type(value) in {bool, int}:
        return cast(bool | int | None, value)
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        return {"type": "nonFiniteNumber"}
    if isinstance(value, str):
        return value if len(value) <= _MAX_STRING else value[:_MAX_STRING] + "…"
    if depth >= _MAX_DEPTH:
        return {"truncated": True}
    if isinstance(value, Mapping):
        result: JsonObject = {}
        for index, (raw_key, item) in enumerate(value.items()):
            if index >= _MAX_ITEMS:
                result["truncated"] = True
                break
            key = str(raw_key)
            result[key] = (
                "[REDACTED]" if _private_key(key)
                else _bounded_value(item, depth=depth + 1)
            )
        return result
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        items = [
            _bounded_value(item, depth=depth + 1)
            for item in value[:_MAX_ITEMS]
        ]
        if len(value) > _MAX_ITEMS:
            items.append({"truncated": True})
        return items
    return {"type": type(value).__name__}


def public_event_value(value: object) -> JsonValue:
    """Return a small JSON value without credentials or arbitrary repr text."""

    bounded = _bounded_value(value, depth=0)
    encoded = json.dumps(
        bounded, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if len(encoded) <= _MAX_EVENT_BYTES:
        return bounded
    if isinstance(bounded, dict):
        keys = [cast(JsonValue, key) for key in list(bounded)[:_MAX_ITEMS]]
        return {"keys": keys, "truncated": True}
    return {"truncated": True}


def public_result_summary(value: object) -> JsonValue:
    """Describe a tool result without copying its resource or UI payload."""

    bounded = public_event_value(value)
    if isinstance(bounded, dict):
        scalar_values: JsonObject = {}
        for key, item in bounded.items():
            if item is None or type(item) in {bool, int, float}:
                scalar_values[key] = cast(bool | int | float | None, item)
            elif isinstance(item, str) and len(item) <= 128:
                scalar_values[key] = item
        keys = [cast(JsonValue, key) for key in list(bounded)[:_MAX_ITEMS]]
        result: JsonObject = {"keys": keys}
        if scalar_values:
            result["values"] = scalar_values
        return result
    if isinstance(bounded, list):
        return {"type": "array", "count": len(bounded)}
    if isinstance(bounded, str):
        return {"type": "text", "length": len(bounded)}
    return bounded


class ChatEmitter(Protocol):
    def emit(self, kind: str, payload: dict[str, object]) -> None: ...


class ListEmitter:
    """In-memory emitter for tests and non-streaming callers."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def emit(self, kind: str, payload: dict[str, object]) -> None:
        self.events.append((kind, payload))
