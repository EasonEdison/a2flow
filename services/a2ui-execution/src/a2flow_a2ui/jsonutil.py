"""Closed JSON pointer, JSON Schema and JSON safety helpers."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass

from a2flow_capability.models import JsonObject, JsonValue
from jsonschema import Draft7Validator
from jsonschema.exceptions import SchemaError

from .models import A2uiError

MAX_POINTER = 1024
MAX_DEPTH = 64


@dataclass(frozen=True, slots=True)
class Lookup:
    found: bool
    value: JsonValue = None


def clone(value: JsonValue) -> JsonValue:
    return copy.deepcopy(value)


def json_bytes(value: JsonValue) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def tokens(pointer: str, *, allow_root: bool = True) -> tuple[str, ...]:
    if type(pointer) is not str or len(pointer) > MAX_POINTER:
        raise A2uiError("JSON_POINTER_INVALID")
    if pointer in {"", "/"}:
        if allow_root:
            return ()
        raise A2uiError("JSON_POINTER_INVALID")
    if not pointer.startswith("/"):
        raise A2uiError("JSON_POINTER_INVALID")
    raw = pointer[1:].split("/")
    if not raw or len(raw) > MAX_DEPTH:
        raise A2uiError("JSON_POINTER_INVALID")
    decoded: list[str] = []
    for token in raw:
        index = 0
        value = ""
        while index < len(token):
            if token[index] != "~":
                value += token[index]
                index += 1
                continue
            if index + 1 >= len(token) or token[index + 1] not in {"0", "1"}:
                raise A2uiError("JSON_POINTER_INVALID")
            value += "~" if token[index + 1] == "0" else "/"
            index += 2
        decoded.append(value)
    return tuple(decoded)


def _index(token: str, length: int, *, append: bool) -> int:
    if not token.isdigit() or (len(token) > 1 and token.startswith("0")):
        raise A2uiError("JSON_POINTER_INVALID")
    value = int(token)
    if value > length or (value == length and not append):
        raise A2uiError("JSON_POINTER_INVALID")
    return value


def read(root: JsonValue, pointer: str) -> Lookup:
    path = tokens(pointer)
    if not path:
        return Lookup(True, clone(root))
    current: JsonValue = root
    for token in path:
        if isinstance(current, dict):
            if token not in current:
                return Lookup(False)
            current = current[token]
        elif isinstance(current, list):
            try:
                index = _index(token, len(current), append=False)
            except A2uiError:
                return Lookup(False)
            current = current[index]
        else:
            return Lookup(False)
    return Lookup(True, clone(current))


def write(root: JsonValue, pointer: str, value: JsonValue) -> JsonValue:
    path = tokens(pointer)
    if not path:
        return clone(value)
    result = clone(root)
    if not isinstance(result, (dict, list)):
        raise A2uiError("JSON_POINTER_INVALID")
    current: JsonValue = result
    for offset, token in enumerate(path[:-1]):
        next_token = path[offset + 1]
        if isinstance(current, dict):
            if token not in current:
                current[token] = [] if next_token.isdigit() else {}
            child = current[token]
        elif isinstance(current, list):
            index = _index(token, len(current), append=True)
            if index == len(current):
                current.append([] if next_token.isdigit() else {})
            child = current[index]
        else:
            raise A2uiError("JSON_POINTER_INVALID")
        if not isinstance(child, (dict, list)):
            raise A2uiError("JSON_POINTER_CONFLICT")
        current = child
    final = path[-1]
    if isinstance(current, dict):
        current[final] = clone(value)
    elif isinstance(current, list):
        index = _index(final, len(current), append=True)
        if index == len(current):
            current.append(clone(value))
        else:
            current[index] = clone(value)
    else:
        raise A2uiError("JSON_POINTER_INVALID")
    return result


def validate_schema(schema: JsonObject, value: JsonValue, code: str) -> None:
    try:
        validator = Draft7Validator(schema)
        validator.check_schema(schema)
    except SchemaError:
        raise A2uiError("A2UI_SCHEMA_INVALID") from None
    if next(validator.iter_errors(value), None) is not None:
        raise A2uiError(code)


def require_object(value: JsonValue, code: str) -> JsonObject:
    if not isinstance(value, dict):
        raise A2uiError(code)
    return value


def require_size(value: JsonValue, limit: int, code: str) -> None:
    if len(json_bytes(value)) > limit:
        raise A2uiError(code)


def reject_authority_keys(value: JsonValue) -> None:
    blocked = {
        "authorization",
        "cookie",
        "credential",
        "credentials",
        "credentialhandle",
        "environment",
        "transportauthority",
        "targetendpoint",
        "url",
        "host",
    }

    def walk(node: JsonValue, depth: int) -> None:
        if depth > 32:
            raise A2uiError("A2UI_ACTION_CONTEXT_INVALID")
        if isinstance(node, dict):
            for key, child in node.items():
                normalized = key.replace("_", "").replace("-", "").lower()
                if normalized in blocked:
                    raise A2uiError("A2UI_ACTION_CONTEXT_AUTHORITY_FORBIDDEN")
                walk(child, depth + 1)
        elif isinstance(node, list):
            for child in node:
                walk(child, depth + 1)

    walk(value, 1)
