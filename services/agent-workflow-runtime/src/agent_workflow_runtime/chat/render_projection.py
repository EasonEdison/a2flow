"""Deterministic, model-facing facts from a canonical A2UI snapshot."""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from typing import Literal, NotRequired, TypedDict, cast

from .cards import JsonObject, JsonValue

_PRIVATE_KEYS = frozenset({
    "authorization", "cookie", "credential", "credentials", "credentialhandle",
    "runtimesessiontoken", "transportauthority", "targetendpoint",
})
_MISSING = object()
_MAX_TEXT = 8000
_MAX_CONTENT_ITEMS = 512
_MAX_OPTIONS = 100
_MAX_REACHABLE_COMPONENTS = 4096
_MAX_COMPONENT_DEPTH = 64


class TextContent(TypedDict):
    kind: Literal["text", "markdown", "button"]
    text: str


class ChoiceOption(TypedDict):
    label: str
    value: str


class ChoiceContent(TypedDict):
    kind: Literal["choice"]
    label: NotRequired[str]
    options: list[ChoiceOption]
    selectedValues: NotRequired[list[str]]


class FieldContent(TypedDict):
    kind: Literal["field"]
    label: str
    value: NotRequired[str]


RenderedContentItem = TextContent | ChoiceContent | FieldContent


class RenderedSurfaceContent(TypedDict):
    surfaceId: str
    content: list[RenderedContentItem]


class RenderedContent(TypedDict):
    surfaces: list[RenderedSurfaceContent]


def _normalized_key(value: str) -> str:
    return value.replace("_", "").replace("-", "").lower()


def sanitize_observation(value: JsonValue) -> JsonValue:
    """Remove private authority-bearing keys from a detached JSON value."""

    if isinstance(value, Mapping):
        return {
            key: sanitize_observation(item)
            for key, item in value.items()
            if _normalized_key(key) not in _PRIVATE_KEYS
        }
    if isinstance(value, list):
        return [sanitize_observation(item) for item in value]
    return copy.deepcopy(value)


def _pointer_tokens(pointer: str) -> tuple[str, ...] | None:
    if not pointer.startswith("/") or len(pointer) > 1024:
        return None
    tokens: list[str] = []
    for raw in pointer[1:].split("/"):
        token = ""
        offset = 0
        while offset < len(raw):
            if raw[offset] != "~":
                token += raw[offset]
                offset += 1
                continue
            if offset + 1 >= len(raw) or raw[offset + 1] not in {"0", "1"}:
                return None
            token += "~" if raw[offset + 1] == "0" else "/"
            offset += 2
        if _normalized_key(token) in _PRIVATE_KEYS:
            return None
        tokens.append(token)
    return tuple(tokens)


def _read_path(root: JsonValue, pointer: str) -> JsonValue | object:
    tokens = _pointer_tokens(pointer)
    if tokens is None:
        return _MISSING
    current: JsonValue = root
    for token in tokens:
        if isinstance(current, Mapping):
            if token not in current:
                return _MISSING
            current = current[token]
        elif isinstance(current, list) and token.isdigit():
            index = int(token)
            if index >= len(current):
                return _MISSING
            current = current[index]
        else:
            return _MISSING
    return sanitize_observation(current)


def _resolve(value: object, data: JsonValue) -> JsonValue | object:
    if isinstance(value, Mapping):
        if set(value) == {"path"} and type(value.get("path")) is str:
            return _read_path(data, value["path"])
        return _MISSING
    if isinstance(value, (str, int, float, bool, list)) or value is None:
        return sanitize_observation(cast(JsonValue, value))
    return _MISSING


def _text(value: object, data: JsonValue) -> str | None:
    resolved = _resolve(value, data)
    return resolved if type(resolved) is str and 0 < len(resolved) <= _MAX_TEXT else None


def _string_list(value: object, data: JsonValue) -> list[str] | None:
    resolved = _resolve(value, data)
    if not isinstance(resolved, list) or any(type(item) is not str for item in resolved):
        return None
    return cast(list[str], resolved)


def _surface_states(
    snapshot: Sequence[Mapping[str, object]],
) -> list[tuple[str, dict[str, JsonObject], JsonValue, bool]]:
    order: list[str] = []
    components: dict[str, dict[str, JsonObject]] = {}
    data_models: dict[str, JsonValue] = {}
    for message in snapshot:
        create = message.get("createSurface")
        if isinstance(create, Mapping) and type(create.get("surfaceId")) is str:
            surface_id = create["surfaceId"]
            if surface_id not in components:
                order.append(surface_id)
                components[surface_id] = {}
            continue
        update = message.get("updateComponents")
        if isinstance(update, Mapping) and type(update.get("surfaceId")) is str:
            surface_id = update["surfaceId"]
            raw_components = update.get("components")
            if surface_id not in components or not isinstance(raw_components, list):
                continue
            for raw in raw_components:
                if isinstance(raw, Mapping) and type(raw.get("id")) is str:
                    components[surface_id][raw["id"]] = cast(JsonObject, copy.deepcopy(raw))
            continue
        update_data = message.get("updateDataModel")
        if (
            isinstance(update_data, Mapping)
            and type(update_data.get("surfaceId")) is str
            and update_data.get("path") == "/"
            and "value" in update_data
        ):
            data_models[update_data["surfaceId"]] = cast(
                JsonValue, copy.deepcopy(update_data["value"]),
            )
    return [
        (
            surface_id,
            components[surface_id],
            data_models.get(surface_id, {}),
            surface_id in data_models,
        )
        for surface_id in order
    ]


