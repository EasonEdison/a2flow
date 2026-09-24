from __future__ import annotations

import json
from copy import deepcopy
from typing import cast

import pytest

from a2flow_capability.compiler import (
    CapabilityCompileError,
    CompiledCapability,
    compile_capability,
)
from a2flow_capability.models import (
    ContextField,
    Environment,
    JsonKind,
    JsonObject,
    JsonValue,
)


def _binding(
    request_mappings: dict[str, str],
    context_mappings: dict[str, str],
    *,
    target_key: str = "business",
) -> JsonObject:
    return {
        "bindingType": "GRPC",
        "target": {
            "targetKey": target_key,
            "serviceName": "probe.Business",
            "methodName": "Invoke",
            "descriptorSetBase64": "ZGVzY3JpcHRvcg==",
            "contextField": "context",
        },
        "requestMappingsJson": json.dumps(request_mappings, separators=(",", ":")),
        "contextMappingsJson": json.dumps(context_mappings, separators=(",", ":")),
        "timeoutMs": 3_000,
        "maxResponseBytes": 1_048_576,
        "idempotency": "NONE",
        "responsePolicy": "ORIGINAL",
    }


def _variant(*, target_key: str = "business") -> JsonObject:
    input_fields: list[JsonObject] = [
        {
            "toolField": "quantity",
            "type": "integer",
            "source": "MODEL_INPUT",
            "businessMeaning": "活动数量",
            "unit": "个",
            "required": True,
            "examples": "2",
            "allowedValues": [
                {"value": 1, "label": "一个"},
                {"value": 2.0, "label": "两个"},
            ],
        },
        {
            "toolField": "items",
            "type": "array",
            "source": "MODEL_INPUT",
            "required": False,
            "items": {
                "type": "object",
                "properties": {
                    "sku": {"type": "string"},
                    "count": {"type": "integer"},
                },
                "required": ["sku", "count"],
            },
        },
        {
            "toolField": "confirmed",
            "type": "boolean",
            "source": "CONSTANT",
            "constantValue": True,
        },
        {
            "toolField": "owner",
            "type": "string",
            "source": "SYSTEM_VARIABLE",
            "systemVariable": "userId",
        },
        {
            "toolField": "callingClient",
            "type": "string",
            "source": "SYSTEM_VARIABLE",
            "systemVariable": "client",
            "valueMapping": {"PC": "desktop", "APP": "mobile"},
        },
    ]
    request_mappings = {
        "quantity": "request.quantity",
        "items": "request.items",
        "confirmed": "request.confirmed",
        "owner": "owner.userId",
        "callingClient": "caller.clientType",
    }
    context_mappings = {
        "owner.userId": "userId",
        "caller.clientType": "client",
    }
    return {
        "apiSource": {"sourceType": "GRPC"},
        "modelContract": {
            "description": "调用真实探针",
            "inputFields": cast(JsonValue, input_fields),
            "inputExampleJson": '{"quantity":2}',
        },
        "executionBinding": _binding(
            request_mappings,
            context_mappings,
            target_key=target_key,
        ),
        "resultContract": {
            "keyOutputFields": [
                {"path": "quantity", "description": "确认数量", "observedType": "integer"},
                {"ignored": "not published metadata"},
                "not-an-object",
            ],
            "responseDemoJson": '{"quantity":2}',
            "technicalOutputSchema": json.dumps(
                {
                    "type": "object",
                    "properties": {"quantity": {"type": "integer"}},
                    "required": ["quantity"],
                },
                separators=(",", ":"),
            ),
        },
    }


def _payload(
    supported: list[str] | None = None,
    variants: dict[str, JsonObject] | None = None,
) -> JsonObject:
    clients = supported or ["PC"]
    client_variants = variants or {"PC": _variant()}
    return {
        "draftId": "capability-1001",
        "revision": 9,
        "status": "PUBLISHED",
        "draft": {
            "payloadType": "CAPABILITY_DRAFT_SNAPSHOT",
            "mode": "UPDATE",
            "basicInfo": {
                "actionCode": "probe.invoke",
                "nameCn": "确认合成活动",
                "description": "公共说明",
            },
            "governance": {
                "enabled": True,
                "emergencyDisabled": False,
                "sideEffectLevel": "READ",
                "approvalPolicy": "REQUEST",
            },
            "supportedClients": cast(JsonValue, clients),
            "clientVariants": cast(JsonValue, client_variants),
        },
        "validationStatus": "VALID",
        "published": True,
        "publishedVersion": 3,
    }


