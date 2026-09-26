from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace

import grpc
import pytest
from a2flow.capability.v1 import capability_pb2 as cap
from a2flow.content.v1 import content_pb2 as content
from a2flow.content.v1 import content_pb2_grpc as content_rpc
from google.protobuf import descriptor_pb2

from a2flow_capability.models import (
    ArgumentDefinition,
    Environment,
    JsonKind,
    JsonObject,
    PublishedPlan,
    RequestMapping,
    TrustedContext,
    ValueSchema,
)
from a2flow_capability.transport import Endpoint, GrpcTransport, TransportError, registered_method


def descriptor() -> str:
    bundle = descriptor_pb2.FileDescriptorSet()
    for item in (cap.DESCRIPTOR, content.DESCRIPTOR):
        bundle.file.add().ParseFromString(item.serialized_pb)
    return base64.b64encode(bundle.SerializeToString()).decode("ascii")


@dataclass(frozen=True)
class Plan:
    target_key: str = "content"
    service_name: str = "a2flow.content.v1.ContentService"
    method_name: str = "CreateProject"
    descriptor_set_base64: str = field(default_factory=descriptor)
    context_field: str = "context"
    timeout_ms: int = 3000
    max_response_bytes: int = 1024 * 1024
    technical_output_schema: JsonObject = field(
        default_factory=lambda: {
            "type": "object",
            "required": ["id", "title"],
            "properties": {"id": {"type": "string"}, "title": {"type": "string"}},
        }
    )


class Content(content_rpc.ContentServiceServicer):
    def __init__(self) -> None:
        self.calls = 0
        self.user_id: int | None = None

    def CreateProject(
        self, request: content.CreateProjectRequest, context: grpc.ServicerContext
    ) -> content.Project:
        self.calls += 1
        self.user_id = request.context.user_id
        assert request.context.HasField("user_id")
        assert request.context.environment == cap.PRT
        assert request.context.request_id == "transport-test"
        assert request.context.client == "PC"
        return content.Project(id=str(self.user_id), title=request.title, revision=1)


def test_registered_descriptor_rejections() -> None:
    assert registered_method(Plan()).name == "CreateProject"
    with pytest.raises(TransportError):
        registered_method(replace(Plan(), method_name="NotRegistered"))
    with pytest.raises(TransportError):
        registered_method(replace(Plan(), context_field="title"))
    bundle = descriptor_pb2.FileDescriptorSet()
    bundle.file.add().ParseFromString(content.DESCRIPTOR.serialized_pb)
    with pytest.raises(TransportError, match="DESCRIPTOR_DEPENDENCY_INVALID"):
        registered_method(
            replace(
                Plan(), descriptor_set_base64=base64.b64encode(bundle.SerializeToString()).decode()
            )
        )


def test_endpoints_fail_closed() -> None:
    with pytest.raises(TransportError):
        Endpoint("example.com", 5000, loopback_plaintext=True)
    with pytest.raises(TransportError):
        Endpoint("example.com", 5000)
    with pytest.raises(TransportError):
        Endpoint("https://example.com", 5000)


def test_context_wire_compatibility_ignores_unrelated_protocol_changes() -> None:
    bundle = descriptor_pb2.FileDescriptorSet.FromString(base64.b64decode(descriptor()))
    for message in bundle.file[0].message_type:
        runtime = cap.DESCRIPTOR.message_types_by_name[message.name]
        for item in message.field:
            item.json_name = runtime.fields_by_name[item.name].json_name
    context = bundle.file[0].message_type[0]
    context.field[0].name = "renamed_identity"
    context.field[0].json_name = "platformUser"
    context.field.add(name="extra_context", number=99, type=9)
    bundle.file[0].message_type.add(name="UnrelatedMessage")
    bundle.file[0].service.clear()
    standard = bundle.SerializeToString()
    assert registered_method(
        replace(Plan(), descriptor_set_base64=base64.b64encode(standard).decode())
    ).name == "CreateProject"
    # Normalization must not alter the submitted descriptor.
    assert bundle.SerializeToString() == standard
    for attribute, value in (
        ("number", 999),
        ("type", descriptor_pb2.FieldDescriptorProto.TYPE_STRING),
    ):
        changed = descriptor_pb2.FileDescriptorSet.FromString(standard)
        setattr(changed.file[0].message_type[0].field[0], attribute, value)
        with pytest.raises(TransportError, match="INCOMPATIBLE_EXECUTION_CONTEXT"):
            registered_method(replace(
                Plan(), descriptor_set_base64=base64.b64encode(changed.SerializeToString()).decode()
            ))


def test_modified_platform_context_and_streaming_are_rejected() -> None:
    bundle = descriptor_pb2.FileDescriptorSet.FromString(base64.b64decode(descriptor()))
    bundle.file[0].message_type[0].field[0].type = descriptor_pb2.FieldDescriptorProto.TYPE_STRING
    tampered = base64.b64encode(bundle.SerializeToString()).decode()
    with pytest.raises(TransportError, match="INCOMPATIBLE_EXECUTION_CONTEXT"):
        registered_method(replace(Plan(), descriptor_set_base64=tampered))
    bundle = descriptor_pb2.FileDescriptorSet.FromString(base64.b64decode(descriptor()))
    bundle.file[1].service[0].method[0].server_streaming = True
    streaming = base64.b64encode(bundle.SerializeToString()).decode()
    with pytest.raises(TransportError, match="REGISTERED_UNARY_CONTEXT_REQUIRED"):
        registered_method(replace(Plan(), descriptor_set_base64=streaming))


