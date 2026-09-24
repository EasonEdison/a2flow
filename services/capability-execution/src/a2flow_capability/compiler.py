"""Compile canonical M capability release payloads into typed execution plans."""

from __future__ import annotations

import base64
import binascii
import json
import math
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import cast

from a2flow_capability.models import (
    ArgumentDefinition,
    ConstantMapping,
    ContextField,
    ContextMapping,
    ContextValueMapping,
    Environment,
    JsonKind,
    JsonObject,
    JsonValue,
    ObjectProperty,
    PublishedPlan,
    RequestMapping,
    ValueSchema,
)

_CLIENT_MODES = (("PC",), ("APP",), ("PC", "APP"), ("COMMON",))
_CLIENTS = frozenset({"PC", "APP", "COMMON"})
_ALLOWED_BINDING_FIELDS = frozenset(
    {
        "bindingType",
        "target",
        "timeoutMs",
        "maxResponseBytes",
        "idempotency",
        "responsePolicy",
        "requestMappingsJson",
        "contextMappingsJson",
    }
)
_TARGET_FIELDS = frozenset(
    {"targetKey", "serviceName", "methodName", "descriptorSetBase64", "contextField"}
)
_MAX_DESCRIPTOR_BASE64 = 2_800_000


class CapabilityCompileError(ValueError):
    """The immutable release payload cannot be compiled without guessing."""


@dataclass(frozen=True, slots=True)
class CompiledCapability:
    plan: PublishedPlan
    description: str
    input_schema: JsonObject
    key_output_fields: list[JsonValue]


@dataclass(frozen=True, slots=True)
class _CompiledField:
    name: str
    source: str
    argument: ArgumentDefinition | None
    constant: JsonValue
    system_variable: ContextField | None
    context_values: tuple[ContextValueMapping, ...]
    input_schema: JsonObject | None


