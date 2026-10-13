"""Bounded temporary A2UI forms: trusted display data and user submissions only.

This profile has no published Application, business invocation or data persistence.
The caller owns card identity, durable scope, replay and workflow continuation.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from typing import Any, Literal, Never, TypedDict, cast

from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field, JsonValue
from referencing import Registry, Resource

from .application_runtime import PreparedApplication
from .models import ActionRejected

PROFILE = "a2flow.temporary.v1"
SUBMIT_ACTION = "submit"
CATALOG_ID = "https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json"
_COMMON_ID = "https://a2ui.org/specification/v0_9/common_types.json"
_ALIAS_ID = "https://a2ui.org/specification/v0_9/catalog.json"
ALLOWED_COMPONENTS = frozenset(
    {
        "Column",
        "Row",
        "Card",
        "List",
        "Divider",
        "Text",
        "Button",
        "TextField",
        "ChoicePicker",
        "CheckBox",
        "Slider",
        "DateTimeInput",
    }
)
_INPUT_TYPES = {
    "TextField": "string",
    "DateTimeInput": "string",
    "CheckBox": "boolean",
    "ChoicePicker": "array",
    "Slider": "number",
}
_ID = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}")
_FIELD = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}")
_DENIED_KEYS = frozenset(
    {
        "url",
        "svgPath",
        "html",
        "script",
        "functionCall",
        "call",
        "checks",
        "validationRegexp",
        "__proto__",
        "constructor",
        "prototype",
    }
)
_UNSAFE_LITERAL = re.compile(
    r"(?:https?://|javascript:|data:|<\s*(?:script|iframe|object)\b)", re.I
)
_MAX_BYTES = 128 * 1024


class TemporaryCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    title: str = Field(min_length=1, max_length=160)
    mode: Literal["DISPLAY_ONLY", "INTERACTIVE"]
    components: list[dict[str, Any]] = Field(min_length=1, max_length=128)
    inputSchema: dict[str, Any]


class SubmissionResult(TypedDict):
    status: Literal["SUBMITTED"]
    values: dict[str, Any]


@dataclass(frozen=True)
class _Admission:
    candidate: TemporaryCandidate
    data: dict[str, Any]
    inputs: dict[str, Any]
    submit_component: str | None


def _reject(code: str) -> Never:
    raise ActionRejected("TEMPORARY_INTERACTION_" + code)


def bounded_json(value: object, *, max_bytes: int = _MAX_BYTES) -> JsonValue:
    """Detach JSON after bounding shape, recursion and exact serializable types."""
    count = 0
    stack = [(value, 0)]
    while stack:
        item, depth = stack.pop()
        count += 1
        if count > 20000 or depth > 24:
            _reject("SIZE_LIMIT")
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                _reject("JSON_INVALID")
            stack.extend((child, depth + 1) for child in item.values())
        elif type(item) is list:
            stack.extend((child, depth + 1) for child in item)
        elif type(item) not in {str, int, float, bool, type(None)} or (
            type(item) is float and not math.isfinite(item)
        ):
            _reject("JSON_INVALID")
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
        if len(encoded.encode()) > max_bytes:
            _reject("SIZE_LIMIT")
        return cast(JsonValue, json.loads(encoded))
    except (TypeError, ValueError, RecursionError, UnicodeError):
        _reject("JSON_INVALID")


def _object(value: object, *, max_bytes: int = _MAX_BYTES) -> dict[str, Any]:
    result = bounded_json(value, max_bytes=max_bytes)
    if not isinstance(result, dict):
        _reject("JSON_INVALID")
    return result


@lru_cache(maxsize=1)
def _official() -> tuple[dict[str, Any], Registry]:
    try:
        root = files("a2flow_a2ui").joinpath("official")
        catalog = json.loads(root.joinpath("catalog.json").read_text())
        common = json.loads(root.joinpath("common_types.json").read_text())
    except (ImportError, OSError, ValueError):
        _reject("CATALOG_UNAVAILABLE")
    if catalog.get("catalogId") != CATALOG_ID:
        _reject("CATALOG_INVALID")
    alias = {**catalog, "$id": _ALIAS_ID}
    registry = Registry().with_resources(
        [
            (CATALOG_ID, Resource.from_contents(catalog)),
            (_COMMON_ID, Resource.from_contents(common)),
            (_ALIAS_ID, Resource.from_contents(alias)),
        ]
    )
    return catalog, registry


def generation_contract() -> dict[str, Any]:
    catalog, _ = _official()
    return {
        "profile": PROFILE,
        "surfaceId": "main",
        "rootId": "root",
        "allowedComponents": {
            name: catalog["components"][name] for name in sorted(ALLOWED_COMPONENTS)
        },
        "commonTypes": json.loads(
            files("a2flow_a2ui").joinpath("official/common_types.json").read_text()
        ),
        "catalogDefinitions": catalog.get("$defs", {}),
        "submitAction": SUBMIT_ACTION,
    }


def _schema(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if (
        set(schema) != {"type", "properties", "required", "additionalProperties"}
        or schema["type"] != "object"
        or schema["additionalProperties"] is not False
        or type(schema["properties"]) is not dict
        or len(schema["properties"]) > 32
        or type(schema["required"]) is not list
    ):
        _reject("INPUT_SCHEMA_INVALID")
    properties = schema["properties"]
    required = schema["required"]
    if (
        any(type(name) is not str for name in required)
        or len(set(required)) != len(required)
        or set(required) - set(properties)
    ):
        _reject("INPUT_SCHEMA_INVALID")
    for name, field in properties.items():
        if (
            not _FIELD.fullmatch(name)
            or name in _DENIED_KEYS
            or type(field) is not dict
            or type(field.get("type")) is not str
            or field["type"] not in {"string", "boolean", "number", "array"}
        ):
            _reject("INPUT_SCHEMA_INVALID")
        kind = field["type"]
        allowed = {"type", "title", "description"}
        allowed |= {"enum", "minLength", "maxLength"} if kind == "string" else set()
        allowed |= {"minimum", "maximum"} if kind == "number" else set()
        allowed |= {"items", "minItems", "maxItems", "uniqueItems"} if kind == "array" else set()
        if set(field) - allowed:
            _reject("INPUT_SCHEMA_INVALID")
        if kind == "array":
            items = field.get("items")
            if (
                type(items) is not dict
                or items.get("type") != "string"
                or set(items) - {"type", "enum"}
            ):
                _reject("INPUT_SCHEMA_INVALID")
        try:
            Draft202012Validator.check_schema(field)
        except Exception:
            _reject("INPUT_SCHEMA_INVALID")
        for value in (field.get("enum"), field.get("items", {}).get("enum")):
            if value is not None and (
                type(value) is not list
                or not 1 <= len(value) <= 128
                or any(type(item) is not str or len(item) > 512 for item in value)
                or len(set(value)) != len(value)
            ):
                _reject("INPUT_SCHEMA_INVALID")
        for bound, limit in (
            ("minLength", 8192),
            ("maxLength", 8192),
            ("minItems", 128),
            ("maxItems", 128),
        ):
            if bound in field and (type(field[bound]) is not int or not 0 <= field[bound] <= limit):
                _reject("INPUT_SCHEMA_INVALID")
        for lower, upper in (
            ("minLength", "maxLength"),
            ("minItems", "maxItems"),
            ("minimum", "maximum"),
        ):
            if lower in field and upper in field and field[lower] > field[upper]:
                _reject("INPUT_SCHEMA_INVALID")
    return cast(dict[str, dict[str, Any]], properties)


def _tokens(path: str) -> list[str]:
    if not path or re.search(r"~(?![01])", path):
        _reject("DATA_PATH_INVALID")
    return [token.replace("~1", "/").replace("~0", "~") for token in path.lstrip("/").split("/")]


def _read(value: object, path: str) -> object:
    for token in _tokens(path):
        if isinstance(value, dict) and token in value:
            value = value[token]
        elif isinstance(value, list) and token.isdecimal() and int(token) < len(value):
            value = value[int(token)]
        else:
            _reject("DATA_PATH_NOT_FOUND")
    return value


def _safe_component(value: object) -> None:
    if isinstance(value, dict):
        if set(value) & _DENIED_KEYS:
            _reject("AUTHORITY_FORBIDDEN")
        for child in value.values():
            _safe_component(child)
    elif isinstance(value, list):
        for child in value:
            _safe_component(child)
    elif isinstance(value, str) and _UNSAFE_LITERAL.search(value):
        _reject("AUTHORITY_FORBIDDEN")


def _references(component: dict[str, Any]) -> list[str]:
    children = component.get("children")
    if isinstance(children, list):
        return children
    if isinstance(children, dict):
        return [children["componentId"]]
    if "child" in component:
        return [component["child"]]
    return []


def _admit(candidate: TemporaryCandidate | dict[str, Any], data: dict[str, Any]) -> _Admission:
    raw = candidate.model_dump() if isinstance(candidate, TemporaryCandidate) else candidate
    raw = _object(raw)
    data = _object(data)
    if type(data) is not dict:
        _reject("DATA_INVALID")
    try:
        value = TemporaryCandidate.model_validate(raw)
    except ValueError:
        _reject("CANDIDATE_INVALID")
    properties = _schema(value.inputSchema)
    if (value.mode == "DISPLAY_ONLY" and properties) or (
        value.mode == "INTERACTIVE" and not properties
    ):
        _reject("MODE_INVALID")
    _safe_component(value.title)
    _, registry = _official()
    indexed: dict[str, dict[str, Any]] = {}
    bound: dict[str, str] = {}
    submit: str | None = None
    for component in value.components:
        _safe_component(component)
        name, kind = component.get("id"), component.get("component")
        if (
            type(name) is not str
            or not _ID.fullmatch(name)
            or name in indexed
            or type(kind) is not str
            or kind not in ALLOWED_COMPONENTS
        ):
            _reject("COMPONENT_INVALID")
        validator = Draft202012Validator(
            {"$ref": CATALOG_ID + "#/components/" + kind}, registry=registry
        )
        if next(validator.iter_errors(component), None) is not None:
            _reject("COMPONENT_INVALID")
        indexed[name] = component
        if kind in _INPUT_TYPES:
            path = component.get("value")
            if (
                type(path) is not dict
                or set(path) != {"path"}
                or type(path["path"]) is not str
                or not path["path"].startswith("/inputs/")
            ):
                _reject("INPUT_BINDING_INVALID")
            field = path["path"][8:]
            if (
                field not in properties
                or field in bound
                or properties[field]["type"] != _INPUT_TYPES[kind]
            ):
                _reject("INPUT_BINDING_INVALID")
            bound[field] = name
            if kind == "ChoicePicker":
                choices = [option["value"] for option in component["options"]]
                enum = properties[field]["items"].get("enum")
                if (
                    not choices
                    or len(choices) > 128
                    or len(set(choices)) != len(choices)
                    or enum is None
                    or set(enum) != set(choices)
                ):
                    _reject("CHOICE_CONTRACT_INVALID")
                if (
                    component.get("variant", "mutuallyExclusive") == "mutuallyExclusive"
                    and properties[field].get("maxItems") != 1
                ):
                    _reject("CHOICE_CONTRACT_INVALID")
            if kind == "Slider" and (
                properties[field].get("minimum") != component.get("min", 0)
                or properties[field].get("maximum") != component["max"]
            ):
                _reject("INPUT_BINDING_INVALID")
        if "action" in component:
            expected = {
                "event": {
                    "name": SUBMIT_ACTION,
                    "context": {field: {"path": "/inputs/" + field} for field in properties},
                }
            }
            if (
                kind != "Button"
                or submit is not None
                or component["action"] != expected
                or value.mode != "INTERACTIVE"
            ):
                _reject("ACTION_NOT_ALLOWED")
            submit = name
    if set(bound) != set(properties) or (value.mode == "INTERACTIVE") != (submit is not None):
        _reject("INPUT_BINDING_INVALID")
    if "root" not in indexed or indexed["root"]["component"] not in {"Column", "Row"}:
        _reject("ROOT_INVALID")
    visited: set[str] = set()

    def visit(name: str, rows: list[Any] | None, depth: int) -> None:
        if depth > 16 or name not in indexed or name in visited:
            _reject("TREE_INVALID")
        visited.add(name)
        component = indexed[name]
        kind = component["component"]
        if rows is not None and (kind in _INPUT_TYPES or "action" in component):
            _reject("INPUT_SCOPE_INVALID")
        children = component.get("children")
        template = isinstance(children, dict)
        if isinstance(children, dict) and (
            kind != "List" or set(children) != {"componentId", "path"}
        ):
            _reject("DATA_PATH_INVALID")
        context_rows = rows if rows is not None else [None]

        def paths(node: object, location: tuple[str, ...] = ()) -> None:
            if isinstance(node, dict):
                if "path" in node:
                    path = node["path"]
                    if template and location == ("children",):
                        pass  # The list's data source is checked separately below.
                    elif location == ("value",) and kind in _INPUT_TYPES:
                        pass  # Exact /inputs/<field> binding checked above.
                    elif location[:2] == ("action", "event"):
                        pass  # The complete action shape was checked above.
                    else:
                        if type(path) is not str or set(node) != {"path"}:
                            _reject("DATA_PATH_INVALID")
                        for row in context_rows:
                            if path.startswith("/data/"):
                                found = _read(data, path[6:])
                            elif not path.startswith("/") and row is not None:
                                found = _read(row, path)
                            else:
                                _reject("DATA_PATH_NOT_ALLOWED")
                            if type(found) not in {str, int, float, bool, type(None)}:
                                _reject("DATA_VALUE_INVALID")
                            if (kind != "Text" or location != ("text",)) and type(found) is not str:
                                _reject("DATA_VALUE_INVALID")
                for key, child in node.items():
                    paths(child, (*location, key))
            elif isinstance(node, list):
                for index, child in enumerate(node):
                    paths(child, (*location, str(index)))

        paths(component)
        next_rows = rows
        if isinstance(children, dict):
            path = children["path"]
            next_rows = []
            for row in context_rows:
                if path.startswith("/data/"):
                    items = _read(data, path[6:])
                elif not path.startswith("/") and row is not None:
                    items = _read(row, path)
                else:
                    _reject("DATA_PATH_NOT_ALLOWED")
                if type(items) is not list or not items or len(items) > 128:
                    _reject("LIST_DATA_INVALID")
                next_rows.extend(items)
            if len(next_rows) > 128:
                _reject("SIZE_LIMIT")
        for child in _references(component):
            visit(child, next_rows, depth + 1)

    visit("root", None, 1)
    if len(visited) != len(indexed):
        _reject("TREE_INVALID")
    initial = {
        name: {"string": "", "boolean": False, "number": field.get("minimum", 0), "array": []}[
            field["type"]
        ]
        for name, field in properties.items()
    }
    return _Admission(value, data, initial, submit)


def prepare_interaction(
    candidate: TemporaryCandidate | dict[str, Any], data: dict[str, Any]
) -> PreparedApplication:
    admitted = _admit(candidate, data)
    value = admitted.candidate
    key = "temporary-interaction"
    digest = hashlib.sha256(
        json.dumps(
            {"candidate": value.model_dump(), "data": admitted.data},
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    ).hexdigest()
    version = "temporary-" + digest[:32]
    messages = [
        {"version": "v0.9.1", "createSurface": {"surfaceId": "main", "catalogId": CATALOG_ID}},
        {
            "version": "v0.9.1",
            "updateComponents": {"surfaceId": "main", "components": value.components},
        },
        {
            "version": "v0.9.1",
            "updateDataModel": {
                "surfaceId": "main",
                "path": "/",
                "value": {"data": admitted.data, "inputs": admitted.inputs},
            },
        },
    ]
    actions = (
        []
        if admitted.submit_component is None
        else [
            {
                "surfaceId": "main",
                "componentId": admitted.submit_component,
                "actionName": SUBMIT_ACTION,
                "inputSchema": value.inputSchema,
            }
        ]
    )
    display = {
        "protocolProfile": PROFILE,
        "definitionSource": "TEMPORARY",
        "applicationKey": key,
        "applicationVersion": version,
        "title": value.title,
        "mode": value.mode,
        "inputSchema": value.inputSchema,
        "snapshotMessages": messages,
        "catalog": {
            "protocolVersion": "v0.9.1",
            "catalogId": CATALOG_ID,
            "catalogRevision": "temporary-v1",
            "catalogDigest": "sha256:"
            + hashlib.sha256(
                json.dumps(_official()[0], sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
        },
        "actions": actions,
        "data": {},
        "components": [],
        "readOnly": False,
    }
    bounded_json(display, max_bytes=384 * 1024)
    return PreparedApplication(
        key,
        version,
        value.mode == "INTERACTIVE",
        json.dumps(display, ensure_ascii=False, allow_nan=False),
    )


def validate_submission(
    display: Mapping[str, Any], action_name: str, inputs: dict[str, Any]
) -> SubmissionResult:
    if (
        display.get("protocolProfile") != PROFILE
        or display.get("definitionSource") != "TEMPORARY"
        or display.get("mode") != "INTERACTIVE"
        or display.get("readOnly") is not False
        or "submission" in display
        or action_name != SUBMIT_ACTION
    ):
        _reject("ACTION_NOT_ALLOWED")
    actions = display.get("actions")
    if (
        not isinstance(actions, list)
        or len(actions) != 1
        or not isinstance(actions[0], dict)
        or actions[0].get("actionName") != SUBMIT_ACTION
    ):
        _reject("ACTION_NOT_ALLOWED")
    schema = display.get("inputSchema")
    if not isinstance(schema, dict) or schema != actions[0].get("inputSchema"):
        _reject("INPUT_SCHEMA_INVALID")
    _schema(schema)
    values = bounded_json(inputs, max_bytes=32 * 1024)
    if (
        type(values) is not dict
        or next(Draft202012Validator(schema).iter_errors(values), None) is not None
    ):
        _reject("SUBMISSION_INVALID")
    return {"status": "SUBMITTED", "values": values}


def completed_interaction(
    display: Mapping[str, Any], result: SubmissionResult
) -> PreparedApplication:
    if (
        type(result) is not dict
        or set(result) != {"status", "values"}
        or result.get("status") != "SUBMITTED"
    ):
        _reject("SUBMISSION_INVALID")
    submitted = validate_submission(display, SUBMIT_ACTION, result["values"])
    finished = _object(dict(display), max_bytes=384 * 1024)
    messages = finished.get("snapshotMessages")
    if not isinstance(messages, list) or not all(isinstance(item, dict) for item in messages):
        _reject("SNAPSHOT_INVALID")
    updates = [message["updateDataModel"] for message in messages if "updateDataModel" in message]
    if len(updates) != 1:
        _reject("SNAPSHOT_INVALID")
    update = updates[0]
    if (
        not isinstance(update, dict)
        or update.get("surfaceId") != "main"
        or update.get("path") != "/"
        or not isinstance(update.get("value"), dict)
        or not isinstance(update["value"].get("inputs"), dict)
    ):
        _reject("SNAPSHOT_INVALID")
    update["value"]["inputs"].update(submitted["values"])
    finished.update(actions=[], submission=submitted, readOnly=True, mode="DISPLAY_ONLY")
    bounded_json(finished, max_bytes=384 * 1024)
    return PreparedApplication(
        finished["applicationKey"],
        finished["applicationVersion"],
        False,
        json.dumps(finished, ensure_ascii=False, allow_nan=False),
    )
