from __future__ import annotations

from collections.abc import Callable

import pytest

from a2flow_capability.bindings import bind_request
from a2flow_capability.models import (
    ArgumentDefinition,
    CapabilityExecutionError,
    ConstantMapping,
    ContextField,
    ContextMapping,
    ContextValueMapping,
    Environment,
    ExecutionErrorCode,
    JsonKind,
    JsonObject,
    ObjectProperty,
    PublishedPlan,
    RequestMapping,
    TrustedContext,
    ValueSchema,
)


def make_plan(
    *,
    arguments: tuple[ArgumentDefinition, ...],
    request_mappings: tuple[RequestMapping, ...] = (),
    context_mappings: tuple[ContextMapping, ...] = (),
    constant_mappings: tuple[ConstantMapping, ...] = (),
) -> PublishedPlan:
    return PublishedPlan(
        source_id="source-1",
        source_digest="sha256:abc",
        resolved_environment=Environment.PRT,
        action_code="query_order",
        capability_version=1,
        client_type="PC",
        target_key="orderService",
        service_name="example.OrderService",
        method_name="Query",
        descriptor_set_base64="ZGVzY3JpcHRvcg==",
        context_field="context",
        timeout_ms=3_000,
        max_response_bytes=1_048_576,
        technical_output_schema={"type": "object"},
        arguments=arguments,
        request_mappings=request_mappings,
        context_mappings=context_mappings,
        constant_mappings=constant_mappings,
    )


def context() -> TrustedContext:
    return TrustedContext(
        user_id=-9,
        environment=Environment.PRT,
        request_id="request-1",
        client="PC",
    )


def assert_error(code: ExecutionErrorCode, operation: Callable[[], object]) -> None:
    with pytest.raises(CapabilityExecutionError) as captured:
        operation()
    assert captured.value.code is code


def test_binds_nested_arguments_context_and_constants_without_mutating_input() -> None:
    item_schema = ValueSchema(
        JsonKind.OBJECT,
        properties=(
            ObjectProperty("sku", ValueSchema(JsonKind.STRING)),
            ObjectProperty("quantity", ValueSchema(JsonKind.INTEGER)),
        ),
        required_properties=frozenset({"sku", "quantity"}),
    )
    plan = make_plan(
        arguments=(
            ArgumentDefinition(
                "items", ValueSchema(JsonKind.ARRAY, items=item_schema), required=True
            ),
            ArgumentDefinition(
                "mode",
                ValueSchema(JsonKind.STRING),
                allowed_values=("FAST", "SAFE"),
            ),
        ),
        request_mappings=(
            RequestMapping("items", "order.items"),
            RequestMapping("mode", "order.mode"),
        ),
        context_mappings=(
            ContextMapping("owner.userId", ContextField.USER_ID),
            ContextMapping(
                "routing.environment",
                ContextField.ENVIRONMENT,
                (ContextValueMapping("PRT", "pre"), ContextValueMapping("ONLINE", "prod")),
            ),
        ),
        constant_mappings=(ConstantMapping("metadata.origin", "A2FLOW"),),
    )
    arguments: JsonObject = {
        "items": [{"sku": "sku-1", "quantity": 2.0}],
        "mode": "FAST",
    }

    effective, request = bind_request(plan, arguments, context())

    assert effective == {"items": [{"sku": "sku-1", "quantity": 2}], "mode": "FAST"}
    assert request == {
        "order": {"items": [{"sku": "sku-1", "quantity": 2}], "mode": "FAST"},
        "owner": {"userId": "-9"},
        "routing": {"environment": "pre"},
        "metadata": {"origin": "A2FLOW"},
    }
    assert arguments["items"] == [{"sku": "sku-1", "quantity": 2.0}]