def compile_capability(
    payload: JsonObject,
    source_id: str,
    source_digest: str,
    environment: Environment,
    version: int,
    client: str,
) -> CompiledCapability:
    """Compile a serialized ``CapabilityActionDraft`` release snapshot."""
    root = _object(_required(payload, "draft", "payload"), "payload.draft")
    _validate_enabled(payload, root)
    basic = _object(_required(root, "basicInfo", "payload.draft"), "basicInfo")
    actual_client = _client(client)
    variant = _select_variant(root, actual_client)
    api_source = _object(_required(variant, "apiSource", "client variant"), "apiSource")
    model_contract = _object(
        _required(variant, "modelContract", "client variant"), "modelContract"
    )
    binding = _object(
        _required(variant, "executionBinding", "client variant"), "executionBinding"
    )
    result_contract = _object(
        _required(variant, "resultContract", "client variant"), "resultContract"
    )
    if _required_string(api_source, "sourceType", "apiSource") != "GRPC":
        raise CapabilityCompileError("only GRPC apiSource.sourceType is supported")
    _validate_binding_shape(binding)

    fields = _compile_fields(model_contract.get("inputFields"))
    field_names = tuple(field.name for field in fields)
    if len(field_names) != len(set(field_names)):
        raise CapabilityCompileError("modelContract.inputFields contains duplicate toolField")
    all_mappings = _json_string_map(
        binding.get("requestMappingsJson"), "executionBinding.requestMappingsJson"
    )
    if set(all_mappings) != set(field_names):
        missing = sorted(set(field_names) - set(all_mappings))
        extra = sorted(set(all_mappings) - set(field_names))
        raise CapabilityCompileError(
            f"requestMappingsJson fields mismatch; missing={missing}, extra={extra}"
        )
    context_mapping_values = _json_string_map(
        binding.get("contextMappingsJson"), "executionBinding.contextMappingsJson"
    )
    expected_context = {
        all_mappings[field.name]: field.system_variable.value
        for field in fields
        if field.system_variable is not None
    }
    if context_mapping_values != expected_context:
        raise CapabilityCompileError(
            "contextMappingsJson must exactly match declared SYSTEM_VARIABLE fields"
        )

    request_mappings = tuple(
        RequestMapping(field.name, all_mappings[field.name])
        for field in fields
        if field.source == "MODEL_INPUT"
    )
    context_mappings = tuple(
        ContextMapping(
            all_mappings[field.name],
            cast(ContextField, field.system_variable),
            field.context_values,
        )
        for field in fields
        if field.source == "SYSTEM_VARIABLE"
    )
    constant_mappings = tuple(
        ConstantMapping(all_mappings[field.name], field.constant)
        for field in fields
        if field.source == "CONSTANT"
    )
    _validate_target_paths(
        tuple(item.request_path for item in request_mappings)
        + tuple(item.request_path for item in context_mappings)
        + tuple(item.request_path for item in constant_mappings)
    )

    target = _object(_required(binding, "target", "executionBinding"), "executionBinding.target")
    descriptor = _required_string(target, "descriptorSetBase64", "executionBinding.target")
    _validate_descriptor_encoding(descriptor)
    technical_schema = _json_object(
        _required_string(result_contract, "technicalOutputSchema", "resultContract"),
        "resultContract.technicalOutputSchema",
    )
    timeout_ms = _bounded_integer(binding.get("timeoutMs"), 3_000, 120_000, "timeoutMs")
    max_response_bytes = _bounded_integer(
        binding.get("maxResponseBytes"), 1_048_576, 5_242_880, "maxResponseBytes"
    )
    idempotency = _optional_string(binding.get("idempotency"), "NONE")
    response_policy = _optional_string(binding.get("responsePolicy"), "ORIGINAL")
    if idempotency != "NONE":
        raise CapabilityCompileError("only NONE idempotency is supported")
    if response_policy != "ORIGINAL":
        raise CapabilityCompileError("only ORIGINAL responsePolicy is supported")

    input_schema = _top_level_input_schema(fields)
    description = _first_nonblank(model_contract.get("description"), basic.get("description"))
    key_output_fields = _key_output_fields(result_contract.get("keyOutputFields"))
    try:
        plan = PublishedPlan(
            source_id=source_id,
            source_digest=source_digest,
            resolved_environment=environment,
            action_code=_required_string(basic, "actionCode", "basicInfo"),
            capability_version=version,
            client_type=actual_client,
            target_key=_required_string(target, "targetKey", "executionBinding.target"),
            service_name=_required_string(target, "serviceName", "executionBinding.target"),
            method_name=_required_string(target, "methodName", "executionBinding.target"),
            descriptor_set_base64=descriptor,
            context_field=_required_string(target, "contextField", "executionBinding.target"),
            timeout_ms=timeout_ms,
            max_response_bytes=max_response_bytes,
            technical_output_schema=technical_schema,
            arguments=tuple(
                field.argument
                for field in fields
                if field.argument is not None
            ),
            request_mappings=request_mappings,
            context_mappings=context_mappings,
            constant_mappings=constant_mappings,
            source_type="GRPC",
            binding_type="GRPC",
            idempotency=idempotency,
            response_policy=response_policy,
        )
    except ValueError as error:
        raise CapabilityCompileError(str(error)) from error
    return CompiledCapability(plan, description, input_schema, key_output_fields)


def _validate_enabled(payload: JsonObject, root: JsonObject) -> None:
    governance = _optional_object(root.get("governance"), "governance")
    if (
        governance.get("enabled") is False
        or governance.get("emergencyDisabled") is True
        or str(payload.get("status", "")).upper() == "DISABLED"
    ):
        raise CapabilityCompileError("published capability is disabled")


def _client(value: str) -> str:
    if type(value) is not str:
        raise CapabilityCompileError("client is required")
    normalized = value.strip().upper()
    if normalized not in _CLIENTS:
        raise CapabilityCompileError("client must be PC, APP or COMMON")
    return normalized


