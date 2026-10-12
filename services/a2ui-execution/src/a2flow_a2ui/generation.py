"""Admission of generated layouts against a published Application and Catalog."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from importlib.resources import files
from typing import Literal, Protocol, TypeAlias, cast

from a2flow_capability.models import JsonObject, JsonValue, TrustedContext
from jsonschema import Draft202012Validator
from pydantic import TypeAdapter
from referencing import Registry, Resource

from .jsonutil import read, reject_authority_keys, require_object, require_size, tokens
from .ledger import PROTOCOL_VERSION, SurfaceLedger
from .models import (
    A2uiError,
    ActionBinding,
    ActionDeclaration,
    GeneratedCandidate,
    GeneratedDefinition,
    GenerationAction,
    GenerationAnchor,
    GenerationComponent,
    GenerationContract,
    GenerationCreateSurfaceEnvelope,
    GenerationReadOnlyDisplayBinding,
    GenerationRelativeBinding,
    GenerationScope,
    GenerationSurface,
    GenerationTemplateScope,
    GenerationUpdateComponentsEnvelope,
    PublishedApplication,
    ShowInputBinding,
    ShowInputSource,
)

_OFFICIAL_ID = "https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json"
_COMMON_ID = "https://a2ui.org/specification/v0_9/common_types.json"
_CATALOG_ALIAS = "https://a2ui.org/specification/v0_9/catalog.json"
_DENIED_COMPONENTS = frozenset({"Image", "Video", "AudioPlayer", "Icon"})
_MAX_COMPONENTS = 256
_MAX_BYTES = 256 * 1024
_MAX_DEPTH = 24
ScopeLineage: TypeAlias = tuple[tuple[str, str, str], ...]
RelativeRule: TypeAlias = tuple[str, str, tuple[str, ...], str, ScopeLineage]
ReadOnlyDisplayRule: TypeAlias = tuple[str, tuple[str, ...], str, ScopeLineage]
_PLAIN_SCHEMA_TYPES = frozenset({"string", "number", "integer", "boolean"})
_SCHEMA_INDIRECTION = frozenset(
    {"$ref", "$dynamicRef", "allOf", "anyOf", "oneOf", "not", "if", "then", "else"}
)


class GenerationCatalogReader(Protocol):
    def generation_catalog(self, catalog_id: str, context: TrustedContext) -> dict[str, str]: ...


def _official() -> tuple[JsonObject, JsonObject, Registry]:
    root = files("a2flow_a2ui").joinpath("official")
    catalog = cast(JsonObject, json.loads(root.joinpath("catalog.json").read_text()))
    common = cast(JsonObject, json.loads(root.joinpath("common_types.json").read_text()))
    alias = {**catalog, "$id": _CATALOG_ALIAS}
    registry = Registry().with_resources(
        [
            (_OFFICIAL_ID, Resource.from_contents(catalog)),
            (_COMMON_ID, Resource.from_contents(common)),
            (_CATALOG_ALIAS, Resource.from_contents(alias)),
        ]
    )
    return catalog, common, registry


def _components(membership: Mapping[str, str]) -> tuple[GenerationComponent, ...]:
    catalog, _, _ = _official()
    definitions = require_object(catalog.get("components"), "A2UI_GENERATION_CATALOG_INVALID")
    allowed: list[GenerationComponent] = []
    for name, origin in sorted(membership.items()):
        if origin != "A2UI_OFFICIAL" or name in _DENIED_COMPONENTS:
            continue
        definition = definitions.get(name)
        if not isinstance(definition, dict):
            raise A2uiError("A2UI_GENERATION_CATALOG_INVALID")
        allowed.append(GenerationComponent(type=name, schema=definition))
    if not allowed:
        raise A2uiError("A2UI_GENERATION_CATALOG_INVALID")
    return tuple(allowed)


def _walk_paths(value: JsonValue, result: set[str]) -> None:
    if isinstance(value, dict):
        path = value.get("path")
        if isinstance(path, str):
            result.add(path)
        for child in value.values():
            _walk_paths(child, result)
    elif isinstance(value, list):
        for child in value:
            _walk_paths(child, result)


def _data_paths(published: PublishedApplication) -> tuple[str, ...]:
    paths: set[str] = set()
    for component in _original_components(published).values():
        _walk_paths(component, paths)
    for message in published.build.initial_messages:
        update = message.get("updateDataModel")
        if isinstance(update, dict):
            path = update.get("path")
            if isinstance(path, str) and path.startswith("/"):
                paths.add(path)
    for binding in published.build.load_bindings:
        for adapter in (*binding.result_adapters, *binding.failure_result_adapters):
            template = adapter.message_template
            if template:
                update = template.get("updateDataModel")
                if isinstance(update, dict):
                    path = update.get("path")
                    if isinstance(path, str) and path.startswith("/"):
                        paths.add(path)
    return tuple(sorted(path for path in paths if path.startswith("/") and path != "/"))


def _original_components(published: PublishedApplication) -> dict[tuple[str, str], JsonObject]:
    components: dict[tuple[str, str], JsonObject] = {}
    for message in published.build.initial_messages:
        update = message.get("updateComponents")
        if not isinstance(update, dict):
            continue
        raw_components = update.get("components")
        if not isinstance(raw_components, list):
            continue
        surface_id = update.get("surfaceId")
        for raw in raw_components:
            if isinstance(surface_id, str) and isinstance(raw, dict):
                component_id = raw.get("id")
                if isinstance(component_id, str):
                    components[(surface_id, component_id)] = raw
    return components


def _message_envelope_schema() -> JsonObject:
    schema = TypeAdapter(
        tuple[GenerationCreateSurfaceEnvelope | GenerationUpdateComponentsEnvelope, ...]
    ).json_schema(by_alias=True)
    schema["minItems"] = 2
    schema["maxItems"] = 64
    schema["prefixItems"] = [{"$ref": "#/$defs/GenerationCreateSurfaceEnvelope"}]
    schema["description"] = (
        "A2UI v0.9.1 message envelopes: first createSurface, followed by "
        "createSurface or updateComponents. Each update must refer to a previously "
        "created surface; the runtime appends trusted updateDataModel messages."
    )
    return schema


def contract(published: PublishedApplication, membership: Mapping[str, str]) -> GenerationContract:
    components = _components(membership)
    for message in published.build.initial_messages:
        reject_authority_keys(message)
    source = _original_components(published)
    # Engineering references remain usable after layout generation.
    anchors = tuple(sorted({component_id for _, component_id in source}))
    return GenerationContract(
        originAppCode=published.release.app_code,
        paramsSchema=published.build.params_schema,
        sourceMessages=published.build.initial_messages,
        messageEnvelopeSchema=_message_envelope_schema(),
        allowedComponents=components,
        allowedDataPaths=_data_paths(published),
        relativeDataBindings=_relative_bindings(published),
        readOnlyDisplayBindings=_read_only_display_bindings(published),
        requiredAnchors=anchors,
        anchorComponents=tuple(
            GenerationAnchor(surfaceId=surface_id, componentId=component_id, component=raw)
            for (surface_id, component_id), raw in sorted(source.items())
        ),
        surfaces=tuple(
            GenerationSurface(surfaceId=item.surface_id, rootComponentId=item.root_component_id)
            for item in published.build.surface_declarations
        ),
        mustPreserve=(
            "Keep every anchor component ID and component type on its original surface; "
            "keep each surface root ID. Anchors may move within a valid tree. Copy any approved "
            "local function expression exactly at the same component property. Relative data "
            "paths must remain inside the identical templateScopes lineage listed in "
            "relativeDataBindings; never move them to another list template. Place server "
            "event actions only through approved actionPlacements. readOnlyDisplayBindings "
            "permit only Text.text reads of explicitly declared APP_PARAMS fields in the same "
            "List template scope; they do not authorize input or action writes. "
            "Keep input-bound properties. "
            "New IDs and layout are allowed using allowedComponents and allowedDataPaths."
        ),
        allowedActions=tuple(
            GenerationAction(
                bindingId=item.binding_id,
                actionName=item.action_code,
                surfaceId=item.surface_id,
                contextSchema=item.context_schema,
            )
            for item in published.build.action_bindings
        ),
        surfaceIds=tuple(item.surface_id for item in published.build.surface_declarations),
    )


def _references(component: JsonObject) -> tuple[str, ...]:
    refs: list[str] = []
    children = component.get("children")
    if isinstance(children, list):
        refs.extend(item for item in children if isinstance(item, str))
    elif isinstance(children, dict):
        child_id = children.get("componentId")
        if isinstance(child_id, str):
            refs.append(child_id)
    for name in ("child", "trigger", "content"):
        value = component.get(name)
        if isinstance(value, str):
            refs.append(value)
    tabs = component.get("tabs")
    if isinstance(tabs, list):
        for tab in tabs:
            if isinstance(tab, dict):
                child_id = tab.get("child")
                if isinstance(child_id, str):
                    refs.append(child_id)
    return tuple(refs)


def _validate_tree(components: dict[str, JsonObject], root: str) -> None:
    if root not in components:
        raise A2uiError("A2UI_GENERATION_ROOT_INVALID")
    states: dict[str, int] = {}

    def visit(component_id: str, depth: int) -> None:
        if depth > _MAX_DEPTH or component_id not in components or states.get(component_id) == 1:
            raise A2uiError("A2UI_GENERATION_TREE_INVALID")
        if states.get(component_id) == 2:
            return
        states[component_id] = 1
        for child in _references(components[component_id]):
            visit(child, depth + 1)
        states[component_id] = 2

    visit(root, 1)
    if len(states) != len(components):
        raise A2uiError("A2UI_GENERATION_TREE_INVALID")


def _path_occurrences(
    value: JsonValue, location: tuple[str, ...] = ()
) -> tuple[tuple[tuple[str, ...], str], ...]:
    found: list[tuple[tuple[str, ...], str]] = []
    if isinstance(value, dict):
        path = value.get("path")
        if isinstance(path, str):
            found.append((location, path))
        for key, child in value.items():
            found.extend(_path_occurrences(child, (*location, key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_path_occurrences(child, (*location, str(index))))
    return tuple(found)


def _scope_contexts(
    components: dict[str, JsonObject], root: str
) -> dict[str, frozenset[ScopeLineage]]:
    contexts: dict[str, set[ScopeLineage]] = {}
    visited: set[tuple[str, ScopeLineage]] = set()

    def visit(component_id: str, scope: ScopeLineage, depth: int) -> None:
        if depth > _MAX_DEPTH or component_id not in components:
            raise A2uiError("A2UI_GENERATION_TREE_INVALID")
        state = (component_id, scope)
        if state in visited:
            return
        visited.add(state)
        contexts.setdefault(component_id, set()).add(scope)
        component = components[component_id]
        children = component.get("children")
        template_id = children.get("componentId") if isinstance(children, dict) else None
        template_path = children.get("path") if isinstance(children, dict) else None
        for child_id in _references(component):
            next_scope = scope
            if child_id == template_id and isinstance(template_path, str):
                next_scope = (*scope, (component_id, child_id, template_path))
            visit(child_id, next_scope, depth + 1)

    visit(root, (), 1)
    return {component_id: frozenset(scopes) for component_id, scopes in contexts.items()}


def _relative_bindings(published: PublishedApplication) -> tuple[GenerationRelativeBinding, ...]:
    source = _original_components(published)
    bindings: list[GenerationRelativeBinding] = []
    for declaration in published.build.surface_declarations:
        surface_id = declaration.surface_id
        components = {
            component_id: raw
            for (item_surface, component_id), raw in source.items()
            if item_surface == surface_id
        }
        contexts = _scope_contexts(components, declaration.root_component_id)
        for component_id, component in sorted(components.items()):
            component_type = component.get("component")
            if not isinstance(component_type, str):
                raise A2uiError("A2UI_GENERATION_SOURCE_INVALID")
            for location, path in _path_occurrences(component):
                if not path or path.startswith("/"):
                    continue
                scopes = contexts.get(component_id, frozenset())
                if len(scopes) != 1:
                    raise A2uiError("A2UI_GENERATION_SOURCE_INVALID")
                scope = next(iter(scopes))
                bindings.append(
                    GenerationRelativeBinding(
                        surfaceId=surface_id,
                        sourceComponentId=component_id,
                        componentType=component_type,
                        propertyPath="/"
                        + "/".join(part.replace("~", "~0").replace("/", "~1") for part in location),
                        path=path,
                        templateScopes=tuple(
                            GenerationTemplateScope(
                                templateComponentId=item[0],
                                itemComponentId=item[1],
                                dataPath=item[2],
                            )
                            for item in scope
                        ),
                    )
                )
    return tuple(bindings)


def _plain_schema(schema: JsonValue, expected_type: str) -> bool:
    return (
        isinstance(schema, dict)
        and schema.get("type") == expected_type
        and not _SCHEMA_INDIRECTION.intersection(schema)
    )


def _read_only_display_bindings(
    published: PublishedApplication,
) -> tuple[GenerationReadOnlyDisplayBinding, ...]:
    """Authorize explicit primitive APP_PARAMS fields already written into a List DataModel."""
    params_schema = published.build.params_schema
    if not _plain_schema(params_schema, "object"):
        return ()
    params_properties = params_schema.get("properties")
    if not isinstance(params_properties, dict):
        return ()
    bindings: list[GenerationReadOnlyDisplayBinding] = []
    source = _original_components(published)
    for declaration in published.build.surface_declarations:
        surface_id = declaration.surface_id
        components = {
            component_id: raw
            for (item_surface, component_id), raw in source.items()
            if item_surface == surface_id
        }
        contexts = _scope_contexts(components, declaration.root_component_id)
        for list_id, component in sorted(components.items()):
            if component.get("component") != "List":
                continue
            children = component.get("children")
            if not isinstance(children, dict):
                continue
            item_id = children.get("componentId")
            data_path = children.get("path")
            if not isinstance(item_id, str) or not isinstance(data_path, str):
                continue
            if len(contexts.get(item_id, frozenset())) != 1:
                continue
            scope = next(iter(contexts[item_id]))
            if not scope or scope[-1] != (list_id, item_id, data_path):
                continue
            data_tokens = tokens(data_path, allow_root=False)
            if len(data_tokens) != 1:
                continue
            for input_binding in published.build.input_bindings:
                if (
                    input_binding.source is not ShowInputSource.APP_PARAMS
                    or not input_binding.required
                    or input_binding.source_path is None
                ):
                    continue
                source_tokens = tokens(input_binding.source_path, allow_root=False)
                target_tokens = tokens(input_binding.target_path, allow_root=False)
                if len(source_tokens) != 1 or target_tokens != (
                    "updateDataModel", "value", data_tokens[0]
                ):
                    continue
                if input_binding.target_message_index >= len(published.build.initial_messages):
                    continue
                message = published.build.initial_messages[input_binding.target_message_index]
                update = message.get("updateDataModel")
                if not isinstance(update, dict) or update.get("surfaceId") != surface_id:
                    continue
                if update.get("path") != "/":
                    continue
                array_schema = params_properties.get(source_tokens[0])
                if not isinstance(array_schema, dict) or not _plain_schema(
                    array_schema, "array"
                ):
                    continue
                item_schema = array_schema.get("items")
                if not isinstance(item_schema, dict) or not _plain_schema(
                    item_schema, "object"
                ):
                    continue
                item_properties = item_schema.get("properties")
                if not isinstance(item_properties, dict):
                    continue
                for field, field_schema in sorted(item_properties.items()):
                    if not isinstance(field, str) or not re.fullmatch(
                        r"[A-Za-z_][A-Za-z0-9_]*", field
                    ):
                        continue
                    field_type = (
                        field_schema.get("type") if isinstance(field_schema, dict) else None
                    )
                    if (
                        not isinstance(field_type, str)
                        or field_type not in _PLAIN_SCHEMA_TYPES
                        or not _plain_schema(field_schema, field_type)
                    ):
                        continue
                    bindings.append(
                        GenerationReadOnlyDisplayBinding(
                            surfaceId=surface_id,
                            templateScopes=tuple(
                                GenerationTemplateScope(
                                    templateComponentId=item[0],
                                    itemComponentId=item[1],
                                    dataPath=item[2],
                                )
                                for item in scope
                            ),
                            dataPath=data_path,
                            componentType="Text",
                            propertyPath="/text",
                            path=field,
                            valueType=cast(
                                Literal["string", "number", "integer", "boolean"], field_type
                            ),
                        )
                    )
    return tuple(bindings)


def _canonical(value: JsonValue) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _function_expressions(value: JsonValue) -> frozenset[tuple[tuple[str, ...], str]]:
    expressions: set[tuple[tuple[str, ...], str]] = set()

    def walk(node: JsonValue, location: tuple[str, ...]) -> None:
        if isinstance(node, dict):
            if "functionCall" in node or "call" in node:
                expressions.add((location, _canonical(node)))
            for key, child in node.items():
                walk(child, (*location, key))
        elif isinstance(node, list):
            for index, child in enumerate(node):
                walk(child, (*location, str(index)))

    walk(value, ())
    return frozenset(expressions)


def _approved_expressions(
    source: Mapping[tuple[str, str], JsonObject],
) -> frozenset[tuple[str, tuple[str, ...], str]]:
    approved: set[tuple[str, tuple[str, ...], str]] = set()
    for component in source.values():
        component_type = component.get("component")
        if isinstance(component_type, str):
            approved.update(
                (component_type, location, expression)
                for location, expression in _function_expressions(component)
            )
    return frozenset(approved)


def _validate_values(
    value: JsonValue,
    data_paths: frozenset[str],
    relative_rules: frozenset[RelativeRule],
    read_only_display_rules: frozenset[ReadOnlyDisplayRule],
    surface_id: str,
    scopes: frozenset[ScopeLineage],
    expressions: frozenset[tuple[str, tuple[str, ...], str]],
    component_type: str,
    location: tuple[str, ...] = (),
    depth: int = 0,
) -> None:
    if depth > 32:
        raise A2uiError("A2UI_GENERATION_VALUE_DEPTH_INVALID")
    if isinstance(value, dict):
        if any(key in value for key in ("url", "svgPath", "html", "script")):
            raise A2uiError("A2UI_GENERATION_AUTHORITY_FORBIDDEN")
        if ("functionCall" in value or "call" in value) and (
            component_type,
            location,
            _canonical(value),
        ) not in expressions:
            raise A2uiError("A2UI_GENERATION_AUTHORITY_FORBIDDEN")
        if "path" in value:
            path = value["path"]
            if not isinstance(path, str):
                raise A2uiError("A2UI_GENERATION_DATA_PATH_NOT_ALLOWED")
            if path.startswith("/"):
                if path not in data_paths:
                    raise A2uiError("A2UI_GENERATION_DATA_PATH_NOT_ALLOWED")
            else:
                if len(scopes) != 1:
                    raise A2uiError("A2UI_GENERATION_DATA_PATH_NOT_ALLOWED")
                scope = next(iter(scopes))
                if (
                    (surface_id, component_type, location, path, scope) not in relative_rules
                    and not (
                        component_type == "Text"
                        and (surface_id, location, path, scope) in read_only_display_rules
                    )
                ):
                    raise A2uiError("A2UI_GENERATION_DATA_PATH_NOT_ALLOWED")
        for key, child in value.items():
            _validate_values(
                child,
                data_paths,
                relative_rules,
                read_only_display_rules,
                surface_id,
                scopes,
                expressions,
                component_type,
                (*location, key),
                depth + 1,
            )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _validate_values(
                child,
                data_paths,
                relative_rules,
                read_only_display_rules,
                surface_id,
                scopes,
                expressions,
                component_type,
                (*location, str(index)),
                depth + 1,
            )


def _index_components(
    messages: tuple[JsonObject, ...],
) -> dict[tuple[str, str], tuple[int, int, JsonObject]]:
    result: dict[tuple[str, str], tuple[int, int, JsonObject]] = {}
    for message_index, message in enumerate(messages):
        update = message.get("updateComponents")
        if not isinstance(update, dict):
            continue
        raw_components = update.get("components")
        if not isinstance(raw_components, list):
            continue
        surface_id = update.get("surfaceId")
        for component_index, raw in enumerate(raw_components):
            if not isinstance(surface_id, str) or not isinstance(raw, dict):
                raise A2uiError("A2UI_GENERATION_COMPONENT_SHAPE_INVALID")
            component_id = raw.get("id")
            if not isinstance(component_id, str) or not component_id:
                raise A2uiError("A2UI_GENERATION_COMPONENT_SHAPE_INVALID")
            key = (surface_id, component_id)
            if key in result:
                raise A2uiError("A2UI_GENERATION_COMPONENT_DUPLICATE")
            result[key] = (message_index, component_index, raw)
    return result


def _remap_inputs(
    published: PublishedApplication,
    messages: tuple[JsonObject, ...],
    candidate_components: dict[tuple[str, str], tuple[int, int, JsonObject]],
    data_index: dict[int, int],
) -> tuple[ShowInputBinding, ...]:
    original_components = _index_components(published.build.initial_messages)
    remapped: list[ShowInputBinding] = []
    for binding in published.build.input_bindings:
        path = tokens(binding.target_path, allow_root=False)
        old_index = binding.target_message_index
        if old_index >= len(published.build.initial_messages):
            raise A2uiError("A2UI_GENERATION_SOURCE_INVALID")
        if path[:2] == ("updateComponents", "components") and len(path) >= 4:
            old_component_index = int(path[2]) if path[2].isdigit() else -1
            matches = [
                (key, value)
                for key, value in original_components.items()
                if value[0] == old_index and value[1] == old_component_index
            ]
            if len(matches) != 1 or matches[0][0] not in candidate_components:
                raise A2uiError("A2UI_GENERATION_SOURCE_INVALID")
            new_index, new_component_index, _ = candidate_components[matches[0][0]]
            new_path = "/updateComponents/components/" + str(new_component_index)
            escaped_suffix = "/".join(
                token.replace("~", "~0").replace("/", "~1") for token in path[3:]
            )
            new_path += "/" + escaped_suffix
            original_value = read(published.build.initial_messages[old_index], binding.target_path)
            candidate_value = read(messages[new_index], new_path)
            if not original_value.found:
                raise A2uiError("A2UI_GENERATION_SOURCE_INVALID")
            if not candidate_value.found or type(candidate_value.value) is not type(
                original_value.value
            ):
                raise A2uiError("A2UI_GENERATION_INPUT_TARGET_INVALID")
            remapped.append(
                binding.model_copy(
                    update={
                        "target_message_index": new_index,
                        "target_path": new_path,
                    }
                )
            )
        elif old_index in data_index and path[0] == "updateDataModel":
            remapped.append(
                binding.model_copy(update={"target_message_index": data_index[old_index]})
            )
        else:
            raise A2uiError("A2UI_GENERATION_SOURCE_INVALID")
    return tuple(remapped)


def validate_candidate(
    published: PublishedApplication,
    membership: Mapping[str, str],
    candidate: GeneratedCandidate,
) -> PublishedApplication:
    policy = contract(published, membership)
    require_size(candidate.model_dump(by_alias=True), _MAX_BYTES, "A2UI_GENERATION_SIZE_LIMIT")
    _, _, registry = _official()
    schemas = {item.type: item.component_schema for item in policy.allowed_components}
    source = _original_components(published)
    expressions = _approved_expressions(source)
    seen_surfaces: set[str] = set()
    for message in candidate.messages:
        if message.get("version") != PROTOCOL_VERSION:
            raise A2uiError("A2UI_GENERATION_MESSAGE_VERSION_INVALID")
        if len(message) != 2:
            raise A2uiError("A2UI_GENERATION_MESSAGE_ENVELOPE_INVALID")
        if "createSurface" in message:
            body = require_object(
                message["createSurface"], "A2UI_GENERATION_CREATE_SURFACE_SHAPE_INVALID"
            )
            if set(body) - {"surfaceId", "catalogId", "theme", "sendDataModel"}:
                raise A2uiError("A2UI_GENERATION_CREATE_SURFACE_SHAPE_INVALID")
            surface = body.get("surfaceId")
            if (
                not isinstance(surface, str)
                or surface in seen_surfaces
                or surface not in policy.surface_ids
                or body.get("catalogId") != published.build.catalog.catalog_id
            ):
                raise A2uiError("A2UI_GENERATION_SURFACE_INVALID")
            seen_surfaces.add(surface)
        elif "updateComponents" in message:
            body = require_object(
                message["updateComponents"], "A2UI_GENERATION_UPDATE_COMPONENTS_SHAPE_INVALID"
            )
            if set(body) != {"surfaceId", "components"} or not isinstance(
                body.get("components"), list
            ):
                raise A2uiError("A2UI_GENERATION_UPDATE_COMPONENTS_SHAPE_INVALID")
            if body.get("surfaceId") not in seen_surfaces:
                raise A2uiError("A2UI_GENERATION_MESSAGE_ORDER_INVALID")
        else:
            raise A2uiError("A2UI_GENERATION_MESSAGE_ENVELOPE_INVALID")
    all_components = _index_components(candidate.messages)
    if len(all_components) > _MAX_COMPONENTS:
        raise A2uiError("A2UI_GENERATION_SIZE_LIMIT")
    if seen_surfaces != set(policy.surface_ids):
        raise A2uiError("A2UI_GENERATION_SURFACE_INVALID")
    if len({key[0] for key in all_components}) != len(policy.surface_ids):
        raise A2uiError("A2UI_GENERATION_ROOT_INVALID")
    candidate_scopes: dict[tuple[str, str], frozenset[ScopeLineage]] = {}
    for declaration in published.build.surface_declarations:
        component_map = {
            component_id: raw
            for (surface_id, component_id), (_, _, raw) in all_components.items()
            if surface_id == declaration.surface_id
        }
        _validate_tree(component_map, declaration.root_component_id)
        candidate_scopes.update(
            ((declaration.surface_id, component_id), scopes)
            for component_id, scopes in _scope_contexts(
                component_map, declaration.root_component_id
            ).items()
        )
    relative_rules: frozenset[RelativeRule] = frozenset(
        (
            item.surface_id,
            item.component_type,
            tokens(item.property_path, allow_root=False),
            item.path,
            tuple(
                (scope.template_component_id, scope.item_component_id, scope.data_path)
                for scope in item.template_scopes
            ),
        )
        for item in policy.relative_data_bindings
    )
    read_only_display_rules: frozenset[ReadOnlyDisplayRule] = frozenset(
        (
            item.surface_id,
            tokens(item.property_path, allow_root=False),
            item.path,
            tuple(
                (scope.template_component_id, scope.item_component_id, scope.data_path)
                for scope in item.template_scopes
            ),
        )
        for item in policy.read_only_display_bindings
    )
    action_targets: dict[str, list[str]] = {}
    action_declarations: list[ActionDeclaration] = []
    placed_ids: set[tuple[str, str]] = set()
    for placement in candidate.action_placements:
        matches = [
            item
            for item in published.build.action_bindings
            if item.binding_id == placement.binding_id
        ]
        key = (placement.surface_id, placement.source_component_id)
        if (
            len(matches) != 1
            or key in placed_ids
            or placement.surface_id != matches[0].surface_id
            or key not in all_components
        ):
            raise A2uiError("A2UI_GENERATION_ACTION_NOT_ALLOWED")
        binding = matches[0]
        original = source.get((binding.surface_id, binding.source_component_id))
        component = all_components[key][2]
        if (
            original is None
            or component.get("component") != original.get("component")
            or component.get("action") != original.get("action")
        ):
            raise A2uiError("A2UI_GENERATION_ACTION_NOT_ALLOWED")
        action_targets.setdefault(binding.binding_id, []).append(placement.source_component_id)
        declarations = [
            item
            for item in published.build.action_declarations
            if item.surface_id == binding.surface_id
            and item.source_component_id == binding.source_component_id
            and item.action_code == binding.action_code
        ]
        if len(declarations) != 1:
            raise A2uiError("A2UI_GENERATION_SOURCE_INVALID")
        action_declarations.append(
            declarations[0].model_copy(
                update={
                    "source_component_id": placement.source_component_id,
                }
            )
        )
        placed_ids.add(key)
    action_bindings: list[ActionBinding] = []
    for binding in published.build.action_bindings:
        targets = action_targets.get(binding.binding_id)
        if targets:
            action_bindings.append(
                binding.model_copy(
                    update={
                        "allowed_source_component_ids": tuple(targets),
                    }
                )
            )
    for key, (_, _, component) in all_components.items():
        component_type = component.get("component")
        if not isinstance(component_type, str) or component_type not in schemas:
            raise A2uiError("A2UI_GENERATION_COMPONENT_NOT_ALLOWED")
        schema_ref = {"$ref": _OFFICIAL_ID + "#/components/" + component_type}
        validator = Draft202012Validator(schema_ref, registry=registry)
        if next(validator.iter_errors(component), None) is not None:
            raise A2uiError("A2UI_GENERATION_COMPONENT_INVALID")
        action = component.get("action")
        if (
            action is not None
            and key not in placed_ids
            and (not isinstance(action, dict) or "functionCall" not in action)
        ):
            raise A2uiError("A2UI_GENERATION_ACTION_NOT_ALLOWED")
        _validate_values(
            component,
            frozenset(policy.allowed_data_paths),
            relative_rules,
            read_only_display_rules,
            key[0],
            candidate_scopes.get(key, frozenset()),
            expressions,
            component_type,
        )
    for key, original in source.items():
        if key not in all_components or all_components[key][2].get("component") != original.get(
            "component"
        ):
            raise A2uiError("A2UI_GENERATION_ANCHOR_MISSING")
        if not _function_expressions(original).issubset(
            _function_expressions(all_components[key][2])
        ):
            raise A2uiError("A2UI_GENERATION_AUTHORITY_FORBIDDEN")
    SurfaceLedger.empty().reduce(candidate.messages)
    data_messages: list[JsonObject] = []
    data_index: dict[int, int] = {}
    for index, message in enumerate(published.build.initial_messages):
        if "updateDataModel" in message:
            data_index[index] = len(candidate.messages) + len(data_messages)
            data_messages.append(message)
    messages = candidate.messages + tuple(data_messages)
    inputs = _remap_inputs(published, messages, all_components, data_index)
    build = published.build.model_copy(
        update={
            "initial_messages": messages,
            "input_bindings": inputs,
            "action_bindings": tuple(action_bindings),
            "action_declarations": tuple(action_declarations),
            "component_types": tuple(
                sorted({raw[2]["component"] for raw in all_components.values()})
            ),
        }
    )
    return PublishedApplication(published.release, build)


def definition(
    origin_app_code: str,
    candidate: GeneratedCandidate,
    scope: GenerationScope,
    context: TrustedContext,
) -> GeneratedDefinition:
    body = {
        "originAppCode": origin_app_code,
        "candidate": candidate.model_dump(by_alias=True),
        "scope": scope.model_dump(by_alias=True),
        "ownerUserId": context.user_id,
        "environment": context.environment.value,
    }
    digest = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest()
    )
    return GeneratedDefinition.model_validate({**body, "artifactDigest": digest})


def verify_definition(
    value: GeneratedDefinition, scope: GenerationScope, context: TrustedContext
) -> None:
    if (
        value.owner_user_id != context.user_id
        or value.environment is not context.environment
        or value.scope != scope
        or value.artifact_digest
        != definition(value.origin_app_code, value.candidate, value.scope, context).artifact_digest
    ):
        raise A2uiError("A2UI_GENERATED_CARD_SCOPE_MISMATCH")