def _compile(payload: JsonObject, *, client: str = "PC") -> CompiledCapability:
    return compile_capability(
        payload,
        source_id="prt-build-17",
        source_digest="sha256:release",
        environment=Environment.PRT,
        version=3,
        client=client,
    )


def test_compiles_real_capability_action_draft_payload() -> None:
    compiled = _compile(_payload())

    plan = compiled.plan
    assert plan.source_id == "prt-build-17"
    assert plan.source_digest == "sha256:release"
    assert plan.action_code == "probe.invoke"
    assert plan.capability_version == 3
    assert plan.target_key == "business"
    assert plan.client_type == "PC"
    assert compiled.description == "调用真实探针"
    assert compiled.key_output_fields == [
        {"path": "quantity", "description": "确认数量", "observedType": "integer"}
    ]

    assert tuple(argument.name for argument in plan.arguments) == ("quantity", "items")
    quantity, items = plan.arguments
    assert quantity.required is True
    assert quantity.allowed_values == (1, 2.0)
    assert type(quantity.allowed_values[1]) is float
    assert items.schema.kind is JsonKind.ARRAY
    assert items.schema.items is not None
    assert items.schema.items.kind is JsonKind.OBJECT
    assert items.schema.items.required_properties == frozenset({"sku", "count"})
    assert compiled.input_schema["required"] == ["quantity"]
    assert compiled.input_schema["additionalProperties"] is False
    properties = compiled.input_schema["properties"]
    assert isinstance(properties, dict)
    assert set(properties) == {"quantity", "items"}

    assert [(item.argument_name, item.request_path) for item in plan.request_mappings] == [
        ("quantity", "request.quantity"),
        ("items", "request.items"),
    ]
    assert [(item.request_path, item.value) for item in plan.constant_mappings] == [
        ("request.confirmed", True)
    ]
    assert [item.context_field for item in plan.context_mappings] == [
        ContextField.USER_ID,
        ContextField.CLIENT,
    ]
    assert plan.context_mappings[1].value_mappings[1].target_value == "mobile"
    assert plan.technical_output_schema["required"] == ["quantity"]


def test_common_variant_is_selected_but_actual_runtime_client_is_preserved() -> None:
    payload = _payload(["COMMON"], {"COMMON": _variant(target_key="commonBusiness")})

    compiled = _compile(payload, client=" app ")

    assert compiled.plan.client_type == "APP"
    assert compiled.plan.target_key == "commonBusiness"
    assert compiled.plan.context_mappings[1].value_mappings[1].source_value == "APP"


def test_specific_client_variants_do_not_fallback_across_clients() -> None:
    payload = _payload(
        ["PC", "APP"],
        {"PC": _variant(target_key="pcTarget"), "APP": _variant(target_key="appTarget")},
    )
    assert _compile(payload, client="APP").plan.target_key == "appTarget"

    pc_only = _payload(["PC"], {"PC": _variant()})
    with pytest.raises(CapabilityCompileError, match="CAPABILITY_CLIENT_NOT_SUPPORTED"):
        _compile(pc_only, client="APP")


@pytest.mark.parametrize(
    "mutation",
    [
        "status",
        "governance_enabled",
        "governance_emergency",
    ],
)
def test_disabled_published_payload_is_rejected(mutation: str) -> None:
    payload = _payload()
    draft = payload["draft"]
    assert isinstance(draft, dict)
    governance = draft["governance"]
    assert isinstance(governance, dict)
    if mutation == "status":
        payload["status"] = "DISABLED"
    elif mutation == "governance_enabled":
        governance["enabled"] = False
    else:
        governance["emergencyDisabled"] = True
    with pytest.raises(CapabilityCompileError, match="disabled"):
        _compile(payload)


def test_client_variant_keys_must_exactly_match_canonical_supported_clients() -> None:
    payload = _payload(["PC", "APP"], {"APP": _variant(), "PC": _variant()})
    with pytest.raises(CapabilityCompileError, match="do not match"):
        _compile(payload)

    unsupported = _payload(["APP", "PC"], {"APP": _variant(), "PC": _variant()})
    with pytest.raises(CapabilityCompileError, match="canonical"):
        _compile(unsupported)


