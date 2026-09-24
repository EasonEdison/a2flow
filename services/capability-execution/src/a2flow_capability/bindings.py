"""Closed argument validation and deterministic business-request bindings."""

from __future__ import annotations

import math
from decimal import Decimal

from a2flow_capability.models import (
    ArgumentDefinition,
    CapabilityExecutionError,
    ContextField,
    ContextMapping,
    ExecutionErrorCode,
    JsonKind,
    JsonObject,
    JsonValue,
    PublishedPlan,
    TrustedContext,
    ValueSchema,
)

FORBIDDEN_ARGUMENTS = frozenset(
    {"url", "uri", "cookie", "authorization", "headers", "header", "host", "token"}
)


def bind_request(
    plan: PublishedPlan, arguments: JsonObject, context: TrustedContext
) -> tuple[JsonObject, JsonObject]:
    """Validate model arguments and build a new business request without mutating inputs."""
    definitions = {definition.name: definition for definition in plan.arguments}
    effective: JsonObject = {}
    for name, value in arguments.items():
        definition = definitions.get(name)
        if name.lower() in FORBIDDEN_ARGUMENTS or definition is None:
            raise CapabilityExecutionError(
                ExecutionErrorCode.ARGUMENT_INVALID,
                f"argument is undeclared or caller-controlled field is forbidden: {name}",
            )
        _validate_value(name, value, definition.schema)
        normalized = _normalize_value(value, definition.schema)
        _validate_allowed_value(name, normalized, definition)
        effective[name] = normalized

    for definition in plan.arguments:
        if definition.required and (
            definition.name not in arguments or arguments[definition.name] is None
        ):
            raise CapabilityExecutionError(
                ExecutionErrorCode.ARGUMENT_INVALID,
                f"required argument is missing: {definition.name}",
            )

    request: JsonObject = {}
    for request_mapping in plan.request_mappings:
        if request_mapping.argument_name in effective:
            _put_path(
                request,
                request_mapping.request_path,
                effective[request_mapping.argument_name],
            )
    for context_mapping in plan.context_mappings:
        _put_path(
            request,
            context_mapping.request_path,
            _context_value(context_mapping, context),
        )
    for constant_mapping in plan.constant_mappings:
        _put_path(
            request,
            constant_mapping.request_path,
            _clone_json(constant_mapping.value),
        )
    return effective, request


def _validate_value(path: str, value: JsonValue, schema: ValueSchema) -> None:
    if value is None:
        return
    if not _matches_kind(value, schema.kind):
        raise CapabilityExecutionError(
            ExecutionErrorCode.ARGUMENT_TYPE_MISMATCH,
            f"argument type does not match published definition: {path}",
        )
    if schema.kind is JsonKind.ARRAY:
        assert schema.items is not None
        assert isinstance(value, list)
        for index, item in enumerate(value):
            _validate_value(f"{path}[{index}]", item, schema.items)
        return
    if schema.kind is not JsonKind.OBJECT:
        return

    assert isinstance(value, dict)
    properties = {prop.name: prop.schema for prop in schema.properties}
    for required in schema.required_properties:
        if required not in value or value[required] is None:
            raise CapabilityExecutionError(
                ExecutionErrorCode.ARGUMENT_INVALID,
                f"required argument is missing: {path}.{required}",
            )
    for name, item in value.items():
        child_schema = properties.get(name)
        if child_schema is None:
            raise CapabilityExecutionError(
                ExecutionErrorCode.ARGUMENT_INVALID,
                f"argument contains an undeclared field: {path}.{name}",
            )
        _validate_value(f"{path}.{name}", item, child_schema)


def _matches_kind(value: JsonValue, kind: JsonKind) -> bool:
    if kind is JsonKind.STRING:
        return type(value) is str
    if kind is JsonKind.BOOLEAN:
        return type(value) is bool
    if kind is JsonKind.INTEGER:
        return _is_integer(value)
    if kind is JsonKind.NUMBER:
        return _is_number(value)
    if kind is JsonKind.ARRAY:
        return isinstance(value, list)
    return isinstance(value, dict)


def _is_number(value: JsonValue) -> bool:
    if type(value) is int:
        return True
    return type(value) is float and math.isfinite(value)


def _is_integer(value: JsonValue) -> bool:
    if type(value) is int:
        return True
    return type(value) is float and math.isfinite(value) and value.is_integer()


def _normalize_value(value: JsonValue, schema: ValueSchema) -> JsonValue:
    if value is None:
        return None
    if schema.kind is JsonKind.INTEGER:
        assert isinstance(value, (int, float))
        return int(value)
    if schema.kind is JsonKind.ARRAY:
        assert schema.items is not None
        assert isinstance(value, list)
        return [_normalize_value(item, schema.items) for item in value]
    if schema.kind is JsonKind.OBJECT:
        assert isinstance(value, dict)
        properties = {prop.name: prop.schema for prop in schema.properties}
        return {name: _normalize_value(item, properties[name]) for name, item in value.items()}
    return value


def _validate_allowed_value(
    name: str, value: JsonValue, definition: ArgumentDefinition
) -> None:
    if value is None or not definition.allowed_values:
        return
    if any(
        _typed_values_equal(value, allowed, definition.schema.kind)
        for allowed in definition.allowed_values
    ):
        return
    raise CapabilityExecutionError(
        ExecutionErrorCode.ARGUMENT_INVALID,
        f"argument value is outside the published allowed values: {name}",
    )


def _typed_values_equal(left: JsonValue, right: JsonValue, kind: JsonKind) -> bool:
    if kind in {JsonKind.NUMBER, JsonKind.INTEGER}:
        if not _is_number(left) or not _is_number(right):
            return False
        return Decimal(str(left)) == Decimal(str(right))
    return type(left) is type(right) and left == right


def _context_value(mapping: ContextMapping, context: TrustedContext) -> JsonValue:
    if mapping.context_field is ContextField.USER_ID:
        value = str(context.user_id)
    elif mapping.context_field is ContextField.CLIENT:
        value = context.client
    else:
        value = context.environment.value
    if not mapping.value_mappings:
        return value
    translated = {
        item.source_value: item.target_value for item in mapping.value_mappings
    }.get(value)
    if translated is None:
        raise CapabilityExecutionError(
            ExecutionErrorCode.REQUEST_MAPPING_INVALID,
            f"system variable value mapping is missing: {mapping.context_field.value}",
        )
    return translated


def _put_path(target: JsonObject, path: str, value: JsonValue) -> None:
    segments = path.split(".")
    current = target
    for segment in segments[:-1]:
        child = current.get(segment)
        if child is None:
            next_object: JsonObject = {}
            current[segment] = next_object
            current = next_object
            continue
        if not isinstance(child, dict):
            raise CapabilityExecutionError(
                ExecutionErrorCode.REQUEST_MAPPING_INVALID,
                "request mapping path conflicts with a scalar field",
            )
        current = child
    leaf = segments[-1]
    if leaf in current:
        raise CapabilityExecutionError(
            ExecutionErrorCode.REQUEST_MAPPING_INVALID,
            "request mapping writes the same target more than once",
        )
    current[leaf] = _clone_json(value)


def _clone_json(value: JsonValue) -> JsonValue:
    if isinstance(value, list):
        return [_clone_json(item) for item in value]
    if isinstance(value, dict):
        return {name: _clone_json(item) for name, item in value.items()}
    return value
