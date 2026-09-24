from __future__ import annotations

from dataclasses import replace

from a2flow_capability.executor import CapabilityExecutor
from a2flow_capability.models import (
    ArgumentDefinition,
    CapabilityTransportError,
    Environment,
    ExecutionErrorCode,
    JsonKind,
    JsonObject,
    JsonValue,
    PublishedPlan,
    RequestMapping,
    TrustedContext,
    ValueSchema,
)


class RecordingTransport:
    def __init__(self, response: JsonValue) -> None:
        self.response = response
        self.calls: list[tuple[PublishedPlan, JsonObject, TrustedContext]] = []

    def execute(
        self, plan: PublishedPlan, business: JsonObject, context: TrustedContext
    ) -> JsonValue:
        self.calls.append((plan, business, context))
        return self.response


class FailingTransport:
    def __init__(self, failure: Exception) -> None:
        self.failure = failure

    def execute(
        self, plan: PublishedPlan, business: JsonObject, context: TrustedContext
    ) -> JsonValue:
        del plan, business, context
        raise self.failure


def plan() -> PublishedPlan:
    return PublishedPlan(
        source_id="source-1",
        source_digest="sha256:abc",
        resolved_environment=Environment.PRT,
        action_code="query_order",
        capability_version=7,
        client_type="PC",
        target_key="orderService",
        service_name="example.OrderService",
        method_name="Query",
        descriptor_set_base64="ZGVzY3JpcHRvcg==",
        context_field="context",
        timeout_ms=3_000,
        max_response_bytes=1_048_576,
        technical_output_schema={"type": "object"},
        arguments=(ArgumentDefinition("orderId", ValueSchema(JsonKind.STRING), True),),
        request_mappings=(RequestMapping("orderId", "query.orderId"),),
    )


def context(
    environment: Environment = Environment.PRT, client: str = "PC"
) -> TrustedContext:
    return TrustedContext(
        user_id=0,
        environment=environment,
        request_id="request-1",
        client=client,
    )


def test_execute_preserves_original_business_response_without_guessing_success() -> None:
    transport = RecordingTransport({"code": 500, "success": False, "payload": {"id": "o1"}})
    executor = CapabilityExecutor(transport)

    result = executor.execute(plan(), {"orderId": "o1"}, context())

    assert result.success is True
    assert result.error_code is None
    assert result.data == {"code": 500, "success": False, "payload": {"id": "o1"}}
    assert transport.calls[0][1] == {"query": {"orderId": "o1"}}


def test_prepare_allows_common_author_preview_but_execute_rejects_it() -> None:
    transport = RecordingTransport({})
    executor = CapabilityExecutor(transport)
    common_plan = replace(plan(), client_type="COMMON")

    preview = executor.prepare(common_plan, {"orderId": "o1"}, context(client="COMMON"))
    result = executor.execute(common_plan, {"orderId": "o1"}, context(client="COMMON"))

    assert preview.business_request == {"query": {"orderId": "o1"}}
    assert result.success is False
    assert result.error_code is ExecutionErrorCode.CAPABILITY_CLIENT_NOT_SUPPORTED
    assert transport.calls == []


def test_environment_and_client_mismatch_fail_before_transport() -> None:
    transport = RecordingTransport({})
    executor = CapabilityExecutor(transport)

    wrong_environment = executor.execute(
        plan(), {"orderId": "o1"}, context(Environment.ONLINE)
    )
    wrong_client = executor.execute(plan(), {"orderId": "o1"}, context(client="APP"))

    assert wrong_environment.error_code is ExecutionErrorCode.RELEASE_ENVIRONMENT_INVALID
    assert wrong_client.error_code is ExecutionErrorCode.CAPABILITY_CLIENT_NOT_SUPPORTED
    assert transport.calls == []


def test_transport_failure_codes_are_preserved_without_request_data() -> None:
    executor = CapabilityExecutor(
        FailingTransport(
            CapabilityTransportError(
                ExecutionErrorCode.RESPONSE_SCHEMA_INVALID,
                "response does not match technical schema",
            )
        )
    )
    result = executor.execute(plan(), {"orderId": "sensitive-order"}, context())

    assert result.success is False
    assert result.error_code is ExecutionErrorCode.RESPONSE_SCHEMA_INVALID
    assert result.message == "response does not match technical schema"
    assert "sensitive-order" not in result.message


def test_unknown_transport_failure_is_sanitized() -> None:
    executor = CapabilityExecutor(FailingTransport(RuntimeError("secret body")))
    result = executor.execute(plan(), {"orderId": "sensitive-order"}, context())

    assert result.success is False
    assert result.error_code is ExecutionErrorCode.TRANSPORT_ERROR
    assert result.message == "gRPC execution failed"