@pytest.mark.parametrize("change", ["missing", "repeated", "oneof", "environment"])
def test_injected_context_incompatible_fields_are_rejected(change: str) -> None:
    bundle = descriptor_pb2.FileDescriptorSet.FromString(base64.b64decode(descriptor()))
    context = bundle.file[0].message_type[0]
    if change == "missing":
        del context.field[0]
        # Remove the now-unused synthetic optional oneof too.
        context.ClearField("oneof_decl")
    elif change == "repeated":
        context.field[0].ClearField("oneof_index")
        context.field[0].ClearField("proto3_optional")
        context.ClearField("oneof_decl")
        context.field[0].label = descriptor_pb2.FieldDescriptorProto.LABEL_REPEATED
    elif change == "oneof":
        index = len(context.oneof_decl)
        context.oneof_decl.add(name="exclusive_platform_fields")
        context.field[2].oneof_index = index
        context.field[3].oneof_index = index
        # Real oneofs must precede synthetic ones in a valid proto3 descriptor.
        context.oneof_decl.reverse()
        for item in context.field:
            if item.HasField("oneof_index"):
                item.oneof_index = index - item.oneof_index
    else:
        environment = next(item for item in bundle.file[0].enum_type if item.name == "Environment")
        next(item for item in environment.value if item.name == "PRT").number = 99
    with pytest.raises(TransportError, match="INCOMPATIBLE_EXECUTION_CONTEXT"):
        registered_method(replace(
            Plan(), descriptor_set_base64=base64.b64encode(bundle.SerializeToString()).decode()
        ))


def test_real_rpc_transport_and_rejection_before_dispatch() -> None:
    service = Content()
    with ThreadPoolExecutor(max_workers=1) as executor:
        server = grpc.server(executor)
        content_rpc.add_ContentServiceServicer_to_server(service, server)
        port = server.add_insecure_port("127.0.0.1:0")
        server.start()
        try:
            transport = GrpcTransport(
                {("content", "PRT"): Endpoint("127.0.0.1", port, loopback_plaintext=True)}
            )
            ctx = TrustedContext(
                user_id=2**63 - 1,
                environment=Environment.PRT,
                request_id="transport-test",
                client="PC",
            )
            bundle = descriptor_pb2.FileDescriptorSet.FromString(base64.b64decode(descriptor()))
            bundle.file[0].message_type[0].field[0].name = "renamed_identity"
            bundle.file[0].message_type[0].field[0].json_name = "platformUser"
            compatible_plan = replace(
                Plan(), descriptor_set_base64=base64.b64encode(bundle.SerializeToString()).decode()
            )
            result = transport.execute(compatible_plan, {"title": "reading"}, ctx)
            assert isinstance(result, dict)
            assert result["id"] == str(2**63 - 1) and result["title"] == "reading"
            assert service.user_id == 2**63 - 1 and service.calls == 1
            for invalid in ({"context": {}}, {"notAField": "value"}):
                with pytest.raises(TransportError):
                    transport.execute(Plan(), invalid, ctx)
            with pytest.raises(TransportError, match="EXACT_TARGET_ENVIRONMENT_REQUIRED"):
                transport.execute(Plan(), {}, replace(ctx, environment=Environment.ONLINE))
            with pytest.raises(TransportError, match="EXTERNAL_SCHEMA_REFERENCE_FORBIDDEN"):
                transport.execute(
                    replace(
                        Plan(), technical_output_schema={"$ref": "https://example.invalid/schema"}
                    ),
                    {},
                    ctx,
                )
            assert service.calls == 1
            with pytest.raises(TransportError, match="RESPONSE_SCHEMA_INVALID"):
                transport.execute(
                    replace(Plan(), technical_output_schema={"type": "array"}),
                    {"title": "reading"},
                    ctx,
                )
            assert service.calls == 2
            # Exercise mapping kernel + actual downstream RPC, not just an injected fake port.
            from a2flow_capability.executor import CapabilityExecutor

            published = PublishedPlan(
                source_id="source-test",
                source_digest="a" * 64,
                resolved_environment=Environment.PRT,
                action_code="content.project.create",
                capability_version=1,
                client_type="PC",
                target_key="content",
                service_name=Plan().service_name,
                method_name="CreateProject",
                descriptor_set_base64=descriptor(),
                context_field="context",
                timeout_ms=3000,
                max_response_bytes=1024 * 1024,
                technical_output_schema=Plan().technical_output_schema,
                arguments=(ArgumentDefinition("projectTitle", ValueSchema(JsonKind.STRING), True),),
                request_mappings=(RequestMapping("projectTitle", "title"),),
            )
            result = CapabilityExecutor(transport).execute(
                published, {"projectTitle": "mapped"}, ctx
            )
            assert result.success and isinstance(result.data, dict)
            assert result.data["title"] == "mapped" and service.calls == 3
        finally:
            server.stop(0).wait()