def _select_variant(root: JsonObject, client: str) -> JsonObject:
    raw_supported = root.get("supportedClients")
    if not isinstance(raw_supported, list) or any(type(item) is not str for item in raw_supported):
        raise CapabilityCompileError("supportedClients is invalid")
    supported = tuple(cast(str, item) for item in raw_supported)
    if supported not in _CLIENT_MODES:
        raise CapabilityCompileError("supportedClients is not a canonical client mode")
    variants = _object(_required(root, "clientVariants", "payload.draft"), "clientVariants")
    if tuple(variants) != supported:
        raise CapabilityCompileError("supportedClients and clientVariants do not match")
    contract_client = "COMMON" if supported == ("COMMON",) else client
    if supported != ("COMMON",) and client not in supported:
        raise CapabilityCompileError(f"CAPABILITY_CLIENT_NOT_SUPPORTED: {client}")
    selected = variants.get(contract_client)
    if not isinstance(selected, dict):
        raise CapabilityCompileError(f"CAPABILITY_CLIENT_NOT_SUPPORTED: {client}")
    return selected


def _validate_binding_shape(binding: JsonObject) -> None:
    if binding.get("bindingType") != "GRPC":
        raise CapabilityCompileError("only GRPC executionBinding.bindingType is supported")
    unknown = set(binding) - _ALLOWED_BINDING_FIELDS
    if unknown:
        raise CapabilityCompileError(f"unknown or HTTP execution binding fields: {sorted(unknown)}")
    target = _object(_required(binding, "target", "executionBinding"), "executionBinding.target")
    unknown_target = set(target) - _TARGET_FIELDS
    if unknown_target:
        raise CapabilityCompileError(f"unknown or HTTP target fields: {sorted(unknown_target)}")
    for field in _TARGET_FIELDS:
        _required_string(target, field, "executionBinding.target")


def _compile_fields(value: JsonValue | None) -> tuple[_CompiledField, ...]:
    if not isinstance(value, list):
        return ()
    result: list[_CompiledField] = []
    for index, item in enumerate(value):
        field = _object(item, f"modelContract.inputFields[{index}]")
        name = _required_string(field, "toolField", f"inputFields[{index}]")
        source = _required_string(field, "source", f"inputFields[{index}]")
        if source not in {"MODEL_INPUT", "CONSTANT", "SYSTEM_VARIABLE"}:
            raise CapabilityCompileError(f"unsupported input field source: {source}")
        kind = _top_level_kind(field.get("type"), name)
        schema, schema_json = _compile_schema(field, kind, top_level=True)
        if source == "MODEL_INPUT":
            allowed = _allowed_values(field, kind)
            if allowed:
                schema_json["enum"] = list(allowed)
            result.append(
                _CompiledField(
                    name=name,
                    source=source,
                    argument=ArgumentDefinition(
                        name,
                        schema,
                        required=field.get("required") is True,
                        allowed_values=allowed,
                    ),
                    constant=None,
                    system_variable=None,
                    context_values=(),
                    input_schema=schema_json,
                )
            )
        elif source == "CONSTANT":
            if "constantValue" not in field:
                raise CapabilityCompileError(f"constantValue is required for field: {name}")
            raw_constant = field["constantValue"]
            if raw_constant is None or raw_constant == "":
                raise CapabilityCompileError(f"constantValue is required for field: {name}")
            result.append(
                _CompiledField(
                    name,
                    source,
                    None,
                    _normalize_constant(raw_constant, schema, name),
                    None,
                    (),
                    None,
                )
            )
        else:
            system_variable = _system_variable(field, kind, name)
            result.append(
                _CompiledField(
                    name,
                    source,
                    None,
                    None,
                    system_variable,
                    _context_values(field, system_variable),
                    None,
                )
            )
    return tuple(result)


def _top_level_kind(value: JsonValue | None, field: str) -> JsonKind:
    kind = _kind(value, field)
    if kind is JsonKind.OBJECT:
        raise CapabilityCompileError(f"top-level object input is unsupported: {field}")
    return kind


def _kind(value: JsonValue | None, path: str) -> JsonKind:
    if type(value) is not str:
        raise CapabilityCompileError(f"input schema type is required: {path}")
    try:
        return JsonKind(value.lower())
    except ValueError as error:
        raise CapabilityCompileError(f"input schema type is invalid: {path}") from error


