"""Typed, transport-free events emitted by the native Chat loop."""

from __future__ import annotations

import json
import math
import re
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
_TOOL_PRIVATE_KEYS = frozenset({
    "api_key", "apikey", "authorization", "client_secret", "cookie",
    "credential", "credentials", "id_token", "password", "passwd",
    "proxy_authorization", "refresh_token", "secret", "set_cookie",
    "access_token", "token",
})
_PRIVATE_KEY_SUFFIXES = (
    "_api_key", "_authorization", "_cookie", "_credential", "_password",
    "_secret", "_token",
)
_PRIVATE_HEADER = re.compile(
    r"(?im)^(\s*(?:authorization|proxy-authorization|cookie|set-cookie)"
    r"\s*:\s*)[^\r\n]*"
)
_PRIVATE_ASSIGNMENT = re.compile(
    r"(?i)(?P<prefix>(?:\"|')?(?:password|passwd|secret|token|"
    r"client[_-]?secret|access[_-]?token|refresh[_-]?token|id[_-]?token|"
    r"api[_-]?key|credential)(?:\"|')?\s*[:=]\s*)"
    r"(?:\"[^\"]*\"|'[^']*'|[^&,\s;}\]\r\n]+)"
)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_JWT = re.compile(
    r"\beyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"
)
_API_TOKEN = re.compile(r"\b(?:sk|rk|pk)-[A-Za-z0-9_-]{16,}\b")


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


def _tool_private_key(key: str) -> bool:
    snake_key = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", key)
    normalized = re.sub(
        r"[^a-z0-9]+", "_", snake_key.casefold(),
    ).strip("_")
    return normalized in _TOOL_PRIVATE_KEYS or normalized.endswith(
        _PRIVATE_KEY_SUFFIXES
    )


def _redact_text(value: str) -> str:
    value = _PRIVATE_HEADER.sub(r"\1[REDACTED]", value)
    value = _PRIVATE_ASSIGNMENT.sub(r"\g<prefix>[REDACTED]", value)
    value = _BEARER.sub("Bearer [REDACTED]", value)
    value = _JWT.sub("[REDACTED_JWT]", value)
    return _API_TOKEN.sub("[REDACTED_TOKEN]", value)


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


def public_tool_result(
    value: object,
    *,
    _stack: set[int] | None = None,
) -> JsonValue:
    """Preserve one ToolMessage result, redacting only credential material."""

    if value is None or type(value) in {bool, int}:
        return cast(bool | int | None, value)
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        return {"type": "nonFiniteNumber"}
    if isinstance(value, str):
        return _redact_text(value)
    stack = set() if _stack is None else _stack
    if isinstance(value, Mapping):
        identity = id(value)
        if identity in stack:
            return {"type": "recursiveReference"}
        stack.add(identity)
        try:
            result: JsonObject = {}
            for raw_key, item in value.items():
                key = str(raw_key)
                result[key] = (
                    "[REDACTED]" if _tool_private_key(key)
                    else public_tool_result(item, _stack=stack)
                )
            return result
        finally:
            stack.remove(identity)
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        identity = id(value)
        if identity in stack:
            return {"type": "recursiveReference"}
        stack.add(identity)
        try:
            return [public_tool_result(item, _stack=stack) for item in value]
        finally:
            stack.remove(identity)
    return {"type": type(value).__name__}


class ChatEmitter(Protocol):
    def emit(self, kind: str, payload: dict[str, object]) -> None: ...


class ListEmitter:
    """In-memory emitter for tests and non-streaming callers."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def emit(self, kind: str, payload: dict[str, object]) -> None:
        self.events.append((kind, payload))