def test_mapping_json_must_cover_all_fields_and_exact_system_variables() -> None:
    payload = _payload()
    binding = _selected_binding(payload)
    binding["requestMappingsJson"] = '{"quantity":"request.quantity"}'
    with pytest.raises(CapabilityCompileError, match="fields mismatch"):
        _compile(payload)

    payload = _payload()
    binding = _selected_binding(payload)
    binding["contextMappingsJson"] = '{"owner.userId":"client"}'
    with pytest.raises(CapabilityCompileError, match="exactly match"):
        _compile(payload)


def test_unknown_http_fields_and_conflicting_target_paths_are_rejected() -> None:
    payload = _payload()
    binding = _selected_binding(payload)
    binding["url"] = "https://model-controlled.invalid"
    with pytest.raises(CapabilityCompileError, match="HTTP execution binding"):
        _compile(payload)

    payload = _payload()
    binding = _selected_binding(payload)
    mappings = json.loads(str(binding["requestMappingsJson"]))
    assert isinstance(mappings, dict)
    mappings["confirmed"] = "request.quantity.child"
    binding["requestMappingsJson"] = json.dumps(mappings)
    with pytest.raises(CapabilityCompileError, match="target paths conflict"):
        _compile(payload)


def test_invalid_nested_schema_allowed_values_and_constants_fail_closed() -> None:
    payload = _payload()
    fields = _selected_fields(payload)
    items = fields[1]["items"]
    assert isinstance(items, dict)
    items["required"] = ["missing"]
    with pytest.raises(CapabilityCompileError, match="unknown property"):
        _compile(payload)

    payload = _payload()
    fields = _selected_fields(payload)
    allowed = fields[0]["allowedValues"]
    assert isinstance(allowed, list)
    allowed.append({"value": 2, "label": "重复"})
    with pytest.raises(CapabilityCompileError, match="duplicated"):
        _compile(payload)

    payload = _payload()
    fields = _selected_fields(payload)
    fields[2]["constantValue"] = "true"
    with pytest.raises(CapabilityCompileError, match="must be boolean"):
        _compile(payload)


def test_top_level_number_constant_accepts_safe_java_form_numeric_string() -> None:
    payload = _payload()
    fields = _selected_fields(payload)
    fields[2]["type"] = "number"
    fields[2]["constantValue"] = "0.1"
    compiled = _compile(payload)
    assert compiled.plan.constant_mappings[0].value == 0.1

    payload = _payload()
    fields = _selected_fields(payload)
    fields[2]["type"] = "number"
    fields[2]["constantValue"] = "0.123456789012345678901"
    with pytest.raises(CapabilityCompileError, match="represented safely"):
        _compile(payload)


def test_binding_defaults_match_java_contract_and_malformed_json_is_rejected() -> None:
    payload = _payload()
    binding = _selected_binding(payload)
    del binding["timeoutMs"]
    del binding["maxResponseBytes"]
    del binding["idempotency"]
    del binding["responsePolicy"]
    compiled = _compile(payload)
    assert compiled.plan.timeout_ms == 3_000
    assert compiled.plan.max_response_bytes == 1_048_576
    assert compiled.plan.idempotency == "NONE"
    assert compiled.plan.response_policy == "ORIGINAL"

    payload = _payload()
    _selected_binding(payload)["requestMappingsJson"] = "[]"
    with pytest.raises(CapabilityCompileError, match="must be an object"):
        _compile(payload)

    payload = _payload()
    result = _selected_result_contract(payload)
    result["technicalOutputSchema"] = "not-json"
    with pytest.raises(CapabilityCompileError, match="valid JSON"):
        _compile(payload)


def test_input_payload_is_not_mutated() -> None:
    payload = _payload()
    before = deepcopy(payload)
    _compile(payload)
    assert payload == before


def _selected_variant(payload: JsonObject) -> JsonObject:
    draft = payload["draft"]
    assert isinstance(draft, dict)
    variants = draft["clientVariants"]
    assert isinstance(variants, dict)
    variant = variants["PC"]
    assert isinstance(variant, dict)
    return variant


def _selected_binding(payload: JsonObject) -> JsonObject:
    binding = _selected_variant(payload)["executionBinding"]
    assert isinstance(binding, dict)
    return binding


def _selected_fields(payload: JsonObject) -> list[JsonObject]:
    contract = _selected_variant(payload)["modelContract"]
    assert isinstance(contract, dict)
    fields = contract["inputFields"]
    assert isinstance(fields, list)
    assert all(isinstance(item, dict) for item in fields)
    return cast(list[JsonObject], fields)


def _selected_result_contract(payload: JsonObject) -> JsonObject:
    result = _selected_variant(payload)["resultContract"]
    assert isinstance(result, dict)
    return result