def _compile_schema(
    source: JsonObject, kind: JsonKind, *, top_level: bool
) -> tuple[ValueSchema, JsonObject]:
    output: JsonObject = {"type": kind.value}
    description = _field_description(source) if top_level else _string(source.get("description"))
    if description:
        output["description"] = description
    if kind is JsonKind.ARRAY:
        items = _object(_required(source, "items", "array input"), "array input.items")
        item_kind = _kind(items.get("type"), "array input.items")
        item_schema, item_output = _compile_schema(items, item_kind, top_level=False)
        output["items"] = item_output
        return ValueSchema(kind, items=item_schema), output
    if kind is JsonKind.OBJECT:
        properties = _object(source.get("properties", {}), "object input.properties")
        compiled_properties: list[ObjectProperty] = []
        output_properties: JsonObject = {}
        for name, raw_schema in properties.items():
            if not name.strip():
                raise CapabilityCompileError("object input property name is required")
            property_node = _object(raw_schema, f"object property {name}")
            property_kind = _kind(property_node.get("type"), f"object property {name}")
            compiled, compiled_output = _compile_schema(
                property_node, property_kind, top_level=False
            )
            compiled_properties.append(ObjectProperty(name, compiled))
            output_properties[name] = compiled_output
        required = _required_property_names(source.get("required"), set(properties))
        output["properties"] = output_properties
        output["required"] = list(required)
        output["additionalProperties"] = False
        return (
            ValueSchema(
                kind,
                properties=tuple(compiled_properties),
                required_properties=frozenset(required),
            ),
            output,
        )
    return ValueSchema(kind), output


def _required_property_names(value: JsonValue | None, properties: set[str]) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise CapabilityCompileError("object input required must be an array")
    result: list[str] = []
    for item in value:
        if type(item) is not str or not item.strip() or item not in properties:
            raise CapabilityCompileError("object input required contains unknown property")
        if item not in result:
            result.append(item)
    return tuple(result)


def _allowed_values(field: JsonObject, kind: JsonKind) -> tuple[JsonValue, ...]:
    if "allowedValues" not in field:
        return ()
    if kind not in {JsonKind.STRING, JsonKind.NUMBER, JsonKind.INTEGER}:
        raise CapabilityCompileError("allowedValues supports only string, number or integer")
    raw_values = field["allowedValues"]
    if not isinstance(raw_values, list) or not raw_values:
        raise CapabilityCompileError("allowedValues must be a non-empty array")
    result: list[JsonValue] = []
    identities: set[str] = set()
    for index, raw_item in enumerate(raw_values):
        item = _object(raw_item, f"allowedValues[{index}]")
        if not _string(item.get("label")):
            raise CapabilityCompileError("allowedValues item label is required")
        value = item.get("value")
        if not _matches_scalar(value, kind) or (kind is JsonKind.STRING and not _string(value)):
            raise CapabilityCompileError("allowedValues item value has invalid type")
        normalized = value
        identity = _value_identity(normalized, kind)
        if identity in identities:
            raise CapabilityCompileError("allowedValues item is duplicated")
        identities.add(identity)
        result.append(normalized)
    return tuple(result)


def _system_variable(field: JsonObject, kind: JsonKind, name: str) -> ContextField:
    if kind is not JsonKind.STRING:
        raise CapabilityCompileError(f"system variable field must be string: {name}")
    value = _required_string(field, "systemVariable", f"input field {name}")
    if value == "userId":
        return ContextField.USER_ID
    if value == "client":
        return ContextField.CLIENT
    raise CapabilityCompileError(f"unsupported systemVariable: {value}")


def _context_values(
    field: JsonObject, system_variable: ContextField
) -> tuple[ContextValueMapping, ...]:
    if "valueMapping" not in field or field["valueMapping"] is None:
        return ()
    if system_variable is ContextField.USER_ID:
        if field["valueMapping"] != {}:
            raise CapabilityCompileError("userId does not support valueMapping")
        return ()
    mapping = _plain_string_map(field["valueMapping"], "valueMapping")
    return tuple(ContextValueMapping(source, target) for source, target in mapping.items())