def _choice(component: JsonObject, data: JsonValue) -> ChoiceContent | None:
    raw_options = component.get("options")
    selected = _string_list(component.get("value"), data)
    if not isinstance(raw_options, list) or len(raw_options) > _MAX_OPTIONS:
        return None
    options: list[ChoiceOption] = []
    for raw in raw_options:
        if not isinstance(raw, Mapping) or type(raw.get("value")) is not str:
            return None
        label = _text(raw.get("label"), data)
        if label is None:
            return None
        options.append({"label": label, "value": raw["value"]})
    content: ChoiceContent = {"kind": "choice", "options": options}
    if selected is not None:
        content["selectedValues"] = selected
    label = _text(component.get("label"), data)
    if label is not None:
        content["label"] = label
    return content


def _project_surface(
    components: dict[str, JsonObject], data: JsonValue,
) -> tuple[list[RenderedContentItem], list[tuple[str, ...]]]:
    content: list[RenderedContentItem] = []
    visited: set[str] = set()
    obscured_paths: list[tuple[str, ...]] = []

    def add(item: RenderedContentItem) -> None:
        if len(content) < _MAX_CONTENT_ITEMS:
            content.append(item)

    def visit(component_id: str, depth: int) -> None:
        if (
            component_id in visited
            or len(content) >= _MAX_CONTENT_ITEMS
            or len(visited) >= _MAX_REACHABLE_COMPONENTS
            or depth > _MAX_COMPONENT_DEPTH
        ):
            return
        visited.add(component_id)
        component = components.get(component_id)
        if component is None or type(component.get("component")) is not str:
            return
        kind = component["component"]
        if kind in {"Row", "Column", "List"}:
            children = component.get("children")
            if isinstance(children, list) and all(type(child) is str for child in children):
                for child in children:
                    visit(child, depth + 1)
            return
        if kind == "Card":
            child = component.get("child")
            if type(child) is str:
                visit(child, depth + 1)
            return
        if kind == "Button":
            child_id = component.get("child")
            child = components.get(child_id) if type(child_id) is str else None
            if child is not None and child.get("component") == "Text":
                text = _text(child.get("text"), data)
                if text is not None:
                    visited.add(child_id)
                    add({"kind": "button", "text": text})
            return
        if kind == "Text":
            text = _text(component.get("text"), data)
            if text is not None:
                add({"kind": "text", "text": text})
            return
        if kind == "Markdown":
            text = _text(component.get("content"), data)
            if text is not None:
                add({"kind": "markdown", "text": text})
            return
        if kind == "ChoicePicker":
            choice = _choice(component, data)
            if choice is not None:
                add(choice)
            return
        if kind == "TextField":
            label = _text(component.get("label"), data)
            if label is None:
                return
            field: FieldContent = {"kind": "field", "label": label}
            if component.get("variant") == "obscured":
                value = component.get("value")
                if isinstance(value, Mapping) and set(value) == {"path"}:
                    path = value.get("path")
                    tokens = _pointer_tokens(path) if type(path) is str else None
                    if tokens:
                        obscured_paths.append(tokens)
            else:
                value = _resolve(component.get("value"), data)
                if type(value) is str and len(value) <= _MAX_TEXT:
                    field["value"] = value
            add(field)
            return
        if kind == "TextDownload":
            text = _text(component.get("label"), data)
            if text is not None:
                add({"kind": "button", "text": text})

    visit("root", 0)
    return content, obscured_paths


def _redact_paths(value: JsonValue, paths: list[tuple[str, ...]]) -> JsonValue:
    redacted = sanitize_observation(value)
    for path in paths:
        current = redacted
        for token in path[:-1]:
            if isinstance(current, dict) and token in current:
                current = current[token]
            elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
                current = current[int(token)]
            else:
                break
        else:
            final = path[-1]
            if isinstance(current, dict):
                current.pop(final, None)
            elif isinstance(current, list) and final.isdigit() and int(final) < len(current):
                current[int(final)] = None
    return redacted


def project_business_state(snapshot: Sequence[Mapping[str, object]]) -> JsonObject:
    """Project canonical DataModels while redacting private and obscured fields."""

    surfaces: list[JsonObject] = []
    for surface_id, components, data, data_defined in _surface_states(snapshot):
        if not data_defined:
            continue
        _, obscured_paths = _project_surface(components, data)
        surfaces.append({
            "surfaceId": surface_id,
            "data": _redact_paths(data, obscured_paths),
        })
    return {"surfaces": surfaces}


def project_rendered_content(snapshot: Sequence[Mapping[str, object]]) -> RenderedContent:
    """Project deterministic visible facts from canonical, root-reachable components."""

    surfaces: list[RenderedSurfaceContent] = []
    for surface_id, components, data, _ in _surface_states(snapshot):
        content, _ = _project_surface(components, data)
        if content:
            surfaces.append({"surfaceId": surface_id, "content": content})
    return {"surfaces": surfaces}