@pytest.mark.parametrize("field", ["url", "Authorization", "token", "extra"])
def test_rejects_undeclared_or_forbidden_top_level_argument(field: str) -> None:
    plan = make_plan(arguments=(ArgumentDefinition("url", ValueSchema(JsonKind.STRING)),))
    assert_error(
        ExecutionErrorCode.ARGUMENT_INVALID,
        lambda: bind_request(plan, {field: "untrusted"}, context()),
    )


def test_rejects_missing_required_and_nested_undeclared_fields() -> None:
    profile = ValueSchema(
        JsonKind.OBJECT,
        properties=(ObjectProperty("name", ValueSchema(JsonKind.STRING)),),
        required_properties=frozenset({"name"}),
    )
    plan = make_plan(arguments=(ArgumentDefinition("profile", profile, required=True),))

    assert_error(
        ExecutionErrorCode.ARGUMENT_INVALID,
        lambda: bind_request(plan, {}, context()),
    )
    assert_error(
        ExecutionErrorCode.ARGUMENT_INVALID,
        lambda: bind_request(plan, {"profile": {"name": "n", "role": "admin"}}, context()),
    )


def test_rejects_boolean_as_number_and_non_finite_number() -> None:
    plan = make_plan(arguments=(ArgumentDefinition("amount", ValueSchema(JsonKind.NUMBER)),))
    assert_error(
        ExecutionErrorCode.ARGUMENT_TYPE_MISMATCH,
        lambda: bind_request(plan, {"amount": True}, context()),
    )
    assert_error(
        ExecutionErrorCode.ARGUMENT_TYPE_MISMATCH,
        lambda: bind_request(plan, {"amount": float("nan")}, context()),
    )


def test_numeric_allowed_values_use_exact_decimal_comparison() -> None:
    large = 9_007_199_254_740_993
    plan = make_plan(
        arguments=(
            ArgumentDefinition(
                "identifier", ValueSchema(JsonKind.INTEGER), allowed_values=(large,)
            ),
        )
    )
    effective, _ = bind_request(plan, {"identifier": large}, context())
    assert effective == {"identifier": large}
    assert_error(
        ExecutionErrorCode.ARGUMENT_INVALID,
        lambda: bind_request(plan, {"identifier": large + 1}, context()),
    )


def test_context_value_mapping_must_cover_trusted_value() -> None:
    plan = make_plan(
        arguments=(),
        context_mappings=(
            ContextMapping(
                "caller.client",
                ContextField.CLIENT,
                (ContextValueMapping("APP", "mobile"),),
            ),
        ),
    )
    assert_error(
        ExecutionErrorCode.REQUEST_MAPPING_INVALID,
        lambda: bind_request(plan, {}, context()),
    )


def test_plan_rejects_duplicate_and_prefix_conflicting_writes() -> None:
    with pytest.raises(ValueError, match="same target"):
        make_plan(
            arguments=(ArgumentDefinition("name", ValueSchema(JsonKind.STRING)),),
            request_mappings=(RequestMapping("name", "payload.value"),),
            constant_mappings=(ConstantMapping("payload.value", "fixed"),),
        )

    plan = make_plan(
        arguments=(ArgumentDefinition("name", ValueSchema(JsonKind.STRING)),),
        request_mappings=(RequestMapping("name", "payload"),),
        constant_mappings=(ConstantMapping("payload.value", "fixed"),),
    )
    assert_error(
        ExecutionErrorCode.REQUEST_MAPPING_INVALID,
        lambda: bind_request(plan, {"name": "scalar"}, context()),
    )


def test_null_mapping_cannot_be_replaced_by_a_nested_mapping() -> None:
    plan = make_plan(
        arguments=(ArgumentDefinition("optional", ValueSchema(JsonKind.STRING)),),
        request_mappings=(RequestMapping("optional", "payload"),),
        constant_mappings=(ConstantMapping("payload.value", "fixed"),),
    )

    assert_error(
        ExecutionErrorCode.REQUEST_MAPPING_INVALID,
        lambda: bind_request(plan, {"optional": None}, context()),
    )