def _normalize_constant(value: JsonValue, schema: ValueSchema, path: str) -> JsonValue:
    kind = schema.kind
    if kind is JsonKind.STRING:
        if type(value) is not str:
            raise CapabilityCompileError(f"constantValue must be string: {path}")
        return value
    if kind is JsonKind.BOOLEAN:
        if type(value) is not bool:
            raise CapabilityCompileError(f"constantValue must be boolean: {path}")
        return value
    if kind is JsonKind.INTEGER:
        if not _matches_scalar(value, kind):
            raise CapabilityCompileError(f"constantValue must be integer: {path}")
        return int(cast(int | float, value))
    if kind is JsonKind.NUMBER:
        if type(value) is str:
            try:
                decimal_value = Decimal(value)
                parsed = float(decimal_value)
            except (InvalidOperation, ValueError, OverflowError) as error:
                raise CapabilityCompileError(
                    f"constantValue must be JSON number: {path}"
                ) from error
            if not math.isfinite(parsed) or Decimal(str(parsed)) != decimal_value:
                raise CapabilityCompileError(
                    f"constantValue numeric string cannot be represented safely: {path}"
                )
            return parsed
        if not _matches_scalar(value, kind):
            raise CapabilityCompileError(f"constantValue must be JSON number: {path}")
        return value
    if kind is JsonKind.ARRAY:
        if not isinstance(value, list):
            raise CapabilityCompileError(f"constantValue must be array: {path}")
        assert schema.items is not None
        return [
            _normalize_constant(item, schema.items, f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    if not isinstance(value, dict):
        raise CapabilityCompileError(f"constantValue must be object: {path}")
    properties = {prop.name: prop.schema for prop in schema.properties}
    for required in schema.required_properties:
        if required not in value or value[required] is None:
            raise CapabilityCompileError(
                f"constantValue is missing required property: {path}.{required}"
            )
    result: JsonObject = {}
    for name, item in value.items():
        child = properties.get(name)
        if child is None:
            raise CapabilityCompileError(f"constantValue contains unknown property: {path}.{name}")
        result[name] = _normalize_constant(item, child, f"{path}.{name}")
    return result


def _matches_scalar(value: JsonValue | None, kind: JsonKind) -> bool:
    if kind is JsonKind.STRING:
        return type(value) is str
    if kind is JsonKind.INTEGER:
        return type(value) is int or (
            type(value) is float and math.isfinite(value) and value.is_integer()
        )
    if kind is JsonKind.NUMBER:
        return type(value) is int or (type(value) is float and math.isfinite(value))
    return False


def _value_identity(value: JsonValue, kind: JsonKind) -> str:
    if kind in {JsonKind.INTEGER, JsonKind.NUMBER}:
        try:
            return "number:" + str(Decimal(str(value)).normalize())
        except InvalidOperation as error:
            raise CapabilityCompileError("allowed numeric value is invalid") from error
    return f"string:{value}"


def _top_level_input_schema(fields: tuple[_CompiledField, ...]) -> JsonObject:
    properties: JsonObject = {}
    required: list[JsonValue] = []
    for field in fields:
        if field.argument is None or field.input_schema is None:
            continue
        properties[field.name] = field.input_schema
        if field.argument.required:
            required.append(field.name)
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _field_description(field: JsonObject) -> str:
    parts: list[str] = []
    meaning = _string(field.get("businessMeaning"))
    if meaning:
        parts.append(meaning)
    unit = _string(field.get("unit"))
    if unit:
        parts.append(f"单位：{unit}")  # noqa: RUF001
    if "allowedValues" in field and isinstance(field["allowedValues"], list):
        labels: list[str] = []
        for raw in field["allowedValues"]:
            if isinstance(raw, dict):
                item = raw
                labels.append(
                    f"{item.get('value')}（{_string(item.get('label'))}）"  # noqa: RUF001
                )
        if labels:
            parts.append("可选值：" + "、".join(labels))  # noqa: RUF001
    examples = _string(field.get("examples"))
    if examples:
        parts.append(f"示例：{examples}")  # noqa: RUF001
    return "；".join(parts)  # noqa: RUF001


def _key_output_fields(value: JsonValue | None) -> list[JsonValue]:
    if not isinstance(value, list):
        return []
    result: list[JsonValue] = []
    for raw in value:
        if not isinstance(raw, dict):
            continue
        source = raw
        item: JsonObject = {}
        for key in ("path", "description", "observedType"):
            if key in source and source[key] is not None and str(source[key]).strip():
                item[key] = source[key]
        if item:
            result.append(item)
    return result


def _validate_target_paths(paths: tuple[str, ...]) -> None:
    for index, current in enumerate(paths):
        for other in paths[index + 1 :]:
            if (
                current == other
                or current.startswith(other + ".")
                or other.startswith(current + ".")
            ):
                raise CapabilityCompileError(
                    f"request mapping target paths conflict: {current} and {other}"
                )


def _validate_descriptor_encoding(value: str) -> None:
    if len(value) > _MAX_DESCRIPTOR_BASE64:
        raise CapabilityCompileError("descriptorSetBase64 exceeds limit")
    try:
        base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as error:
        raise CapabilityCompileError("descriptorSetBase64 is invalid base64") from error


def _bounded_integer(value: JsonValue | None, default: int, maximum: int, name: str) -> int:
    if value is None or value == "":
        return default
    if type(value) is bool:
        raise CapabilityCompileError(f"{name} must be an exact positive integer")
    try:
        parsed = Decimal(str(value))
        integral = int(parsed)
    except (InvalidOperation, ValueError, OverflowError) as error:
        raise CapabilityCompileError(f"{name} must be an exact positive integer") from error
    if parsed != integral or not 1 <= integral <= maximum:
        raise CapabilityCompileError(f"{name} must be in range 1..{maximum}")
    return integral


def _json_string_map(value: JsonValue | None, path: str) -> dict[str, str]:
    if value is None or value == "":
        return {}
    if type(value) is not str:
        raise CapabilityCompileError(f"{path} must be a JSON object string")
    try:
        decoded: object = json.loads(value)
    except (TypeError, json.JSONDecodeError) as error:
        raise CapabilityCompileError(f"{path} must contain valid JSON") from error
    return _plain_string_map(decoded, path)


def _plain_string_map(value: object, path: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise CapabilityCompileError(f"{path} must be an object")
    result: dict[str, str] = {}
    for key, item in value.items():
        if type(key) is not str or not key.strip() or type(item) is not str or not item.strip():
            raise CapabilityCompileError(f"{path} must contain non-blank string pairs")
        result[key] = item
    return result


def _json_object(value: str, path: str) -> JsonObject:
    try:
        decoded: object = json.loads(value)
    except (TypeError, json.JSONDecodeError) as error:
        raise CapabilityCompileError(f"{path} must contain valid JSON") from error
    return _object(decoded, path)


def _object(value: object, path: str) -> JsonObject:
    if not isinstance(value, dict) or any(type(key) is not str for key in value):
        raise CapabilityCompileError(f"{path} must be an object")
    return cast(JsonObject, value)


def _optional_object(value: JsonValue | None, path: str) -> JsonObject:
    if value is None:
        return {}
    return _object(value, path)


def _required(source: JsonObject, field: str, path: str) -> JsonValue:
    if field not in source:
        raise CapabilityCompileError(f"{path}.{field} is required")
    return source[field]


def _required_string(source: JsonObject, field: str, path: str) -> str:
    value = _required(source, field, path)
    if type(value) is not str or not value.strip():
        raise CapabilityCompileError(f"{path}.{field} is required")
    return value.strip()


def _optional_string(value: JsonValue | None, default: str) -> str:
    if value is None or (type(value) is str and not value.strip()):
        return default
    if type(value) is not str:
        raise CapabilityCompileError("execution policy must be a string")
    return value


def _string(value: JsonValue | None) -> str:
    return value.strip() if type(value) is str else ""


def _first_nonblank(primary: JsonValue | None, fallback: JsonValue | None) -> str:
    return _string(primary) or _string(fallback)
